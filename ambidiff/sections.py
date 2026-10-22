"""Ausência contextual e visão resumida de documentos; preserva registros individuais."""
from copy import deepcopy
from collections import defaultdict
from .core import normalizar,_registro

GENERICO={'','conteudo principal','conteúdo principal','pagina','página','pagina inicial','página inicial'}

def comparar_secoes(comps,pa,pb,nome_a,nome_b):
    novos=[];substituidos=set()
    for src,dst,origem,outro in ((pa,pb,nome_a,nome_b),(pb,pa,nome_b,nome_a)):
        for item in src.itens:
            local=normalizar(item.local)
            if item.imagem_link or item.tipo not in ('Opção','Documento') or item.natureza=='editorial' or local in GENERICO:continue
            # Sem seção observável de origem, não fabricar escopo.
            equivalentes=[i for i in dst.itens if i.tipo==item.tipo and normalizar(i.nome)==normalizar(item.nome) and normalizar(i.local)==local]
            if equivalentes:continue
            renomeado=any(d.get('tipo')=='Rótulo' and d.get('local')==item.local and item.nome in (d.get('texto_a'),d.get('texto_b')) for d in comps)
            if renomeado:continue
            row=_registro(item,src,dst,origem,outro)
            row.update(escopo='Seção correspondente; não é ausência global',referencia=item.destino,
                       tags=['OPCAO_AUSENTE','OPCAO_AUSENTE_NA_SECAO'] if item.tipo=='Opção' else ['DOCUMENTO_DIVERGENTE'],
                       tag_tecnica='OPCAO_AUSENTE' if item.tipo=='Opção' else 'DOCUMENTO_DIVERGENTE',escopo_tag='OPCAO_AUSENTE_NA_SECAO')
            outras=[i.local for i in dst.itens if i.tipo==item.tipo and normalizar(i.nome)==normalizar(item.nome)]
            if outras:row['realocado_possivelmente_para']=sorted(set(outras))
            row['descricao']+=' Escopo: não identificado nesta seção; não comprova ausência em todo o portal.'
            novos.append(row);substituidos.add((item.tipo,item.nome,origem))
    # Textos informativos: associação apenas com contexto e seletor únicos observados.
    usados=set()
    for ia in pa.itens:
        if ia.tipo!='Texto' or not ia.seletor or normalizar(ia.local) in GENERICO:continue
        candidates=[ib for ib in pb.itens if ib.tipo=='Texto' and ib.seletor==ia.seletor and normalizar(ib.local)==normalizar(ia.local)]
        if len(candidates)!=1 or sum(i.tipo=='Texto' and i.seletor==ia.seletor and normalizar(i.local)==normalizar(ia.local) for i in pa.itens)!=1:continue
        ib=candidates[0]
        if ia.nome==ib.nome or (ia.nome,ib.nome) in usados:continue
        da=[d for d in comps if d.get('tipo')=='Texto' and d.get('elemento')==ia.nome and d.get('presente_em')==nome_a and not d.get('texto_b')]
        db=[d for d in comps if d.get('tipo')=='Texto' and d.get('elemento')==ib.nome and d.get('presente_em')==nome_b and not d.get('texto_b')]
        if len(da)!=1 or len(db)!=1:continue
        row=_registro(ia,pa,pb,nome_a,nome_b)
        row.update(texto_a=ia.nome,texto_b=ib.nome,situacao='Informação diferente na seção correspondente',possivel_diferenca_dados=True,
                   descricao='Valores diferentes em texto informativo associado por seção, seletor único e tipo. Pode haver diferença de atualização; causa não confirmada e nenhum ambiente é presumido correto.')
        novos.append(row);usados.add((ia.nome,ib.nome))
        substituidos.update({('Texto',ia.nome,nome_a),('Texto',ib.nome,nome_b)})
    return [d for d in comps if (d.get('tipo'),d.get('elemento'),d.get('presente_em')) not in substituidos]+novos

def agrupar_documentos(rows):
    buckets=defaultdict(list);out=[]
    for row in rows:
        if row.get('tipo')!='Documento' or row.get('destino_a') or not row.get('local') or normalizar(row['local']) in GENERICO:
            out.append(row);continue
        key=(row.get('local'),row.get('presente_em'),row.get('nao_identificado_em'),row.get('classificacao'),row.get('classificacao_manual'),row.get('revisao_manual'),
             tuple(sorted((o.get('url_presente',''),o.get('url_comparada','')) for o in row.get('ocorrencias') or [row])))
        buckets[key].append(row)
    for group in buckets.values():
        if len(group)<2:out.extend(group);continue
        principal=deepcopy(group[0]);principal.update(tipo='Documentos da seção',categoria='Documentos',elemento='Documentos não identificados na seção '+group[0]['local'],
            descricao='Itens documentais sem correspondência nesta seção. Referências preservadas; não foram comparados conteúdos de arquivos.',
            itens_agrupados=deepcopy(group),registros_agrupados=deepcopy(group),ids_agrupados=[r['id'] for r in group],
            quantidade_itens=len(group))
        out.append(principal)
    return out


def agrupar_relacionados(rows):
    """Somente texto/controle normativo na mesma seção, escopo e revisão."""
    import re
    groups=defaultdict(list);resto=[]
    for row in rows:
        texto=' '.join(str(row.get(k,'')) for k in ('elemento','texto_a','texto_b'))
        norm=re.search(r'\b(portaria|decreto|lei|resolu[çc][ãa]o)\s*(?:n[ºo°.]?\s*)?\d',texto,re.I)
        if not norm or row.get('tipo') not in ('Texto','Opção','Rótulo','Documento') or normalizar(row.get('local','')) in GENERICO:
            resto.append(row);continue
        key=(normalizar(row.get('local','')),tuple(sorted((row.get('url_presente',''),row.get('url_comparada','')))),norm[1].casefold(),
             row.get('classificacao'),row.get('classificacao_manual'),row.get('revisao_manual'))
        groups[key].append(row)
    for group in groups.values():
        # Exige evidência de texto e controle; não agrega textos independentes.
        if len(group)<2 or not any(x.get('tipo')=='Texto' for x in group) or not any(x.get('tipo') in ('Opção','Rótulo','Documento') for x in group):
            resto.extend(group);continue
        p=deepcopy(group[0]);p.update(tipo='Referências normativas da seção',elemento='Referências normativas diferentes em '+group[0]['local'],
            descricao='Textos e controles normativos relacionados na mesma seção. Todos os valores e destinos permanecem nos detalhes; causa e correção não foram presumidas.',
            registros_agrupados=deepcopy(group),itens_agrupados=deepcopy(group),ids_agrupados=[x['id'] for x in group],quantidade_itens=len(group))
        resto.append(p)
    return resto
