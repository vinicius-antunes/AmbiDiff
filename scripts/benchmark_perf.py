"""Compara dois checkouts em subprocessos, mesma configuração e servidores locais."""
import argparse
import json
import platform
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from fixtures_perf import portais_perf

CODE=r'''
import sys,json,threading,time
sys.path.insert(0,sys.argv[1])
from ambidiff.core import executar
from ambidiff import paired
orig=paired._extrair_page
primeiras={}
def extrair(*args,**kwargs):
    pagina=orig(*args,**kwargs)
    primeiras.setdefault(pagina.url,pagina)
    return pagina
paired._extrair_page=extrair
start=time.perf_counter()
r=executar(sys.argv[2],sys.argv[3],'PRD','LAB',threading.Event(),lambda _:None,lambda _:None,varredura_inteligente=True)
# Canonical comparison ignores timing, ordering of incidental DIV IDs and origins.
def normal(url):
    for base in sys.argv[2:4]:
        from urllib.parse import urlsplit
        url=url.replace(urlsplit(base).netloc,'ambiente.test')
    return url
fingerprints=[]
for d in r['divergencias']:
    if d.get('tipo')=='Texto' and d.get('texto_a') and d.get('texto_b'):
        fingerprints.extend([('Texto',d['texto_a'],d.get('presente_em',''),'','',d.get('ocorrencias_total',1)),
                             ('Texto',d['texto_b'],d.get('nao_identificado_em',''),'','',d.get('ocorrencias_total',1))])
    else:fingerprints.append((d.get('tipo',''),d.get('elemento',''),d.get('presente_em',''),normal(d.get('destino_a','')),normal(d.get('destino_b','')),d.get('ocorrencias_total',1)))
fingerprints=sorted(fingerprints)

inspecoes=sorted((normal(url),sorted({(i.tipo,i.nome,i.local,normal(i.destino),i.funcao) for i in pagina.itens}),pagina.coleta.get('estavel'),pagina.coleta.get('rolagem_limitada')) for url,pagina in primeiras.items())
print(json.dumps({'divergencias_agrupadas_observadas':len(r['divergencias']),'pares_descobertos':r['metricas']['contagens'].get('pares_descobertos',max(x['visitadas']+x['pendentes'] for x in r['meta_varredura'].values())),'interrupcoes':[x['motivo_parada'] for x in r['meta_varredura'].values() if x['motivo_parada']],'inspecoes_primeiras_por_pagina':inspecoes,'inconclusivos_unicos':len({json.dumps(x,sort_keys=True) for x in r['otimizacao']['equivalencias_inconclusivas']}),'falsos_positivos_conhecidos':None,'tempo_segundos':time.perf_counter()-start,'paginas':r['paginas'],
 'situacao':r['situacao_analise'],'falhas':r['falhas'],'pendencias':r['pendencias'],
 'sem_inspecao_profunda':r['otimizacao']['quantidade_paginas_sem_inspecao_profunda'],
 'metricas':r['metricas'],'divergencias':fingerprints,
 'pares_visitados':max(x['visitadas'] for x in r['meta_varredura'].values()),
 'pares_pendentes':max(x['pendentes'] for x in r['meta_varredura'].values())},ensure_ascii=False))
'''

def benchmark(baseline,paginas=3,repeticoes=3):
    results=[]
    for dinamico in (False,True):
        with portais_perf(paginas,dinamico) as (bases,requests):
            for n in range(repeticoes):
                for version in (('anterior','otimizada') if n%2==0 else ('otimizada','anterior')):
                    print(f'{"dinamico" if dinamico else "estavel"} {n+1}/{repeticoes}: {version}',file=sys.stderr,flush=True)
                    before=len(requests)
                    root=baseline if version=='anterior' else ROOT
                    process=subprocess.run([sys.executable,'-B','-c',CODE,str(root),*bases],capture_output=True,text=True,timeout=300,check=True)
                    run=json.loads(process.stdout);run.update(versao=version,cenario='dinamico' if dinamico else 'estavel',repeticao=n+1,requisicoes_servidor=len(requests)-before)
                    results.append(run)
    summaries={}
    for scenario in ('estavel','dinamico'):
        runs=[r for r in results if r['cenario']==scenario]
        med={v:statistics.median(r['tempo_segundos'] for r in runs if r['versao']==v) for v in ('anterior','otimizada')}
        same=all((r['divergencias'],r['paginas'],r['sem_inspecao_profunda'],r['pares_pendentes'],r['falhas'],r['inspecoes_primeiras_por_pagina'])==(runs[0]['divergencias'],runs[0]['paginas'],runs[0]['sem_inspecao_profunda'],runs[0]['pares_pendentes'],runs[0]['falhas'],runs[0]['inspecoes_primeiras_por_pagina']) for r in runs)
        summaries[scenario]={'medianas_segundos':med,'variacao_segundos':{v:[min(r['tempo_segundos'] for r in runs if r['versao']==v),max(r['tempo_segundos'] for r in runs if r['versao']==v)] for v in med},'reducao_percentual':round(100*(1-med['otimizada']/med['anterior']),2),'cobertura_e_achados_equivalentes':same,'meta_sintetica_atingida':same and med['otimizada']<=med['anterior']/2}
    return {'referencia_commit':subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip(),'referencia':str(baseline),'python':platform.python_version(),'plataforma':platform.platform(),'opcoes':{'inteligente':True,'base_desatualizada':False,'capturas':False,'cliques':False,'auditoria':False},'paginas_por_ambiente':paginas,'repeticoes':repeticoes,'resumos':summaries,'execucoes':results,'limite':'Somente loopback sintético. Textos pareados são decompostos nos dois valores/ambientes para comparar observações, independentemente da consolidação em cartões. Cobertura comparada por itens e contextos efetivamente extraídos em cada página, achados, falhas e omissões. Falsos positivos não recebem auditoria humana formal neste benchmark; não comprova desempenho nos portais reais nem igualdade de todos os estados futuros de JavaScript.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--pages',type=int,default=3);parser.add_argument('--repetitions',type=int,default=3);args=parser.parse_args()
    if not 1<=args.pages<=20 or not 1<=args.repetitions<=10:parser.error('Limites: 1–20 páginas, 1–10 repetições.')
    print(json.dumps(benchmark(args.baseline,args.pages,args.repetitions),ensure_ascii=False,indent=2))
