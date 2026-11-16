"""Política de admissão: observa referências, evita expansão editorial conhecida.

Não decide equivalência, segurança ou ausência. URLs funcionais ficam intactas.
"""
from collections import Counter
import re
from urllib.parse import urlsplit,urlunsplit,parse_qsl,unquote_plus
from .core import normalizar,url_limpa
from .security import url_diagnostica

TRACKING={'utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid','gclid'}
IMPORTANTES=r'áudios|audios|servi[cç]o|consulta|atendimento|institucional|organograma|legisla|portaria|normativ|decreto|resolu|document|/documents/'
EDITORIAL=r'not[ií]cia|editorial|publica[cç][aã]o|hist[oó]ric|galeria|imprensa|/news/'


def identidade(url):
    if not url:return ''
    p=urlsplit(url)
    query='&'.join(part for part in p.query.split('&') if unquote_plus(part.split('=',1)[0]).casefold() not in TRACKING)
    clean=urlunsplit((p.scheme,p.netloc,p.path,query,''))
    valid=urlsplit(url_limpa(urlunsplit((p.scheme,p.netloc,p.path,'',''))))
    return urlunsplit((valid.scheme,valid.netloc,valid.path,query,p.fragment))


def _impressao(url):
    p=urlsplit(url);parts=[];print_query=False
    for raw in p.query.split('&'):
        key,_,value=raw.partition('=')
        if unquote_plus(key).casefold() in ('print','printable','p_p_mode') and unquote_plus(value).casefold() in ('true','1','yes','print'):
            print_query=True
        else:parts.append(raw)
    path=re.sub(r'/print(?=/|$)','',p.path,flags=re.I) or '/'
    if print_query or path!=p.path:return identidade(urlunsplit((p.scheme,p.netloc,path,'&'.join(parts),p.fragment)))
    return ''


class PoliticaURLs:
    def __init__(self,estado=None):
        self.registros={tuple(r['par']):dict(r) for r in (estado or {}).get('registros',[])}
        self.duplicacoes=(estado or {}).get('duplicacoes',0)
        self.preservadas=set((estado or {}).get('preservadas',[]))
    def avaliar(self,par,contexto='',representados=()):
        urls=tuple(par[:2]);label=normalizar(par[2][-1] if par[2] else '')
        context=normalizar(contexto);motivos=[];excecao=False
        for side,url in enumerate(urls):
            if not url:continue
            try:
                p=urlsplit(url);text=normalizar(label+' '+p.path+' '+context)
                importante=bool(re.search(IMPORTANTES,text))
                menu=bool(re.search(r'menu|submenu|cabeçalho|cabecalho|rodapé|rodape|navegação|navegacao|estrutura',context))
                editorial=bool(re.search(EDITORIAL,text))
                params=parse_qsl(p.query,keep_blank_values=True)
                search=bool(re.search(r'/(?:search|busca|pesquisa|resultados-de-busca)(?:/|$)',p.path,re.I) or
                    (re.search(r'buscar|pesquis|search',label) and any(re.search(r'(?:^|_)(q|keywords|search|termo)$',k,re.I) for k,v in params)))
                categoria=''
                if search and not importante:categoria='pesquisa_interna'
                elif importante or menu:excecao=True
                elif editorial:
                    pagination=any(re.search(r'(?:^|_)(cur|page|pagina|start)$',k,re.I) and v.isdecimal() and int(v)>(0 if k.casefold().endswith('start') else 1) for k,v in params)
                    pagination=pagination or bool(re.search(r'/(?:page|pagina)/(?:[2-9]|[1-9]\d+)(?:/|$)',p.path,re.I)) or label in ('próximo','proximo','anterior','next','previous')
                    filters=any(re.search(r'(?:^|_)(ano|year|mes|month|dia|day|categoria|category|categoryid|orderby|sort|ordenacao)$',k,re.I) and v for k,v in params)
                    if pagination:categoria='paginacao_editorial'
                    elif filters:categoria='filtros_editoriais'
                    elif '/w/' in p.path or '/-/' in p.path:categoria='rota_editorial'
                if not categoria and not (importante or menu):
                    original=_impressao(url)
                    if original and side<len(representados) and original in representados[side]:categoria='impressao_redundante'
                motivos.append(categoria)
            except (TypeError,ValueError):motivos.append('') # Dúvida não exclui; validação existente decide.
        excluir=bool(motivos) and all(motivos)
        categoria=motivos[0] if excluir else ''
        anterior=self.registros.get(urls,{})
        if not excluir and excecao:
            self.preservadas.update(u for u in urls if u)
            for registro in self.registros.values():
                if registro['excluido'] and all(not u or u in self.preservadas for u in registro['par']):
                    registro.update(excluido=False,categoria='',excecao_estrutural=True,reconsiderado=True,motivo='Referência posteriormente preservada por contexto estrutural')
        # Preservação posterior revoga a exclusão anterior, sem bloquear admissão.
        if excluir or excecao or anterior:
            self.registros[urls]={'par':list(urls),'categoria':categoria,'excluido':excluir,
                'excecao_estrutural':excecao,'reconsiderado':bool(anterior.get('excluido') and not excluir) or anterior.get('reconsiderado',False),
                'motivo':categoria.replace('_',' ') if excluir else 'Exceção estrutural ou evidência insuficiente para exclusão'}
        return excluir
    def estado(self):return {'registros':list(self.registros.values()),'duplicacoes':self.duplicacoes,'preservadas':sorted(self.preservadas)}
    def resumo(self,detalhado=False):
        rows=list(self.registros.values());excluded=[r for r in rows if r['excluido']]
        por_categoria={}
        for r in excluded:
            por_categoria.setdefault(r['categoria'],set()).update(u for u in r['par'] if u and u not in self.preservadas)
        result={'urls_excluidas_por_categoria':{k:len(v) for k,v in por_categoria.items()},'pares_excluidos':len(excluded),'urls_excluidas':len({u for r in excluded for u in r['par'] if u and u not in self.preservadas}),
            'excluidas_por_categoria':dict(Counter(r['categoria'] for r in excluded)),
            'duplicacoes_evitadas':self.duplicacoes,'excecoes_estruturais':sum(r['excecao_estrutural'] for r in rows),
            'exclusoes_reconsideradas':sum(r.get('reconsiderado',False) for r in rows),
            'nota':'Exclusão intencional de navegação; referência na origem continua comparada. Não comprova equivalência nem cobertura integral.'}
        if detalhado:result['referencias']=[{**{k:v for k,v in r.items() if k!='par'},'urls':[url_diagnostica(u) if u else '' for u in r['par']]} for r in rows]
        return result
