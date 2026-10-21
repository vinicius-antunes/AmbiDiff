"""Gerenciamento local dos relatórios e exclusões de DIVs.

O JSON original da execução é mantido intacto; um arquivo auxiliar com IDs
ocultados preserva as decisões do revisor. Sem acesso a rede ou aplicações externas.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import threading
from datetime import datetime

RUN_RE=re.compile(r'\d{8}_\d{6}_[a-f0-9]{6}\Z')
DIV_RE=re.compile(r'DIV-\d{4,5}\Z')


def valid_run(run_id:str)->bool:
    return isinstance(run_id,str) and bool(RUN_RE.fullmatch(run_id))


def original_path(root:Path,run_id:str)->Path:
    if not valid_run(run_id):raise ValueError('ID de relatório inválido.')
    return root / f'comparacao_{run_id}.json'


def _overlay(root:Path,run_id:str)->Path:
    if not valid_run(run_id):raise ValueError('ID de relatório inválido.')
    return root / f'exclusoes_{run_id}.json'


def atomic_json(path:Path,data)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    try:
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


def ler_original(root:Path,run_id:str)->dict:
    return json.loads(original_path(root,run_id).read_text(encoding='utf-8'))


def ler_exclusoes(root:Path,run_id:str)->set[str]:
    file=_overlay(root,run_id)
    if not file.exists():return set()
    payload=json.loads(file.read_text(encoding='utf-8'))
    return {x for x in payload.get('ids',[]) if isinstance(x,str) and DIV_RE.fullmatch(x)}


def preparar_relatorio(root:Path,run_id:str)->dict:
    report=ler_original(root,run_id)
    original=report.get('divergencias',[])
    ignored=ler_exclusoes(root,run_id)
    report['divergencias']=[row for row in original if row.get('id') not in ignored]
    report['divergencias_ocultadas']=len(original)-len(report['divergencias'])
    report['total_original']=len(original)
    path=root/f'revisoes_{run_id}.json'
    rev=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    report['revisoes_manuais']=rev
    for row in report['divergencias']:
        if row.get('id') in rev:row['revisao_manual']=rev[row['id']]
    return report


def excluir_div(root:Path,run_id:str,div_id:str,lock:threading.RLock|None=None)->dict:
    if not isinstance(div_id,str) or not DIV_RE.fullmatch(div_id):
        raise ValueError('ID de divergência inválido.')
    def write():
        original=ler_original(root,run_id)
        ids={x.get('id') for x in original.get('divergencias',[])}
        if div_id not in ids:raise KeyError('Divergência não encontrada neste relatório.')
        old=ler_exclusoes(root,run_id)
        old.add(div_id)
        atomic_json(_overlay(root,run_id),{'ids':sorted(old),'atualizado_em':datetime.now().isoformat(timespec='seconds')})
        return preparar_relatorio(root,run_id)
    if lock is not None:
        with lock:return write()
    return write()



def registrar_revisao(root:Path,run_id:str,div_id:str,situacao:str,lock:threading.RLock|None=None)->dict:
    if not isinstance(div_id,str) or not DIV_RE.fullmatch(div_id):raise ValueError('ID de divergência inválido.')
    if situacao not in ('confirmada','pendente'):raise ValueError('Revisão deve ser confirmada ou pendente.')
    def update():
        dados=ler_original(root,run_id)
        if div_id not in {x.get('id') for x in dados.get('divergencias',[])}:raise KeyError(div_id)
        arq=root/f'revisoes_{run_id}.json'
        rev=json.loads(arq.read_text(encoding='utf-8')) if arq.exists() else {}
        if situacao=='pendente':rev.pop(div_id,None)
        else:rev[div_id]=situacao
        atomic_json(arq,rev)
        return preparar_relatorio(root,run_id)
    if lock:
        with lock:return update()
    return update()

def excluir_execucoes(root:Path,hist_path:Path,run_ids:list[str],lock:threading.RLock|None=None)->int:
    if not isinstance(run_ids,list) or not run_ids or len(run_ids)>100:
        raise ValueError('Selecione de 1 a 100 relatórios.')
    if not all(valid_run(x) for x in run_ids) or len(set(run_ids))!=len(run_ids):
        raise ValueError('Lista de relatórios inválida.')
    def delete():
        history=json.loads(hist_path.read_text(encoding='utf-8')) if hist_path.exists() else []
        indexed={x['id'] for x in history}
        if not set(run_ids)<=indexed or not all(original_path(root,x).is_file() for x in run_ids):
            raise KeyError('Um dos relatórios não existe mais no histórico.')
        # Remoção estritamente limitada aos nomes construídos a partir dos IDs validados.
        # Não segue links simbólicos para diretórios de evidência.
        for rid in run_ids:
            for prefix in ('comparacao_','comparacao_filtrado_'):
                for ext in ('json','csv','html'):
                    (root/f'{prefix}{rid}.{ext}').unlink(missing_ok=True)
            _overlay(root,rid).unlink(missing_ok=True)
            for name in ('revisoes_', 'diagnostico_', 'log_', 'checkpoint_'):
                for ext in ('json','txt'):
                    (root/f'{name}{rid}.{ext}').unlink(missing_ok=True)
            ev=root/f'evidencias_{rid}'
            if ev.is_symlink():ev.unlink()
            elif ev.is_dir():shutil.rmtree(ev)
        new_history=[x for x in history if x['id'] not in set(run_ids)]
        atomic_json(hist_path,new_history)
        return len(run_ids)
    if lock is not None:
        with lock:return delete()
    return delete()
