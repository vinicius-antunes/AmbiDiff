"""Antes/depois em grafo CGE fictício: 12 páginas de notícias e 4 de vídeos.

Navegação simulada em 4ms por abertura; sem portais reais. Use --root para medir
uma cópia da versão anterior sem alterar as branches ou o benchmark.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--repeats',type=int,default=3)
args=parser.parse_args()
if not 1<=args.repeats<=20:parser.error('Repetições entre 1 e 20')
sys.path[:0]=[str(args.root),str(args.root/'tests')]
import test_update18 as fixture
from test_update18 import executar,opcao,A,B
from urllib.parse import urlsplit,parse_qsl
sleep=time.sleep;old_patch=fixture.patch

def counted(target,*a,**kw):
    if target=='ambidiff.paired._abrir':
        abrir=kw['side_effect']
        def delayed(*a,**kw):sleep(.004);return abrir(*a,**kw)
        kw['side_effect']=delayed
    return old_patch(target,*a,**kw)
fixture.patch=counted

def graph(url):
    base=A if url.startswith(A) else B
    if url==base:
        return [opcao('Notícias',base+'noticias','Menu'),opcao('Vídeos',base+'videos','Menu'),opcao('Serviço',base+'servicos/consulta','Menu')]+([opcao('ÁUDIOS',base+'audio.pdf','Menu')] if base==A else [])
    route=urlsplit(url).path.rstrip('/')
    if route.endswith(('/noticias','/videos')):
        count=12 if route.endswith('noticias') else 4
        return [opcao(str(n),base+('noticias' if count==12 else 'videos')+'?_publisher_INSTANCE_TESTE_cur='+str(n), 'Notícias' if count==12 else 'Vídeos',posicao='Menu de navegação',natureza='estrutura') for n in range(1,count+1)]
    return []
runs=[]
for _ in range(args.repeats):
    start=time.perf_counter();r,opened,_=executar(graph)
    runs.append({'seconds':round(time.perf_counter()-start,6),'navigations':len(opened),'compared':r['andamento']['pares_comparados'],
        'admitted':r['andamento']['pares_admitidos_html'],'later_pages_visited':sum(any(k.endswith('_cur') and int(v)>1 for k,v in parse_qsl(urlsplit(u).query)) for u in opened),
        'audios':any(d.get('elemento')=='ÁUDIOS' for d in r['divergencias']),
        'service_visited':all(base+'servicos/consulta' in opened for base in (A,B)),
        'failed':r['andamento']['pares_com_falha'],'filter':r.get('filtro_urls',{})})
print(json.dumps({'median_seconds':statistics.median(r['seconds'] for r in runs),'runs':runs,
    'scope':'Simulado; 4ms por abertura, 12 notícias e 4 vídeos, sem comparar conteúdo profundo omitido. Não é desempenho em portal real.'},ensure_ascii=False,indent=2))
