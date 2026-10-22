"""Exportação equivalente v1/v2: referências sintéticas, nenhum acesso à rede."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CODE=r'''
import sys,json,tempfile,time,hashlib
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from ambidiff.reports import exportar
from ambidiff.storage import ler_original
rid='20261022_150000_abcdef'
quantidade=int(sys.argv[3])
docs=[{'elemento':'Referência '+str(n),'destino_a':'https://a.test/manual.pdf','destino_b':'https://b.test/manual.pdf',
    'classificacao':'Verificação inconclusiva','a':{'situacao':'inconclusivo','motivo':'HEAD não suportado; corpo não lido','bytes_lidos':0},
    'b':{'situacao':'inconclusivo','motivo':'HEAD não suportado; corpo não lido','bytes_lidos':0}} for n in range(quantidade)]
dados={'id':rid,'site_nome':'Portal sintético','formato_compacto':sys.argv[2]=='atual',
    'paginas':{'PRD':10,'DES':10},'ambientes':{'PRD':'https://a.test/','DES':'https://b.test/'},
    'divergencias':[{'id':'DIV-0001','tipo':'Opção','elemento':'ÁUDIOS','local':'Institucional','descricao':'Opção não identificada na seção correspondente.'}],
    'documentos_verificados':docs,'metricas':{'releituras':[]},'otimizacao':{'equivalencias_verificadas':[
        {'elemento':'Rodapé','url_a':'https://a.test/'+str(n),'url_b':'https://b.test/'+str(n),'nivel':'DOM estático observado'} for n in range(quantidade)]}}
with tempfile.TemporaryDirectory() as td:
    root=Path(td);inicio=time.perf_counter();paths=exportar(dados,root,rid);duracao=time.perf_counter()-inicio
    lido=ler_original(root,rid)
    assert lido['documentos_verificados']==docs
    assert lido['otimizacao']==dados['otimizacao']
    print(json.dumps({'duracao_segundos':duracao,'json_principal_bytes':Path(paths['json']).stat().st_size,
        'html_bytes':Path(paths['html']).stat().st_size,'csv_bytes':Path(paths['csv']).stat().st_size,
        'json_total_bytes':sum(p.stat().st_size for p in root.glob('*.json')),
        'observacoes_preservadas':len(lido['documentos_verificados']),
        'evidencia_sha256':hashlib.sha256(json.dumps({'documentos':lido['documentos_verificados'],'otimizacao':lido['otimizacao']},sort_keys=True).encode()).hexdigest()}))
'''


def benchmark(baseline,referencias,repeticoes):
    runs=[]
    for n in range(repeticoes):
        for versao in (('anterior','atual') if n%2==0 else ('atual','anterior')):
            root=baseline if versao=='anterior' else ROOT
            r=subprocess.run([sys.executable,'-B','-c',CODE,str(root),versao,str(referencias)],capture_output=True,text=True,check=True)
            runs.append(dict(json.loads(r.stdout),versao=versao,repeticao=n+1))
    campos=('duracao_segundos','json_principal_bytes','html_bytes','csv_bytes','json_total_bytes')
    medianas={v:{k:statistics.median(r[k] for r in runs if r['versao']==v) for k in campos} for v in ('anterior','atual')}
    return {'referencia_commit':subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip(),
        'referencias':referencias,'repeticoes':repeticoes,'medianas':medianas,
        'observacoes_equivalentes':len({r['evidencia_sha256'] for r in runs})==1,
        'reducao_json_principal_percentual':round(100*(1-medianas['atual']['json_principal_bytes']/medianas['anterior']['json_principal_bytes']),2),
        'execucoes':runs,'limite':'Exportação sintética v1 versus formato compacto v2 do fluxo oficial. Não mede o relatório real do INTERMAT, navegação nem disco Windows. O total JSON inclui os detalhes separados; não confundir redução do principal com redução total de armazenamento.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--references',type=int,default=500);p.add_argument('--repetitions',type=int,default=3);a=p.parse_args()
    if not 1<=a.references<=10000 or not 1<=a.repetitions<=10:p.error('Limites: 1–10000 referências e 1–10 repetições.')
    print(json.dumps(benchmark(a.baseline,a.references,a.repetitions),ensure_ascii=False,indent=2))
