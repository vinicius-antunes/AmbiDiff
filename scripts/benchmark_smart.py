"""Benchmark local: python scripts/benchmark_smart.py --articles 8 --repetitions 3."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from fixtures_smart import portais
from ambidiff.core import executar


def benchmark(artigos=8,repeticoes=3):
    resultados=[]
    with portais(artigos) as (bases,requisicoes):
        for repeticao in range(repeticoes):
            # Alterna ordem para reduzir viés de aquecimento.
            for inteligente in ([False,True] if repeticao%2==0 else [True,False]):
                print(f'Repetição {repeticao+1}/{repeticoes}: '+('inteligente' if inteligente else 'atual'),file=sys.stderr,flush=True)
                inicio=time.perf_counter();antes=len(requisicoes)
                r=executar(*bases,'PRD','DES',threading.Event(),lambda _:None,lambda _:None,
                    ambiente_desatualizado='DES',varredura_inteligente=inteligente)
                resultados.append({'repeticao':repeticao+1,'modo':r['modo_varredura'],
                    'tempo_parede_segundos':round(time.perf_counter()-inicio,6),
                    'requisicoes_servidor':len(requisicoes)-antes,'metricas':r['metricas'],
                    'paginas':r['paginas'],'situacao':r['situacao_analise'],
                    'paginas_sem_inspecao_profunda':r['otimizacao']['quantidade_paginas_sem_inspecao_profunda'],
                    'divergencias':len(r['divergencias'])})
    medianas={modo:statistics.median(x['tempo_parede_segundos'] for x in resultados if x['modo']==modo)
              for modo in ('atual','inteligente')}
    return {'cenario':'Portais sintéticos HTTP locais; notícias com mesma estrutura e DES defasado declarado; sem capturas opcionais',
            'artigos_por_ambiente':artigos,'repeticoes':repeticoes,'execucoes':resultados,
            'medianas_segundos':medianas,'reducao_percentual_observada':round(100*(1-medianas['inteligente']/medianas['atual']),2),
            'limite':'Resultados locais não estimam desempenho ou equivalência de portais reais. O modo inteligente tem cobertura profunda menor e adiciona checagem documental.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--articles',type=int,default=8)
    parser.add_argument('--repetitions',type=int,default=3)
    args=parser.parse_args()
    if not 3<=args.articles<=100 or not 1<=args.repetitions<=10:parser.error('Use 3–100 artigos e 1–10 repetições.')
    print(json.dumps(benchmark(args.articles,args.repetitions),ensure_ascii=False,indent=2))
