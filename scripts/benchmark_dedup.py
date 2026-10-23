"""Carga densa em grafo sintético; mede CPU/deduplicação, sem rede ou Chromium."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
CODE=r'''
import sys,time,json,hashlib
sys.path.insert(0,sys.argv[1]);sys.path.insert(1,sys.argv[2])
from test_intermat import pipeline,A,B
from ambidiff.core import Item
observacoes=[]
def ajustar(p):
    base=A if p.url.startswith(A) else B
    for i in range(30):p.itens.append(Item('Opção','Link '+str(i),'Link '+str(i),local='Menu '+str(i),destino=base))
    observacoes.append((p.url,[(i.tipo,i.nome,i.local,i.destino) for i in p.itens]))
start=time.perf_counter();r,abertas=pipeline(n=int(sys.argv[3]),ajustar=ajustar,ciclo=True);tempo=time.perf_counter()-start
prova={'paginas':r['paginas'],'abertas':sorted(abertas),'observacoes':sorted(observacoes),'divergencias':[(d['elemento'],d.get('presente_em'),d.get('ocorrencias_total')) for d in r['divergencias']]}
print(json.dumps({'tempo_segundos':tempo,'paginas':r['paginas'],'aberturas_simuladas':len(abertas),'pares_descobertos':r['andamento']['pares_descobertos'],
    'pares_pendentes':r['andamento']['pares_pendentes'],'duplicacoes_evitadas':r['metricas']['contagens'].get('urls_duplicadas'),
    'paginas_reutilizadas':r['metricas']['contagens'].get('paginas_reutilizadas',0),'metricas':r['metricas'],
    'prova_sha256':hashlib.sha256(json.dumps(prova,sort_keys=True).encode()).hexdigest()}))
'''

def benchmark(baseline,pages,reps):
    runs=[]
    for n in range(reps):
        for v in (('anterior','atual') if n%2==0 else ('atual','anterior')):
            print(str(n+1)+'/'+str(reps)+' '+v,file=sys.stderr,flush=True)
            out=subprocess.run([sys.executable,'-B','-c',CODE,str(baseline if v=='anterior' else ROOT),str(ROOT/'tests'),str(pages)],capture_output=True,text=True,check=True,timeout=180)
            runs.append(dict(json.loads(out.stdout),versao=v,repeticao=n+1))
    med={v:statistics.median(r['tempo_segundos'] for r in runs if r['versao']==v) for v in ('anterior','atual')}
    return {'referencia_commit':subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip(),'paginas_por_ambiente':pages,'repeticoes':reps,
        'medianas_segundos':med,'reducao_percentual':round(100*(1-med['atual']/med['anterior']),2),'evidencia_equivalente':len({r['prova_sha256'] for r in runs})==1,'execucoes':runs,
        'limite':'Grafo fabricado com 30 links repetidos por página, navegadores simulados e mesma extração. Mede CPU e deduplicação, não tempo de portais, renderização, rede, PDF ou custo de checkpoints. Nenhuma página é descartada por semelhança.'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--pages',type=int,default=1000);p.add_argument('--repetitions',type=int,default=3);a=p.parse_args()
    if not 1<=a.pages<=3000 or not 1<=a.repetitions<=10:p.error('Limites: 1–3000 páginas, 1–10 repetições.')
    print(json.dumps(benchmark(a.baseline,a.pages,a.repetitions),ensure_ascii=False,indent=2))
