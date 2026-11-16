"""Benchmark controlado com o mesmo grafo fictício antes/depois, sem rede.

python scripts/benchmark_urlfilter.py --root /copia/da/versao --repeats 3
4 ms por abertura simulam custo fixo; não medem desempenho em portal real.
"""
import argparse
from pathlib import Path
import sys
import time
import statistics
import json

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--repeats',type=int,default=3)
args=parser.parse_args()
if not 1<=args.repeats<=20:parser.error('Repetições: 1 a 20')
sys.path[:0]=[str(args.root),str(args.root/'tests')]
from test_update18 import executar,opcao,A,B
import test_update18 as fixture
sleep=time.sleep;original_patch=fixture.patch

def instrumentar(target,*a,**kw):
    if target=='ambidiff.paired._abrir':
        abrir=kw['side_effect']
        def medido(*args,**kwargs):sleep(.004);return abrir(*args,**kwargs)
        kw['side_effect']=medido
    return original_patch(target,*a,**kw)
fixture.patch=instrumentar

def grafo(u):
    base=A if u.startswith(A) else B
    if u!=base:return []
    itens=[opcao('Notícia '+str(i),base+'w/artigo-'+str(i),'Notícias',recurso='navegacao') for i in range(30)]
    itens += [opcao('Notícia página '+str(i),base+'noticias?_portlet_cur='+str(i),'Notícias') for i in range(2,12)]
    itens += [opcao('Notícia do ano '+str(i),base+'noticias?year='+str(i),'Notícias') for i in range(2020,2025)]
    itens += [opcao('Pesquisa',base+'busca?q=teste'),opcao('Impressão',base+'?print=true'),opcao('Serviço',base+'servico','Menu'),opcao('Institucional',base+'w/estrutura','Menu')]
    if base==A:itens.append(opcao('ÁUDIOS',base+'audio.pdf','Menu'))
    return itens

runs=[]
for _ in range(args.repeats):
    inicio=time.perf_counter();r,opened,_=executar(grafo)
    runs.append({'segundos':round(time.perf_counter()-inicio,6),'aberturas':len(opened),
        'admitidos':r['andamento']['pares_admitidos_html'],'comparados':r['andamento']['pares_comparados'],
        'falhos':r['andamento']['pares_com_falha'],'divs':len(r['divergencias']),
        'audios':any(d.get('elemento')=='ÁUDIOS' for d in r['divergencias']),
        'estruturais_visitados':all(u in opened for u in (A+'servico',B+'servico',A+'w/estrutura',B+'w/estrutura')),
        'filtro':r.get('filtro_urls',{})})
print(json.dumps({'cenario':'49 referências por ambiente + ÁUDIOS unilateral; navegação simulada 4ms/abertura',
    'tempo_mediano':statistics.median(r['segundos'] for r in runs),'execucoes':runs,
    'limite':'Redução deliberada da exploração editorial; não comprova ganho em portal real. A comparação da origem e as páginas estruturais continuam.'},ensure_ascii=False,indent=2))
