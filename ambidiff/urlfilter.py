"""Política de admissão: observa referências, evita expansão editorial conhecida.

Não decide equivalência, segurança ou ausência. URLs funcionais ficam intactas.
"""
from collections import Counter
import re
from urllib.parse import urlsplit,urlunsplit,parse_qsl,unquote_plus
from .core import normalizar,url_limpa
from .security import url_diagnostica
from .pagination import finalidade,paginacao,primeira_equivalente

TRACKING={'utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid','gclid'}


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


def _indices_seguros(url):
    try:
        return [{'parametro':k.rsplit('_',1)[-1].lower(),'valor':v} for k,v in paginacao(url)['indices']]
    except (TypeError,ValueError):return []


class PoliticaURLs:
    def __init__(self,estado=None):
        self.registros={tuple(r['par']):dict(r) for r in (estado or {}).get('registros',[])}
        self.duplicacoes=(estado or {}).get('duplicacoes',0)
        self.preservadas=set((estado or {}).get('preservadas',[])) if (estado or {}).get('versao')==2 else set()
        self.eventos=Counter((estado or {}).get('eventos',{}))
    def avaliar(self,par,contexto='',representados=()):
        urls=tuple(par[:2]);label=normalizar(par[2][-1] if par[2] else '')
        self.eventos['tentativas_admissao']+=1
        context=normalizar(contexto);motivos=[];excecao=False;justificativas=[]
        for side,url in enumerate(urls):
            if not url:continue
            try:
                p=urlsplit(url)
                uso=finalidade(url,label,context);pg=paginacao(url)
                importante=uso['estrutural'];editorial=uso['editorial']
                if importante:justificativas.append(uso['motivo_estrutural']+('; paginação relevante' if pg['posterior'] else ''))
                params=parse_qsl(p.query,keep_blank_values=True)
                search=bool(re.search(r'/(?:search|busca|pesquisa|resultados-de-busca)(?:/|$)',p.path,re.I) or
                    (re.search(r'buscar|pesquis|search',label) and any(re.search(r'(?:^|_)(q|keywords|search|termo)$',k,re.I) for k,v in params)))
                categoria=''
                if pg['posterior'] and editorial and not importante:categoria='paginacao_editorial'
                elif search and not importante:categoria='pesquisa_interna'
                elif importante:excecao=True
                elif editorial:
                    pagination=pg['posterior']
                    delta_isolado=any(re.search(r'(?:^|_)delta$',k,re.I) for k,v in params) and not pg['indices']
                    pagination=pagination or (not pg['indices'] and not delta_isolado and 'pagina' in context and label in ('próximo','proximo','anterior','next','previous'))
                    filters=any(re.search(r'(?:^|_)(ano|year|mes|month|dia|day|categoria|category|categoryid|orderby|sort|ordenacao)$',k,re.I) and v for k,v in params)
                    if pagination:categoria='paginacao_editorial'
                    elif filters:categoria='filtros_editoriais'
                    elif ('/w/' in p.path or '/-/' in p.path) and label not in ('áudios','audios','vídeos','videos','galerias','notícias','noticias'):categoria='rota_editorial'
                    elif (not urls[0] or not urls[1]) and re.search(r'/(noticias?|news|videos?|audios?|galerias?)/[^/]+',p.path,re.I):categoria='editorial_sem_contraparte'
                if not categoria and not (importante):
                    original=_impressao(url)
                    if original and side<len(representados) and original in representados[side]:categoria='impressao_redundante'
                if not categoria and not importante and 'origem_unilateral' in context:categoria='ramificacao_unilateral_nao_expandida'
                motivos.append(categoria)
            except (TypeError,ValueError):motivos.append('') # Dúvida não exclui; validação existente decide.
        excluir=bool(motivos) and all(motivos)
        categoria=motivos[0] if excluir else ''
        self.eventos['exclusoes' if excluir else 'preservacoes']+=1
        anterior=self.registros.get(urls,{})
        if not excluir and excecao:
            self.preservadas.update(u for u in urls if u)
            for registro in self.registros.values():
                if registro['excluido'] and all(not u or u in self.preservadas for u in registro['par']):
                    registro.update(excluido=False,categoria='',excecao_estrutural=True,reconsiderado=True,motivo='Referência posteriormente preservada por contexto estrutural')
        # Preservação posterior revoga a exclusão anterior, sem bloquear admissão.
        self.registros[urls]={'versao_politica':2,'par':list(urls),'categoria':categoria,'excluido':excluir,
                'excecao_estrutural':excecao,'reconsiderado':bool(anterior.get('excluido') and not excluir) or anterior.get('reconsiderado',False),
                'motivo':categoria.replace('_',' ') if excluir else '; '.join(sorted(set(justificativas))) or 'Natureza ambígua; análise preservada sem presumir finalidade estrutural'}
        return excluir
    def estado(self):return {'versao':2,'registros':list(self.registros.values()),'duplicacoes':self.duplicacoes,'preservadas':sorted(self.preservadas),'eventos':dict(self.eventos)}
    def resumo(self,detalhado=False):
        rows=list(self.registros.values());excluded=[r for r in rows if r['excluido']]
        por_categoria={}
        for r in excluded:
            por_categoria.setdefault(r['categoria'],set()).update(u for u in r['par'] if u and u not in self.preservadas)
        result={'eventos':dict(self.eventos),'amostras_limitadas':100,'urls_excluidas_por_categoria':{k:len(v) for k,v in por_categoria.items()},'pares_excluidos':len(excluded),'urls_excluidas':len({u for r in excluded for u in r['par'] if u and u not in self.preservadas}),
            'excluidas_por_categoria':dict(Counter(r['categoria'] for r in excluded)),
            'duplicacoes_evitadas':self.duplicacoes,'excecoes_legadas_sem_revalidacao':sum(r['excecao_estrutural'] and r.get('versao_politica',1)!=2 for r in rows),'excecoes_estruturais':sum(r['excecao_estrutural'] and r.get('versao_politica',1)==2 for r in rows),
            'exclusoes_reconsideradas':sum(r.get('reconsiderado',False) for r in rows),
            'nota':'Exclusão intencional de navegação; referência na origem continua comparada. Não comprova equivalência nem cobertura integral.'}
        if detalhado:result['referencias']=[{**{k:v for k,v in r.items() if k!='par'},'paginacao':[_indices_seguros(u) if u else [] for u in r['par']],'urls':[url_diagnostica(u) if u else '' for u in r['par']]} for r in rows[:100]]
        result['amostras_omitidas']=max(0,len(rows)-100)
        result['exclusivas_descartadas_por_categoria']=dict(Counter(r['categoria'] for r in rows if r['excluido'] and not all(r['par'])))
        result['exclusivas_descartadas']=sum(r['excluido'] and not all(r['par']) for r in rows)
        result['paginacoes_relevantes_preservadas']=sum(not r['excluido'] and 'paginação relevante' in r['motivo'] for r in rows)
        result['paginacoes_documentais_preservadas']=sum(not r['excluido'] and 'paginação relevante' in r['motivo'] and 'finalidade documental/legislativa' in r['motivo'] for r in rows)
        result['rotas_w_excluidas']=len({u for r in excluded for u in r['par'] if '/w/' in u})
        result['rotas_traco_excluidas']=len({u for r in excluded for u in r['par'] if '/-/' in u})
        return result
