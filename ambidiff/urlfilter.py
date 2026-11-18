"""Política de admissão: observa referências, evita expansão editorial conhecida.

Não decide equivalência, segurança ou ausência. URLs funcionais ficam intactas.
"""
from collections import Counter
import re
from urllib.parse import urlsplit,urlunsplit,parse_qsl,unquote_plus
from .core import normalizar,url_limpa
from .security import url_diagnostica
from .pagination import finalidade,paginacao,primeira_equivalente
from .portal import EscopoPortal

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
    def __init__(self,estado=None,bases=()):
        self.registros={tuple(r['par']):dict(r) for r in (estado or {}).get('registros',[])}
        self.duplicacoes=(estado or {}).get('duplicacoes',0)
        self.preservadas=set((estado or {}).get('preservadas',[])) if (estado or {}).get('versao')==2 else set()
        self.eventos=Counter((estado or {}).get('eventos',{}))
        self.escopos=[EscopoPortal(b,((estado or {}).get('portais',[])+[{},{}])[i]) for i,b in enumerate(bases)]
        self.evidencias=[dict(x) for x in (estado or {}).get('finalidades_observadas',[{},{}])]
    def observar(self,lado,pagina,destino,raiz=False):
        if lado<len(self.escopos):self.escopos[lado].observar(destino,pagina.coleta.get('portal',{}),raiz)
        if pagina.coleta.get('finalidade_pagina')=='listagem_editorial':self.evidencias[lado][destino]='listagem_editorial'
        for item in pagina.itens:
            if item.destino and finalidade(item.destino,item.nome,item.local)['categoria']=='servico':
                self.evidencias[lado][item.destino]='servico'
                if lado<len(self.escopos) and self.escopos[lado].outro(item.destino):
                    self.escopos[lado].compartilhados.add(item.destino)
        for ref in pagina.coleta.get('referencias_finalidade',[]):
            if ref.get('finalidade') in ('listagem_editorial','editorial_individual','documental','servico'):
                if self.evidencias[lado].get(ref['url']) not in ('documental','servico'):
                    self.evidencias[lado][ref['url']]=ref['finalidade']
    def avaliar(self,par,contexto='',representados=(),fase='admissao'):
        urls=tuple(par[:2]);label=normalizar(par[2][-1] if par[2] else '')
        self.eventos['tentativas_admissao']+=1
        context=normalizar(contexto);motivos=[];finalidades=[];excecao=False;justificativas=[]
        for side,url in enumerate(urls):
            if not url:continue
            try:
                p=urlsplit(url)
                prova=self.evidencias[side].get(url,'')
                uso=finalidade(url,label,context if not prova else ('Documentos' if prova=='documental' else 'Serviços' if prova=='servico' else context+' editorial'))
                pg=paginacao(url)
                importante=uso['estrutural'];editorial=uso['editorial']
                outro=side<len(self.escopos) and self.escopos[side].outro(url)
                # Serviço compartilhado observado: autoriza apenas a referência
                # exata, nunca o portal inteiro nem todos os seus descendentes.
                if outro and uso['categoria']=='servico':
                    self.escopos[side].compartilhados.add(url);outro=False
                finalidades.append('outro_portal' if outro else uso['categoria'])
                if importante:justificativas.append(uso['motivo_estrutural']+('; referência compartilhada exata' if side<len(self.escopos) and url in self.escopos[side].compartilhados else '')+('; paginação relevante' if pg['posterior'] else ''))
                params=parse_qsl(p.query,keep_blank_values=True)
                search=bool(re.search(r'/(?:search|busca|pesquisa|resultados-de-busca)(?:/|$)',p.path,re.I) or
                    (re.search(r'buscar|pesquis|search',label) and any(re.search(r'(?:^|_)(q|keywords|search|termo)$',k,re.I) for k,v in params)))
                categoria=''
                if outro:categoria='outro_portal'
                elif pg['posterior'] and editorial and not importante:categoria='paginacao_editorial'
                elif prova=='editorial_individual' and not importante:categoria='conteudo_editorial_individual'
                elif search and not importante:categoria='pesquisa_interna'
                elif importante:excecao=True
                elif editorial:
                    pagination=pg['posterior']
                    delta_isolado=any(re.search(r'(?:^|_)delta$',k,re.I) for k,v in params) and not pg['indices']
                    pagination=pagination or (not pg['indices'] and not delta_isolado and 'pagina' in context and label in ('próximo','proximo','anterior','next','previous'))
                    filters=any(re.search(r'(?:^|_)(ano|year|mes|month|dia|day|categoria|category|categoryid|orderby|sort|ordenacao)$',k,re.I) and v for k,v in params)
                    if pagination:categoria='paginacao_editorial'
                    elif filters:categoria='filtros_editoriais'
                    elif ('/w/' in p.path or '/-/' in p.path) and prova!='listagem_editorial' and label not in ('áudios','audios','vídeos','videos','galerias','notícias','noticias','fotos','fotografias','rádio','radio','tv','arquivo editorial'):categoria='rota_editorial'
                    elif (not urls[0] or not urls[1]) and re.search(r'/(noticias?|news|videos?|audios?|galerias?|fotos?|fotografias?|radio|tv)/[^/]+',p.path,re.I):categoria='editorial_sem_contraparte'
                if not categoria and not (importante):
                    original=_impressao(url)
                    if original and side<len(representados) and original in representados[side]:categoria='impressao_redundante'
                if not categoria and not importante and 'origem_unilateral' in context:categoria='ramificacao_unilateral_nao_expandida'
                motivos.append(categoria)
            except (TypeError,ValueError):
                motivos.append('');finalidades.append('indeterminada') # Dúvida não exclui.
        excluir=bool(motivos) and (all(motivos) or 'outro_portal' in motivos)
        categoria=('outro_portal' if 'outro_portal' in motivos else motivos[0]) if excluir else ''
        self.eventos['exclusoes' if excluir else 'preservacoes']+=1
        anterior=self.registros.get(urls,{})
        if not excluir and excecao:
            self.preservadas.update(u for u in urls if u)
            for registro in self.registros.values():
                if registro['excluido'] and registro['categoria']!='outro_portal' and all(not u or u in self.preservadas for u in registro['par']):
                    registro.update(excluido=False,categoria='',excecao_estrutural=True,reconsiderado=True,motivo='Referência posteriormente preservada por contexto estrutural')
        # Preservação posterior revoga a exclusão anterior, sem bloquear admissão.
        self.registros[urls]={'versao_politica':2,'par':list(urls),'categoria':categoria,'excluido':excluir,
                'fases':sorted(set(anterior.get('fases',[]))|{fase}),
                'finalidades':finalidades,
                'excecao_estrutural':excecao and not excluir,'reconsiderado':bool(anterior.get('excluido') and not excluir) or anterior.get('reconsiderado',False),
                'motivo':categoria.replace('_',' ') if excluir else '; '.join(sorted(set(justificativas))) or 'Natureza ambígua; análise preservada sem presumir finalidade estrutural'}
        return excluir
    def estado(self):return {'versao':2,'registros':list(self.registros.values()),'duplicacoes':self.duplicacoes,'preservadas':sorted(self.preservadas),'eventos':dict(self.eventos),'portais':[e.estado() for e in self.escopos],'finalidades_observadas':self.evidencias}
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
        result['exclusivas_classificadas_por_finalidade']=dict(Counter(c for r in rows if not all(r['par']) for c in r.get('finalidades',[]) if c))
        result['navegacoes_planejadas_evitadas']=sum(bool(u) for r in excluded if 'admissao' in r.get('fases',[]) for u in r['par'])
        result['pares_contidos_apos_redirecionamento']=sum('pos_navegacao' in r.get('fases',[]) for r in excluded)
        result['escopos_portais']=[{'origem':url_diagnostica(e.base),'site_identificado':e.site,
            'grupo_identificado':bool(e.grupo),'referencias_compartilhadas':len(e.compartilhados)} for e in self.escopos]
        result['nota_navegacoes']='Oportunidades de abertura HTML excluídas por referência única; não são requisições HTTP medidas nem ganho de tempo comprovado.'
        result['paginacoes_relevantes_preservadas']=sum(not r['excluido'] and 'paginação relevante' in r['motivo'] for r in rows)
        result['paginacoes_documentais_preservadas']=sum(not r['excluido'] and 'paginação relevante' in r['motivo'] and 'finalidade documental/legislativa' in r['motivo'] for r in rows)
        result['rotas_w_excluidas']=len({u for r in excluded for u in r['par'] if '/w/' in u})
        result['rotas_traco_excluidas']=len({u for r in excluded for u in r['par'] if '/-/' in u})
        return result
