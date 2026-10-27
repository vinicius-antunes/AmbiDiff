"""Medição controlada em Chromium loopback; compacta evidências sintéticas."""
import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path
from benchmark_perf import benchmark

QUEUE_CODE=r'''
import copy,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);sys.path.insert(1,sys.argv[2])
from test_intermat import pipeline
from ambidiff import checkpoints as cp
snaps=[];pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
with tempfile.TemporaryDirectory() as td:
    start=time.perf_counter()
    r,abertas=pipeline(n=1000,ciclo=True,retomada=snaps[0]['retomada'],estrategia=sys.argv[3],orcamento_minutos=0,checkpoint=lambda d:cp.gravar(Path(td)/'cp.json',d))
    total=time.perf_counter()-start
    recuperado=cp.validar(json.loads((Path(td)/'cp.json').read_text())['retomada'])
    print(json.dumps({'tempo_segundos':total,'aberturas_simuladas':len(abertas),'pares_comparados':r['andamento']['pares_comparados'],'pendentes':r['andamento']['pares_pendentes'],
      'falhas':len(r['falhas']),'audios_preservado':any(d['elemento']=='ÁUDIOS' for d in r['divergencias']),
      'checkpoint_visitados_validado':len(recuperado['visitados']),'metricas':r['metricas']}))
'''


def fila(baseline,repeticoes):
    root=Path(__file__).resolve().parents[1];rows=[]
    for i in range(repeticoes):
        for v in (('anterior','otimizada') if i%2==0 else ('otimizada','anterior')):
            checkout=baseline if v=='anterior' else root
            estrategia='profunda' if v=='anterior' else 'dinamica'
            run=subprocess.run([sys.executable,'-B','-c',QUEUE_CODE,str(checkout),str(root/'tests'),estrategia],capture_output=True,text=True,check=True,timeout=180)
            rows.append(dict(json.loads(run.stdout),versao=v,repeticao=i+1))
    return {'referencia_commit':subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip(),
            'medianas_segundos':{v:statistics.median(r['tempo_segundos'] for r in rows if r['versao']==v) for v in ('anterior','otimizada')},'execucoes':rows,
            'limite':'Mil pares sintéticos em cadeia, navegação/extração simuladas, checkpoint real em disco temporário. Baseline usa profunda/0 para garantir a mesma cobertura, atual dinamica/0. Não mede velocidade de Chromium/rede/Windows. Inclui construção, assinatura e gravação de checkpoints e novos estados auditáveis.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--pages',type=int,default=3);p.add_argument('--repetitions',type=int,default=3);p.add_argument('--scenario',choices=('browser','queue'),default='browser');a=p.parse_args()
    if not 1<=a.pages<=20 or not 1<=a.repetitions<=10:p.error('Use 1–20 páginas e 1–10 repetições.')
    if a.scenario=='queue':
        print(json.dumps(fila(a.baseline,a.repetitions),ensure_ascii=False,indent=2));sys.exit(0)
    dados=benchmark(a.baseline,a.pages,a.repetitions)
    for resumo in dados['resumos'].values():resumo.pop('meta_sintetica_atingida',None)
    for run in dados['execucoes']:
        for key in ('inspecoes_primeiras_por_pagina','divergencias'):
            valor=run.pop(key)
            run[key+'_quantidade']=len(valor)
            run[key+'_sha256']=hashlib.sha256(json.dumps(valor,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    dados['nota']='As listas sintéticas foram comparadas integralmente pelo benchmark e resumidas por SHA-256/quantidade neste artefato. AMBIDIFF_HEADLESS=1 somente na medição; a aplicação usa navegadores visíveis por padrão. Não mede Windows, capturas, checkpoints nem portais reais.'
    print(json.dumps(dados,ensure_ascii=False,indent=2))
