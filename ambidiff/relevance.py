"""Priorização conservadora; nunca altera a coleta original nem prova equivalência."""
from copy import deepcopy
from collections import Counter
from urllib.parse import urlsplit, parse_qs

CLASSES=('relevante','baixa','editorial','inconclusivo')
SVG='Código do ícone diferente — revisão visual'

def classificar(row, ambientes=None):
    if row.get('verificacao_limitada'):return 'inconclusivo','Componente com avaliação limitada pela política de segurança; diferença preservada sem defeito comprovado.'
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
    if row.get('tipo') in ('Redirecionamento','Destino verificado') and row.get('situacao')!='LINK_INACESSIVEL' and _share_equivalent(urls,ambientes or {}):
        return 'baixa','Compartilhamento difere somente pela origem dos ambientes.'
    return 'relevante','Diferença preservada para revisão; não determina qual ambiente está correto.'

def _messenger(url):
    try:
        u=urlsplit(url)
        return u.scheme=='https' and u.hostname=='m.me' and bool(u.path.strip('/')) and not u.query and not u.fragment
    except ValueError:return False

def evidencia_compartilhamento(urls,ambientes):
    """Prova sintática: endpoint conhecido e destino no ambiente de cada lado."""
    try:
        from .core import url_limpa
        from .paired import link_equivalente
        bases=list(ambientes.values())
        if len(bases)!=2 or len(urls)!=2:return None
        for v in urls:url_limpa(v)
        parsed=[urlsplit(v) for v in urls]
        endpoints={('www.facebook.com','/sharer/sharer.php'):'u',
            ('facebook.com','/sharer/sharer.php'):'u',('twitter.com','/intent/tweet'):'url',
            ('www.twitter.com','/intent/tweet'):'url',('x.com','/intent/tweet'):'url'}
        chave=(parsed[0].netloc,parsed[0].path)
        if chave not in endpoints or any(p.scheme!='https' or p.fragment or (p.netloc,p.path)!=chave for p in parsed):return None
        qs=[parse_qs(p.query,keep_blank_values=True) for p in parsed];key=endpoints[chave]
        if any(len(q.get(key,[]))!=1 for q in qs):return None
        targets=[q[key][0] for q in qs]
        for target in targets:url_limpa(target)
        for target,base in zip(targets,bases):
            t,b=urlsplit(target),urlsplit(url_limpa(base))
            if (t.scheme,t.netloc)!=(b.scheme,b.netloc):return None
            root=b.path.rstrip('/')
            if root and t.path!=root and not t.path.startswith(root+'/'):return None
        # Não descarta queries nem transforma %2F em separador de caminho.
        import re
        def unreserved(u):
            return re.sub(r'%([0-9a-fA-F]{2})',lambda m:chr(int(m[1],16)) if chr(int(m[1],16)) in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~' else '%'+m[1].upper(),u)
        if not link_equivalente(*map(unreserved,targets),*bases):return None
        for q in qs:q.pop(key)
        if qs[0]!=qs[1]:return None
        return {'endpoint':parsed[0].netloc+parsed[0].path,'destino_a':targets[0],'destino_b':targets[1],
            'evidencias':['endpoint conhecido','origem correta em cada ambiente','caminho e parâmetros correspondentes'],
            'limite':'Equivalência de referência; disponibilidade, clique e intenção editorial não comprovados.'}
    except (ValueError,TypeError,AttributeError):return None


def _share_equivalent(urls,ambientes):
    return evidencia_compartilhamento(urls,ambientes) is not None


def preparar(dados, manuais=None):
    report=deepcopy(dados)
    rows=[]
    for r in report.get('divergencias',[]):
        rows.extend(deepcopy(r.get('registros_agrupados') or [r]))
    report['registros_originais']=deepcopy(report.get('registros_originais',rows))
    groups={};out=[];shares=[]
    for row in rows:
        auto,motivo=classificar(row,report.get('ambientes'))
        if auto=='baixa':
            ev=evidencia_compartilhamento([row.get('destino_a',''),row.get('destino_b','')],report.get('ambientes',{}))
            if ev:shares.append(dict(ev,id=row.get('id'),ocorrencias=row.get('ocorrencias_total',1)))
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
    from .sections import agrupar_documentos,agrupar_relacionados
    out=agrupar_documentos(agrupar_relacionados(enriquecer(out)))
    report['grupos_relacionados']=relacionar(out)
    for row in out:row['grupos_relacionados']=[g['id'] for g in report['grupos_relacionados'] if row.get('id') in g['ids']]
    report['equivalencias_compartilhamento']=shares
    report['resumo_compartilhamento']={'registros':len(shares),'ocorrencias':sum(x['ocorrencias'] for x in shares),'grupos':sum(any(x['id'] in (r.get('ids_agrupados') or [r.get('id')]) for x in shares) for r in out)}
    report['divergencias']=out
    report['resumo_relevancia']=dict(Counter(r['classificacao'] for r in out))
    report['editoriais_preservados']=deepcopy(report.get('registros_editoriais',report.get('variacoes_dados',[])))
    report['editoriais_classificados']=enriquecer([dict(x,classificacao='editorial') for x in report['editoriais_preservados']])
    return report
