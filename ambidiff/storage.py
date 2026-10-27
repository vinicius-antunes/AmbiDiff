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
DIV_RE=re.compile(r'DIV-\d{4,9}\Z')


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


def ler_original(root:Path,run_id:str,detalhes=True)->dict:
    report=json.loads(original_path(root,run_id).read_text(encoding='utf-8'))
    if detalhes and report.get('formato_relatorio')==2:
        arquivo=root/f'detalhes_{run_id}.json'
        if not arquivo.is_file():raise ValueError('Detalhes locais ausentes; relatório principal preservado.')
        report.update(json.loads(arquivo.read_text(encoding='utf-8')))
    report['divergencias']=[member for row in report.get('divergencias',[]) for member in (row.get('registros_agrupados') or [row])]
    return report


def ler_exclusoes(root:Path,run_id:str)->set[str]:
    file=_overlay(root,run_id)
    if not file.exists():return set()
    payload=json.loads(file.read_text(encoding='utf-8'))
    return {x for x in payload.get('ids',[]) if isinstance(x,str) and DIV_RE.fullmatch(x)}


def preparar_relatorio(root:Path,run_id:str,detalhes=True)->dict:
    report=ler_original(root,run_id,detalhes=detalhes)
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
    from .relevance import preparar
    manual=root/f'relevancia_{run_id}.json'
    resultado=preparar(report,json.loads(manual.read_text(encoding="utf-8")) if manual.exists() else {})
    visiveis={r['id'] for r in original if r.get('id') not in ignored}
    resultado['ids_selecionados']=sorted(ler_selecao(root,run_id)&visiveis)
    return resultado


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
            (root/f'detalhes_filtrado_{rid}.json').unlink(missing_ok=True)
            _overlay(root,rid).unlink(missing_ok=True)
            for name in ('selecoes_', 'recuperacao_', 'detalhes_', 'execucao_', 'relevancia_', 'revisoes_', 'diagnostico_', 'log_', 'checkpoint_'):
                for ext in ('json','txt','log'):
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


def reclassificar(root,run_id,div_id,classe):
    from .relevance import CLASSES
    if classe not in (*CLASSES,'automatica'):raise ValueError('Classificação inválida.')
    original=ler_original(root,run_id)
    if div_id not in {r.get('id') for r in original.get('divergencias',[])}:raise KeyError(div_id)
    path=root/f'relevancia_{run_id}.json'
    overlay=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if classe=='automatica':overlay.pop(div_id,None)
    else:overlay[div_id]=classe
    atomic_json(path,overlay)
    return preparar_relatorio(root,run_id)


def ler_selecao(root,run_id):
    if not valid_run(run_id):raise ValueError('ID inválido.')
    p=root/f'selecoes_{run_id}.json'
    data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    return {i for i in data.get('ids',[]) if isinstance(i,str) and DIV_RE.fullmatch(i)}


def selecionar(root,run_id,div_id,marcada):
    if type(marcada) is not bool:raise ValueError('Informe selecionado como booleano.')
    report=preparar_relatorio(root,run_id)
    grupo=next((r for r in report['divergencias'] if r['id']==div_id),None)
    if grupo:ids=set(grupo.get('ids_agrupados') or [div_id])
    else:ids={div_id} if any(div_id in r.get('ids_agrupados',[]) for r in report['divergencias']) else set()
    if not ids:raise KeyError('DIV não encontrada ou excluída.')
    atuais=ler_selecao(root,run_id)
    atuais=atuais|ids if marcada else atuais-ids
    atomic_json(root/f'selecoes_{run_id}.json',{'ids':sorted(atuais)})
    return sorted(atuais-ler_exclusoes(root,run_id))


def filtrar_divergencias(rows,filtros):
    """Mesma busca da tela, incluindo busca por ID que ignora categoria/lado/tipo."""
    if not isinstance(filtros,dict) or set(filtros)-{'busca','categoria','lado','tipo','revisao','mostrar_todas'}:raise ValueError('Filtros inválidos.')
    for k,v in filtros.items():
        if k=='mostrar_todas':
            if type(v) is not bool:raise ValueError('Filtro mostrar_todas deve ser booleano.')
        elif not isinstance(v,str) or len(v)>500:raise ValueError('Filtro textual inválido.')
    review=filtros.get('revisao','todos')
    if review not in ('todos','pendentes','confirmadas'):raise ValueError('Filtro de revisão inválido.')
    q=filtros.get('busca','').strip().lower();m=re.fullmatch(r'(?:div[\s-]*)?(\d{1,9})',q,re.I)
    busca_id='DIV-'+m[1].zfill(4) if m else None
    out=[]
    for d in rows:
        if review=='pendentes' and d.get('revisao_manual') or review=='confirmadas' and not d.get('revisao_manual'):continue
        if not filtros.get('mostrar_todas',False) and d.get('classificacao') in ('baixa','editorial'):continue
        if busca_id:
            if busca_id==d['id'] or busca_id in d.get('ids_agrupados',[]):out.append(d)
            continue
        if any(filtros.get(k,'todas' if k=='categoria' else 'todos') not in ('todas','todos',d.get(campo)) for k,campo in (('categoria','categoria'),('lado','presente_em'),('tipo','tipo'))):continue
        campos=[json.dumps(d.get('itens_agrupados',[]),ensure_ascii=False,separators=(',',':')),*[d.get(k,'') for k in ('id','elemento','pagina','descricao','local','caminho','posicao','destino_a','destino_b','url_presente','url_comparada')]]
        if not q or any(q in str(v or '').lower() for v in campos):out.append(d)
    return out


def selecionar_lote(root,run_id,acao,filtros=None):
    if acao not in ('todas','filtradas','limpar'):raise ValueError('Ação de seleção inválida.')
    report=preparar_relatorio(root,run_id)
    def membros(rows):
        ids={i for row in rows for i in (row.get('ids_agrupados') or [row['id']])}
        if any(not isinstance(i,str) or not DIV_RE.fullmatch(i) for i in ids):raise ValueError('IDs incompatíveis no relatório.')
        return ids-ler_exclusoes(root,run_id)
    elegiveis=membros(report['divergencias'])
    rows=filtrar_divergencias(report['divergencias'],{} if filtros is None else filtros) if acao=='filtradas' else report['divergencias']
    anteriores=ler_selecao(root,run_id)&elegiveis
    ids=set() if acao=='limpar' else elegiveis if acao=='todas' else anteriores|membros(rows)
    atomic_json(root/f'selecoes_{run_id}.json',{'ids':sorted(ids)})
    return {'ids_selecionados':sorted(ids),'acao':acao,'total_elegivel':len(elegiveis),'grupos_afetados':len(rows)}


def somente_selecionadas(report,ids):
    from copy import deepcopy
    # Exportar uma seleção não deve carregar DOM, grupos ou referências de DIVs
    # fora do escopo. Preserve apenas o contexto comum e os membros escolhidos.
    contexto=('id','versao','site_nome','ambientes','gerado_em','iniciado_em',
        'finalizado_em','duracao_segundos','situacao_analise','estado_execucao',
        'paginas','completo','meta_varredura','modo_varredura','ambiente_desatualizado',
        'retomada_de','site_id','cobertura','motivo_encerramento')
    out={k:deepcopy(report[k]) for k in contexto if k in report};rows=[];seen=set()
    for group in report['divergencias']:
        for r in group.get('registros_agrupados') or [group]:
            if r['id'] in ids and r['id'] not in seen:rows.append(deepcopy(r));seen.add(r['id'])
    out.update(divergencias=rows,registros_originais=rows,escopo_exportacao='Somente DIVs selecionadas',exportacao_selecionada=True,exportacao_completa=False,formato_compacto=False,formato_relatorio=1)
    if 'cobertura' in out:out['cobertura'].pop('representantes_segmento',None)
    metricas=report.get('metricas',{})
    out['metricas']={k:deepcopy(metricas[k]) for k in ('iniciado_em','finalizado_em',
        'duracao_segundos','tempo_total_segundos','tempos_segundos','contagens',
        'nota_tempos','nota_deduplicacao','nota_requisicoes') if k in metricas}
    out['ids_selecionados']=sorted(seen)
    out['revisoes_manuais']={k:deepcopy(v) for k,v in report.get('revisoes_manuais',{}).items() if k in seen}
    out['ocorrencias_brutas']=sum(r.get('ocorrencias_total',1) for r in rows)
    return out
