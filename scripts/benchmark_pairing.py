"""Comparação controlada de grafos fictícios; não abre navegador nem acessa rede.

Uso: python scripts/benchmark_pairing.py [raiz_da_versao]
A raiz opcional deve conter código e testes da versão a medir.
"""
from pathlib import Path
import json,sys,time
raiz=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
sys.path[:0]=[str(raiz),str(raiz/'tests')]
import test_update18 as f
original=f.patch
coletas=[]
def instrumentar(target,*args,**kwargs):
    if target=='ambidiff.paired._extrair_page':
        extrair=kwargs['side_effect']
        def coletar(*a,**kw):
            coletas.append(kw.get('profunda',True));return extrair(*a,**kw)
        kwargs['side_effect']=coletar
    return original(target,*args,**kwargs)
f.patch=instrumentar
def grafo(url):
    base=f.A if url.startswith(f.A) else f.B
    return [f.opcao('Serviço '+str(i),base+str(i),'Menu lateral' if base==f.A else 'Rodapé',recurso='navegacao') for i in range(25)] if url==base else []
for cenario in ('menus_reorganizados','noticias_exclusivas'):
    coletas.clear()
    def noticias(url):
        if url==f.A:return [f.opcao('Notícia '+str(i),f.A+'noticias/'+str(i),'Notícias',recurso='navegacao') for i in range(25)]
        return []
    inicio=time.perf_counter();r,abertas,_=f.executar(grafo if cenario=='menus_reorganizados' else noticias)
    print(json.dumps({'cenario':cenario,'comparados':r['andamento']['pares_comparados'],
        'inconclusivos':r['andamento']['pares_inconclusivos'],'admitidos':r['andamento']['pares_descobertos'],
        'aberturas':len(abertas),'coletas_com_preparacao_profunda':sum(coletas),
        'coletas_superficiais':len(coletas)-sum(coletas),'falhas':r['andamento']['pares_com_falha'],
        'divs':len(r['divergencias']),'tempo_simulado_segundos':round(time.perf_counter()-inicio,4)},ensure_ascii=False))
