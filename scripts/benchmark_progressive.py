"""Antes/depois em grafo local simulado; cobertura limitada é parte do resultado."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CODE=r'''
import sys,time,json,copy,tempfile,tracemalloc,inspect,cProfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1]);sys.path.insert(1,sys.argv[2])
from test_intermat import pipeline,A,B
from ambidiff import paired,checkpoints as cp
from ambidiff.core import Item
from ambidiff.storage import atomic_json
from ambidiff.relevance import preparar,classificar
n=int(sys.argv[3]);cenario=sys.argv[4];memory=sys.argv[5]=='1'
snaps=[];pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
base=snaps[0]['retomada'];primeira=None;critica=None;io_checkpoint=0
original=paired.comparacao
def comparar(*args,**kwargs):
    global primeira,critica
    rows=original(*args,**kwargs)
    if rows and primeira is None and any(classificar(r,{'PRD':A,'DES':B})[0]=='relevante' for r in rows):primeira=time.perf_counter()-start
    if critica is None and any(r.get('elemento')=='Controle crítico' for r in rows):critica=time.perf_counter()-start
    return rows
def ajustar(p):
    host=A if p.url.startswith(A) else B
    if cenario=='editorial':
        if p.url==host:
            p.itens=[Item('Opção','Notícia '+str(i),'Notícia '+str(i),local='Notícias',destino=host+'noticias/'+str(i)) for i in range(1,n+1)]
            if host==A:p.itens.append(Item('Opção','ÁUDIOS','ÁUDIOS',local='Menu',destino=host+'audio.pdf'))
        else:
            p.itens=[]
            if p.url.endswith('noticias/1'):p.itens.append(Item('Opção','Próxima consulta','Próxima consulta',local='Menu',destino=host+'consulta/9999'))
            if '/consulta/' in p.url and host==A:p.itens.append(Item('Opção','Controle crítico','Controle crítico',local='Serviços',destino=host+'servico.pdf'))
    if p.url==host:
        p.itens.append(Item('Opção','Compartilhar','Compartilhar',local='Rodapé',destino='https://www.facebook.com/sharer/sharer.php?u='+host+'pagina'))
args={}
if 'estrategia' in inspect.signature(paired.executar_pareado).parameters:args={'estrategia':'progressiva','orcamento_minutos':0}
with tempfile.TemporaryDirectory() as td:
    path=Path(td)/'checkpoint.json'
    def salvar(d):
        global io_checkpoint
        start_io=time.perf_counter()
        try:
            if hasattr(cp,'gravar'):return cp.gravar(path,d)
            atomic_json(path,d)
        finally:io_checkpoint+=time.perf_counter()-start_io
    if memory:tracemalloc.start()
    profile=cProfile.Profile();start=time.perf_counter()
    if not memory:profile.enable()
    with patch('ambidiff.paired.comparacao',side_effect=comparar):r,opened=pipeline(n=n,retomada=base,ajustar=ajustar,checkpoint=salvar,ciclo=True,**args)
    total=time.perf_counter()-start;profile.disable()
    snapshots=sum(x.totaltime for x in profile.getstats() if not isinstance(x.code,str) and x.code.co_name=='snapshot' and x.code.co_filename.endswith('paired.py'))
    peak=tracemalloc.get_traced_memory()[1] if memory else None
    if memory:tracemalloc.stop()
    view=preparar(r);m=r['metricas'];names={d['elemento'] for d in view['divergencias'] if d.get('classificacao')=='relevante'}
    print(json.dumps({'cenario':cenario,'paginas_planejadas':n,'tempo_total':total,'memoria_python_pico_bytes':peak,'tempo_primeira_div_relevante':primeira,'tempo_controle_critico':critica,
        'pares_descobertos':r['andamento']['pares_descobertos'],'pares_comparados':r['paginas']['PRD'],'pendentes':r['andamento']['pares_pendentes'],
        'editoriais_aprofundadas':sum('/noticias/' in u for u in opened)//2,'editoriais_representantes':r.get('cobertura',{}).get('representantes_segmento',[]),
        'divs_estruturais_sentinelas':sorted(names & {'ÁUDIOS','Controle crítico'}),'compartilhamentos_relevantes':sum(d.get('elemento')=='Compartilhar' and d.get('classificacao')=='relevante' for d in view['divergencias']),
        'duplicacoes_evitadas':m['contagens'].get('urls_duplicadas',0),'tempo_checkpoint':snapshots+io_checkpoint,'checkpoint_construcao_assinatura':snapshots,'checkpoint_serializacao_gravacao':io_checkpoint,
        'tempos':m['tempos_segundos'],'contagens':m['contagens'],'situacao':r['situacao_analise'],'aberturas':len(opened)}))
'''


def medir(baseline,repeticoes,memory_pages=200):
    rows=[];memory=[]
    for cenario,n in [('institucional',1005),('editorial',300)]:
        for i in range(repeticoes):
            for nome in (('anterior','atual') if i%2==0 else ('atual','anterior')):
                root=baseline if nome=='anterior' else ROOT
                print(cenario+' '+nome+' '+str(i+1),file=sys.stderr,flush=True)
                r=subprocess.run([sys.executable,'-B','-c',CODE,str(root),str(ROOT/'tests'),str(n),cenario,'0'],capture_output=True,text=True,check=True,timeout=240)
                rows.append(dict(json.loads(r.stdout),versao=nome,repeticao=i+1))
        for nome,root in [('anterior',baseline),('atual',ROOT)]:
            r=subprocess.run([sys.executable,'-B','-c',CODE,str(root),str(ROOT/'tests'),str(min(n,memory_pages)),cenario,'1'],capture_output=True,text=True,check=True,timeout=240)
            memory.append(dict(json.loads(r.stdout),versao=nome))
    resumo={}
    for cenario in ('institucional','editorial'):
        sub={nome:[r for r in rows if r['cenario']==cenario and r['versao']==nome] for nome in ('anterior','atual')}
        resumo[cenario]={nome:{k:statistics.median(r[k] for r in rs if r[k] is not None) if any(r[k] is not None for r in rs) else None for k in ('tempo_total','tempo_checkpoint','tempo_primeira_div_relevante','tempo_controle_critico','pares_comparados','pendentes','editoriais_aprofundadas')} for nome,rs in sub.items()}
    return {'referencia':subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip(),'repeticoes':repeticoes,'resumos':resumo,'execucoes':rows,'memoria_execucoes_separadas':memory,
        'limites':'Grafo fabricado, navegadores/extração simulados; CP real em arquivo temporário. Sem rede. cProfile ativo nas rodadas de tempo de ambas as versões para medir snapshot e assinatura, somado ao callback de gravação (fases não sobrepostas); inclui custo de instrumentação. Preparação/navegação não são medidas de Chromium. Memória Python via tracemalloc sem cProfile em rodadas separadas, por padrão com até 200 páginas planejadas por ambiente, configuráveis; não representa RSS do navegador. Coberturas editoriais são diferentes e explicitadas; comparar sentinelas não valida as páginas adiadas. Orçamento removido para isolar a estratégia.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--repetitions',type=int,default=3);p.add_argument('--memory-pages',type=int,default=200);a=p.parse_args()
    if not 1<=a.repetitions<=10:p.error('Use de 1 a 10 repetições.')
    if not 1<=a.memory_pages<=3000:p.error('Memória: use de 1 a 3000 páginas sintéticas.')
    print(json.dumps(medir(a.baseline,a.repetitions,a.memory_pages),ensure_ascii=False,indent=2))
