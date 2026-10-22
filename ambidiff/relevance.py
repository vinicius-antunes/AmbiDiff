"""Priorização conservadora; nunca altera a coleta original nem prova equivalência."""
from copy import deepcopy
from collections import Counter
from urllib.parse import urlsplit, parse_qs

CLASSES=('relevante','baixa','editorial','inconclusivo')
SVG='Código do ícone diferente — revisão visual'

def classificar(row, ambientes=None):
    # Evidência de impacto sempre prevalece sobre sinais técnicos secundários.
    if any(row.get(k) for k in ('impacto_visual_confirmado','falha_funcional','problema_acessibilidade','diferenca_estrutural')):
        return 'relevante','Há evidência explícita de impacto.'
    if row.get('situacao')==SVG and row.get('tipo')=='Ícone' and row.get('assinatura_a') and row.get('assinatura_b'):
        return 'baixa','Somente representação técnica diferente; equivalência visual não verificada.'
    if row.get('tipo') in ('Contexto',) or row.get('situacao')=='inconclusivo':
        return 'inconclusivo','Evidências insuficientes; requer revisão.'
    urls=[row.get(k,'') for k in ('destino_a','destino_b')]
    # Exige endpoint reconhecido nos dois lados, não apenas o nome Messenger.
    if row.get('tipo')=='Redirecionamento' and all(_messenger(u) for u in urls):
        return ('baixa','Mesmo widget externo Messenger e mesmo destinatário.') if urls[0]==urls[1] else ('relevante','Destinatários externos diferentes.')
    if row.get('tipo')=='Redirecionamento' and _share_equivalent(urls,ambientes or {}):
        return 'baixa','Compartilhamento difere somente pela origem dos ambientes.'
    return 'relevante','Diferença preservada para revisão; não determina qual ambiente está correto.'

def _messenger(url):
    try:
        u=urlsplit(url)
        return u.scheme=='https' and u.hostname=='m.me' and bool(u.path.strip('/')) and not u.query and not u.fragment
    except ValueError:return False

def _share_equivalent(urls,ambientes):
    try:
        origins={urlsplit(v).netloc for v in ambientes.values() if isinstance(v,str)}
        parsed=[urlsplit(v) for v in urls]
        if len(origins)<2 or any(u.scheme!='https' or (u.hostname,u.path) not in
            {('www.facebook.com','/sharer/sharer.php'),('twitter.com','/intent/tweet')} for u in parsed):return False
        if parsed[0].netloc!=parsed[1].netloc or parsed[0].path!=parsed[1].path or parsed[0].fragment!=parsed[1].fragment:return False
        qs=[parse_qs(u.query,keep_blank_values=True) for u in parsed]
        key='u' if parsed[0].hostname=='www.facebook.com' else 'url'
        if any(len(q.get(key,[]))!=1 for q in qs):return False
        target=[urlsplit(q[key][0]) for q in qs]
        if any(u.scheme not in ('http','https') or u.netloc not in origins for u in target):return False
        for q,u in zip(qs,target):q[key]=[u._replace(scheme='',netloc='').geturl()]
        return qs[0]==qs[1] and target[0].netloc!=target[1].netloc
    except (ValueError,TypeError):return False

def preparar(dados, manuais=None):
    report=deepcopy(dados)
    rows=[]
    for r in report.get('divergencias',[]):
        rows.extend(deepcopy(r.get('registros_agrupados') or [r]))
    report['registros_originais']=deepcopy(report.get('registros_originais',rows))
    groups={};out=[]
    for row in rows:
        auto,motivo=classificar(row,report.get('ambientes'))
        # Old hand-confirmations must remain visible.
        manual=(manuais or {}).get(row.get('id')) or row.get('classificacao_manual')
        row.update(classificacao_automatica=auto,classificacao=manual or ('relevante' if row.get('revisao_manual')=='confirmada' else auto),motivo_relevancia=motivo)
        if manual:row['classificacao_manual']=manual
        # Consolidate only identical technical fingerprints; retain every member.
        key=(row['classificacao'],row.get('presente_em'),row.get('nao_identificado_em'),row.get('tipo'),row.get('elemento'),row.get('destino_a'),row.get('destino_b'),row.get('assinatura_a'),row.get('assinatura_b'))
        if row['classificacao']=='baixa' and not manual and key in groups:
            group=groups[key]
            group['registros_agrupados'].append(deepcopy(row))
            group['ids_agrupados'].append(row.get('id'))
            group['ocorrencias'].extend(deepcopy(row.get('ocorrencias') or [row]))
            group['ocorrencias_total']=len(group['ocorrencias'])
        else:
            if row['classificacao']=='baixa' and not manual:
                row['registros_agrupados']=[deepcopy(row)];row['ids_agrupados']=[row.get('id')]
                row['ocorrencias']=deepcopy(row.get('ocorrencias') or [row]);groups[key]=row
            out.append(row)
    from .taxonomy import enriquecer,relacionar
    out=enriquecer(out)
    report['grupos_relacionados']=relacionar(out)
    for row in out:row['grupos_relacionados']=[g['id'] for g in report['grupos_relacionados'] if row.get('id') in g['ids']]
    report['divergencias']=out
    report['resumo_relevancia']=dict(Counter(r['classificacao'] for r in out))
    report['editoriais_preservados']=deepcopy(report.get('registros_editoriais',report.get('variacoes_dados',[])))
    report['editoriais_classificados']=enriquecer([dict(x,classificacao='editorial') for x in report['editoriais_preservados']])
    return report
