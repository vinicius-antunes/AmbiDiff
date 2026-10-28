"""Falha real de página em Chromium loopback; sem acesso institucional."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from fixtures_perf import portais_perf

CODE=r'''
import json,sys,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
from ambidiff import paired,checkpoints as cp
from ambidiff.core import executar,_abrir
from ambidiff.diagnostics import montar_diagnostico
closed=False
ba,bb=sys.argv[2:4]
def abrir(p,u):
    global closed
    if not closed and u.endswith('/pagina/1'):
        closed=True;p.close()
    return _abrir(p,u)
with tempfile.TemporaryDirectory() as td:
    root=Path(td);checkpoint=root/'checkpoint.json';inicio=time.perf_counter();erro=None
    with patch('ambidiff.paired._abrir',side_effect=abrir):
        try:r=executar(ba,bb,'PRD','LAB',threading.Event(),lambda _:None,lambda _:None,varredura_inteligente=True,evidencias_dir=root/'evidencias',checkpoint=lambda d:cp.gravar(checkpoint,d))
        except Exception as ex:
            erro=type(ex).__name__;r=cp.recuperar(json.loads(checkpoint.read_text()))
            r.update(estado_execucao='falha',situacao_analise='parcial',erro_execucao=str(ex))
    total=time.perf_counter()-inicio
    diag=montar_diagnostico(r);andamento=r['andamento'];metricas=r.get('metricas',{})
    print(json.dumps({'tempo_segundos':total,'erro_fatal_tipo':erro,'pares_comparados':andamento.get('pares_comparados'),
      'pares_pendentes':andamento.get('pares_pendentes'),'pares_descobertos':andamento.get('pares_descobertos'),
      'falhas_automacao_contadas':diag.get('contadores_diagnostico',{}).get('automacao'),
      'pngs_gerados':len(list(root.rglob('*.png'))),'tempos':metricas.get('tempos_segundos',{}),'contagens':metricas.get('contagens',{}),
      'checkpoint_valido':bool(cp.validar(json.loads(checkpoint.read_text())['retomada']))}))
'''

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--repetitions',type=int,default=3);a=p.parse_args()
    if not 1<=a.repetitions<=10:p.error('Use de 1 a 10 repetições.')
    rows=[]
    with portais_perf(3) as (bases,requests):
        for i in range(a.repetitions):
            for version in (('anterior','atual') if i%2==0 else ('atual','anterior')):
                print(f'recuperação {version} {i+1}',file=sys.stderr,flush=True)
                root=a.baseline if version=='anterior' else ROOT
                result=subprocess.run([sys.executable,'-B','-c',CODE,str(root),*bases],capture_output=True,text=True,check=True,timeout=180)
                rows.append(dict(json.loads(result.stdout),versao=version,repeticao=i+1))
    print(json.dumps({'referencia_commit':subprocess.check_output(['git','-C',str(a.baseline),'rev-parse','HEAD'],text=True).strip(),'execucoes':rows,
      'limites':'Chromium headless real, três pares loopback e fechamento deliberado de uma página. Checkpoint/evidências em pasta temporária. Cobertura diferente: a referência encerra parcialmente; a versão atual continua. Tempos não representam ganho/perda comparável de velocidade nem portais reais. AMBIDIFF_HEADLESS=1 é necessário apenas para manter a referência a46aad2 oculta no benchmark.'},ensure_ascii=False,indent=2))
