"""Grafo Liferay fictício idêntico antes/depois; não mede portais reais.

4ms por abertura HTML e 1ms por HEAD simulado. --root aponta para uma cópia
da versão a medir. Conteúdo editorial profundo/portais vizinhos é omitido de
propósito: não constitui cobertura equivalente dessas páginas.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
from urllib.parse import urlsplit
from unittest.mock import patch

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--repeats',type=int,default=3)
args=parser.parse_args()
if not 1<=args.repeats<=20:parser.error('Repetições entre 1 e 20')
sys.path[:0]=[str(args.root),str(args.root/'tests')]
import test_update18 as fixture
from test_update18 import A,B,opcao

sleep=time.sleep
old_patch=fixture.patch
real_page=fixture.Pagina
def counted(target,*a,**kw):
    if target=='ambidiff.paired._abrir':
        original=kw['side_effect']
        def delayed(*a,**kw):sleep(.004);return original(*a,**kw)
        kw['side_effect']=delayed
    return old_patch(target,*a,**kw)
fixture.patch=counted

def page(*a,**kw):
    result=real_page(*a,**kw);u=result.url;base=A if u.startswith(A) else B
    result.coleta['portal']={'canonical':base+'web/verde/inicio','group_id':'10'}
    if urlsplit(u).path=='/colecao':
        result.coleta['referencias_finalidade']=[{'url':base+'colecao?_portlet_INSTANCE_X_cur='+str(n),'finalidade':'listagem_editorial'} for n in range(1,116)]
    return result

def graph(u):
    base=A if u.startswith(A) else B;p=urlsplit(u)
    if u==base:
        return [opcao('Coleção',base+'colecao','Menu'),opcao('SIMCAR',base+'web/compartilhado/simcar','Serviços'),opcao('Portal vizinho',base+'web/outro','Menu')]+([opcao('ÁUDIOS',A+'audio.pdf','Menu')] if base==A else [])
    if p.path=='/colecao':return [opcao(str(n),base+'colecao?_portlet_INSTANCE_X_cur='+str(n),'Paginação') for n in range(1,116)]
    if p.path=='/web/outro':return [opcao('Área '+str(n),base+'web/outro/area'+str(n),'Menu') for n in range(10)]
    if p.path=='/web/compartilhado/simcar':return [opcao('Árvore vizinha',base+'web/compartilhado/filho','Menu')]
    return []

runs=[]
for _ in range(args.repeats):
    heads=[]
    def head(self,u):
        heads.append(u);sleep(.001)
        return {'classificacao':'DESTINO_ACESSIVEL','url_final':u,'status':200,'bytes_lidos':0}
    # O helper atual simula HEAD internamente; as duas versões recebem o
    # mesmo transporte cronometrado por meio do seu contexto de patches.
    def patched(target,*a,**kw):
        if target=='ambidiff.destinations.Destinos.conferir':return old_patch(target,head)
        return counted(target,*a,**kw)
    fixture.patch=patched
    start=time.perf_counter()
    with patch.object(fixture,'Pagina',side_effect=page),patch('ambidiff.destinations.Destinos.conferir',head):
        r,opened,_=fixture.executar(graph)
    runs.append({'seconds':round(time.perf_counter()-start,6),'html_openings':len(opened),'head_calls':len(heads),
        'admitted':r['andamento']['pares_admitidos_html'],'compared':r['andamento']['pares_comparados'],
        'failed':r['andamento']['pares_com_falha'],'pending':r['andamento']['pares_pendentes'],
        'audios':any(d.get('elemento')=='ÁUDIOS' for d in r['divergencias']),
        'shared_service':all(base+'web/compartilhado/simcar' in opened for base in (A,B)),
        'neighbor_openings':sum('/web/outro' in u for u in opened),
        'later_editorial_openings':sum('_cur=' in u and not u.endswith('_cur=1') for u in opened),
        'filter':r.get('filtro_urls',{})})
print(json.dumps({'median_seconds':statistics.median(r['seconds'] for r in runs),'runs':runs,
    'scope':'Simulado: 115 páginas editoriais, portal vizinho e serviço compartilhado. Não mede ganho real nem cobertura do conteúdo omitido.'},ensure_ascii=False,indent=2))
