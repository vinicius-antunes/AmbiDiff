"""Identificação conservadora de conteúdo editorial e sinais de bases defasadas.

A existência de uma base antiga não apaga divergências estruturais/funcionais.
Nenhuma classificação aqui implica erro de PRD ou DES.
"""
from __future__ import annotations
from collections import defaultdict
from urllib.parse import urlsplit
import re
from .core import normalizar, titulo_normalizado

DATA_EDITORIAL = re.compile(r'\b(?:\d{1,2}[ /-])?(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-zç]*\b|\b\d{1,2}[/-]\d{1,2}[/-]20\d{2}\b', re.I)
ROTA_EDITORIAL = re.compile(r'/(?:w/|noticias(?:/|$)|notícias(?:/|$)|blog(?:/|$)|posts?/|imprensa(?:/|$))', re.I)


def item_editorial(item, pagina=None) -> bool:
    # Preferir evidência contextual vinda do DOM. Nunca deduzir apenas por diferença de data.
    if getattr(item,'natureza','') == 'editorial':return True
    if getattr(item,'natureza','') == 'estrutura':return False
    # Compatibilidade com páginas fabricadas sem os novos campos.
    if pagina and ROTA_EDITORIAL.search(urlsplit(pagina.url).path):
        return bool(getattr(item,'tipo','') in ('Texto','Imagem') and
                    getattr(item,'posicao','') not in ('Menu de navegação','Cabeçalho','Rodapé'))
    return False


def separar_editoriais(comps, pa, pb, itens_a, itens_b, nomes, defasado):
    """Agrupa diferenças editoriais por evidência DOM, mesmo sem defasagem declarada.

    Preserva a DIV quando não se identifica uma área editorial correspondente
    no outro ambiente. A declaração de defasagem fornece apenas contexto.
    """
    editoriais_a=[i for i in itens_a if item_editorial(i,pa)]
    editoriais_b=[i for i in itens_b if item_editorial(i,pb)]
    ids_a={(i.tipo,normalizar(i.chave)) for i in editoriais_a}
    ids_b={(i.tipo,normalizar(i.chave)) for i in editoriais_b}
    locais_a={normalizar(i.local) for i in editoriais_a}
    locais_b={normalizar(i.local) for i in editoriais_b}
    # Artigos correspondentes podem ter títulos diferentes como 'local'.
    # A rota editorial e conteúdo editorial nos dois lados constituem contexto
    # adicional; isto nunca dispensa comparar menus/controles estruturais.
    artigos_pareados=bool(
        editoriais_a and editoriais_b and
        ROTA_EDITORIAL.search(urlsplit(pa.url).path) and
        ROTA_EDITORIAL.search(urlsplit(pb.url).path))
    regs=[];data=[]
    for d in comps:
        k=(d.get('tipo',''),normalizar(d.get('elemento','')))
        src = ids_a if d.get('presente_em')==nomes[0] else ids_b
        editorial=(k in src or
            (d.get('tipo')=='Texto' and 'texto_a' in d and
             (('Texto',normalizar(d['texto_a'])) in ids_a or
              ('Texto',normalizar(d.get('texto_b',''))) in ids_b)))
        candidatos=[i for i in (itens_a if d.get('presente_em')==nomes[0] else itens_b) if normalizar(i.nome)==normalizar(d.get('elemento','')) or i.nome==d.get('texto_a')]
        if d.get('local'):candidatos=[i for i in candidatos if normalizar(i.local)==normalizar(d['local'])]
        if d.get('posicao'):candidatos=[i for i in candidatos if i.posicao==d['posicao']]
        editorial=editorial and bool(candidatos) and all(item_editorial(i,pa if d.get('presente_em')==nomes[0] else pb) for i in candidatos)
        publicacao=d.get('tipo')=='Opção' and any(ROTA_EDITORIAL.search(urlsplit(i.destino).path) for i in candidatos if i.destino)
        # Uma lista ou seção editorial totalmente ausente pode ser um problema
        # estrutural: nesse caso não deslocar seus itens para o grupo informativo.
        locais_opostos=locais_b if d.get('presente_em')==nomes[0] else locais_a
        area_correspondente=bool(candidatos) and (normalizar(candidatos[0].local) in locais_opostos or artigos_pareados)
        # Em uma base explicitamente defasada, preservar o agrupamento editorial
        # legado (inclusive avisos editoriais exclusivos), coberto por regressões.
        if editorial and (defasado or area_correspondente) and (d.get('tipo') in ('Texto','Imagem') or publicacao):
            motivo=('Contexto editorial observado; base desatualizada declarada pelo usuário. '
                    'A causa da diferença não foi comprovada.' if defasado else
                    'Contexto editorial observado nos dois ambientes. Diferença de publicação '
                    'possível mesmo sem base declarada desatualizada; causa não comprovada.')
            data.append(dict(d,bloco_editorial=candidatos[0].entidade if candidatos else d.get('local',''),
                motivo_editorial=motivo))
        else:regs.append(d)
    return regs,data


def agrupar_variacoes(dados, desatualizado):
    """Produz grupos informativos por área/portal, não DIVs e não defeitos."""
    agrupados=defaultdict(list)
    for item in dados:
        pagina=item.get('url_presente') or ''
        path=urlsplit(pagina).path or '/'
        # A mesma lista pode estar na home e /inicio, evitar grupo por cada notícia.
        categoria='Notícias e publicações' if path=='/' or ROTA_EDITORIAL.search(path) else 'Conteúdo editorial e imagens'
        bloco=item.get('bloco_editorial','')
        chave=(categoria,item.get('url_presente',''),item.get('local',''),bloco,item.get('presente_em','')) if bloco.startswith('@aviso:') else (categoria,'',item.get('local',''),'','')
        agrupados[chave].append(item)
    resumo=[]
    for chave,rows in agrupados.items():
        titulo=chave[0]
        unique=[];seen=set()
        for x in rows:
            key=(x.get('tipo'),normalizar(x.get('elemento')),x.get('presente_em'))
            if key not in seen:
                seen.add(key);unique.append(x)
        resumo.append({'categoria':titulo,'ambiente_desatualizado':desatualizado,
             'quantidade_ocorrencias':len(rows),'quantidade_itens':len(unique),
             'motivo':'Possível variação editorial entre ambientes; não comprova defasagem nem defeito. Revisão recomendada.',
             'registros':unique,'local':chave[2],'pagina':chave[1],'ambiente':chave[4],
             'exemplos':[{'tipo':v.get('tipo'),'elemento':v.get('elemento'),
                         'pagina':v.get('url_presente'),'ambiente':v.get('presente_em')} for v in unique[:18]]})
    return resumo


def sinais_extraidos(paginas,nome):
    encontrados=[];visto=set()
    for p in paginas.values():
        for s in p.coleta.get('avisos_ambiente',[]):
            key=normalizar(s)
            if key in visto:continue
            visto.add(key)
            encontrados.append({'ambiente':nome,'pagina':p.url,'texto':s[:340],
                 'interpretacao':'Possível aviso sobre ambiente ou base de dados; requer confirmação.'})
    return encontrados[:12]
