"""Semântica de paginação e finalidade do destino, sem herdar a origem inteira."""
import re
import unicodedata
from urllib.parse import urlsplit,parse_qsl,urlunsplit


def texto(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value).casefold()) if not unicodedata.combining(c))


def finalidade(url,rotulo='',contexto=''):
    p=urlsplit(url);path=texto(p.path);label=texto(rotulo);context=texto(contexto)
    # Assunto de uma notícia não transforma a notícia em serviço/legislação.
    rota_editorial=bool(re.search(r'/(noticias?|news|videos?|audios?|galerias?|fotos?|fotografias?|radio|tv|arquivo-editorial|historicos?)(/|$)',path))
    editorial=bool(rota_editorial or re.search(r'noticia|editorial|publicacao|imprensa|galeria|video|audio|fotografia|\bfotos?\b|\bradio\b|\btv\b',label+' '+context))
    documental=bool(re.search(r'/(documents|documentos|legislacao|resolucoes|portarias|normativos|transparencia)(/|$)|\.(pdf|docx?|xlsx?|odt)$',path) or (not rota_editorial and re.match(r'^(portarias?|resolucoes|legislacao|documentos?|normativos?)(\b)',label)) or (not rota_editorial and re.match(r'^(legislacao|resolucoes|documentos|portarias|listagem administrativa)\b',context)))
    servico=bool((not rota_editorial and re.fullmatch(r'servico ao cidadao|consultar processo|consulta processual',label)) or re.search(r'/(servicos|consulta|atendimento|sistemas)(/|$)',path) or (not editorial and (re.match(r'^(servico|consultar processo|consulta processual|atendimento)\b',label) or re.match(r'^servicos?\b',context))))
    institucional=bool(re.search(r'/(institucional|organograma|contatos|estrutura-organizacional)(/|$)',path) or ('integridade' in path and re.search(r'integridade|campanha',label)) or (not editorial and re.match(r'^(institucional|organograma|contatos administrativos)\b',label)))
    return {'categoria':'documental' if documental else 'servico' if servico else 'institucional' if institucional else 'editorial' if editorial else 'indeterminada','editorial':editorial,'estrutural':documental or servico or institucional,
            'motivo_estrutural':'finalidade documental/legislativa' if documental else 'serviço público' if servico else 'conteúdo institucional' if institucional else ''}


def paginacao(url):
    p=urlsplit(url);posterior=False;iniciais=[];indices=[]
    for k,v in parse_qsl(p.query,keep_blank_values=True):
        m=re.search(r'(?:^|_)(cur|page|pagina|start|offset)$',k,re.I)
        if not m or not v.isdecimal():continue
        threshold=0 if m[1].lower() in ('start','offset') else 1
        indices.append((k,int(v)))
        if int(v)>threshold:posterior=True
        elif int(v)==threshold:iniciais.append(k)
    m=re.search(r'/(?:page|pagina)/(\d+)(?:/|$)',p.path,re.I)
    if m and int(m[1])>1:posterior=True
    return {'posterior':posterior,'iniciais':iniciais,'indices':indices}


def primeira_equivalente(url,rotulo='',contexto=''):
    if not finalidade(url,rotulo,contexto)['editorial']:return url
    info=paginacao(url)
    if info['posterior'] or not info['iniciais']:return url
    p=urlsplit(url)
    from urllib.parse import unquote_plus
    raw='&'.join(x for x in p.query.split('&') if unquote_plus(x.split('=',1)[0]) not in info['iniciais'])
    return urlunsplit((p.scheme,p.netloc,p.path,raw,p.fragment))
