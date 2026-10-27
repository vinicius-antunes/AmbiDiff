"""Checkpoint v1: páginas sintéticas crescentes; subprocessos isolados, sem rede."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CODE=r'''
import sys,time,json,tempfile,tracemalloc
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0,sys.argv[1]);sys.path.insert(1,sys.argv[2])
from test_intermat import pipeline,A,B
from ambidiff.core import Pagina,Item
from ambidiff import checkpoints as cp
from ambidiff.storage import atomic_json
snaps=[];pipeline(checkpoint=lambda s:snaps.append(s))
estado=snaps[0]['retomada']['estado'];n=int(sys.argv[3])
paginas={base:{base+str(i):Pagina(base+str(i),'','Portal sintético',[
    Item('Texto','Texto '+str(j),'Texto '+str(j),local='Seção',estrutura='p') for j in range(20)],['Início',str(i)],coleta={'dom_sintetico':'x'*2000}) for i in range(n)} for base in (A,B)}
estado['visitados']=[[A+str(i),B+str(i)] for i in range(n)];estado['pares_enfileirados']=estado['visitados'];estado['fila']=[]
estado['brutos']=[{'id':'DIV-'+str(i).zfill(4),'tipo':'Opção','elemento':'ÁUDIOS '+str(i),'descricao':'Diferença sintética'} for i in range(n)]
cache=cp.PaginasSerializadas() if hasattr(cp,'PaginasSerializadas') else None
tempos=[]
with tempfile.TemporaryDirectory() as td:
    path=Path(td)/'checkpoint.json'
    for rep in range(3):
        start=time.perf_counter()
        estado['paginas_a']=cache.converter(paginas[A]) if cache else {k:asdict(v) for k,v in paginas[A].items()}
        estado['paginas_b']=cache.converter(paginas[B]) if cache else {k:asdict(v) for k,v in paginas[B].items()}
        convertido=time.perf_counter();payload={'retomada':cp.empacotar(estado),'brutos':estado['brutos']};assinado=time.perf_counter()
        dumps=json.dumps;serial=[]
        def medir_json(*args,**kwargs):
            start_json=time.perf_counter();text=dumps(*args,**kwargs);serial.append(time.perf_counter()-start_json);return text
        json.dumps=medir_json
        try:
            if hasattr(cp,'gravar'):cp.gravar(path,payload)
            else:atomic_json(path,payload)
        finally:json.dumps=dumps
        fim=time.perf_counter();old=json.loads(path.read_text());vstart=time.perf_counter();rest=cp.validar(old['retomada']);vfim=time.perf_counter()
        assert len(rest['paginas_a'])==n and len(rest['brutos'])==n and len(rest['visitados'])==n
        assert rest==estado, 'O estado restaurado deve preservar todos os campos, não só contagens.'
        tempos.append({'total':fim-start,'conversao':convertido-start,'assinatura_json':assinado-convertido,'serializacao_json':sum(serial),'gravacao_e_metadados':max(0,fim-assinado-sum(serial)),'serializacao_gravacao':fim-assinado,'validacao':vfim-vstart})
    tracemalloc.start()
    c=cp.PaginasSerializadas() if cache else None
    pages=c.converter(paginas[A]) if c else {k:asdict(v) for k,v in paginas[A].items()}
    estado['paginas_a']=pages;cp.empacotar(estado);peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
    print(json.dumps({'paginas_por_ambiente':n,'medianas_segundos':{k:sorted(t[k] for t in tempos)[1] for k in tempos[0]},'amostras':tempos,'bytes_checkpoint':path.stat().st_size,'pico_alocacoes_python_bytes':peak,'dados_recuperados':True,'conteudo_restaurado_igual':True}))
'''


def executar(baseline,pages):
    rows=[]
    for n in pages:
        for nome,root in (('anterior',baseline),('atual',ROOT)):
            out=subprocess.run([sys.executable,'-B','-c',CODE,str(root),str(ROOT/'tests'),str(n)],capture_output=True,text=True,check=True,timeout=180)
            rows.append(dict(json.loads(out.stdout),versao=nome))
    return {'referencia':subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip(),
        'execucoes':rows,'limites':'Páginas e DIVs fabricadas, três snapshots do mesmo estado (primeiro frio). Mesmo conteúdo v1; arquivos temporários locais. Não mede portais nem disco Windows. Pico tracemalloc mede alocações Python de conversão e assinatura, não RSS do Chromium.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--pages',type=int,nargs='+',default=[50,200,800]);a=p.parse_args()
    if any(not 1<=n<=3000 for n in a.pages):p.error('Use de 1 a 3000 páginas sintéticas por ambiente.')
    print(json.dumps(executar(a.baseline,a.pages),ensure_ascii=False,indent=2))
