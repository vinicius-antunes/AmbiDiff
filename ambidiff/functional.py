"""Teste limitado de cliques de navegação, opt-in, em contexto descartável.

Somente links internos equivalentes (GET); requisições com outros métodos são
bloqueadas. Não clica botões sem href, formulários, downloads ou links externos.
"""
from __future__ import annotations
from urllib.parse import urlsplit
import re
from .core import normalizar,permitido

PERMITIDOS=re.compile(r'(?:consultar|acessar|abrir|visualizar|saiba mais|detalhes|conferir|início|inicio|legisla[cç][aã]o)',re.I)
PROIBIDOS=re.compile(r'(?:logout|logoff|exclu|remov|delet|apagar|delete|unsubscribe|sair|download|baixar|login|entrar|salvar|enviar|pagar|pagamento|submit|save|pay)',re.I)


def escolher_candidatos(pares,base_a,base_b,limite=2):
    from .paired import e_arquivo,link_equivalente
    escolhidos=[]
    for ia,ib in pares:
        if ia.tipo!='Opção' or ib.tipo!='Opção' :continue
        if not ia.seletor or not ib.seletor:continue
        if not (ia.controle_alvo and ib.controle_alvo) and not PERMITIDOS.search(ia.nome):continue
        if PROIBIDOS.search(ia.nome+' '+ia.destino+' '+ib.destino):continue
        if not ia.destino and not ib.destino and ia.controle_alvo and ib.controle_alvo:
            escolhidos.append((ia,ib))
            if len(escolhidos)>=limite:break
            continue
        if not ia.destino or not ib.destino:continue
        if not PERMITIDOS.search(ia.nome) or PROIBIDOS.search(ia.nome+' '+ia.destino+' '+ib.destino):continue
        if e_arquivo(ia.destino) or e_arquivo(ib.destino):continue
        if not permitido(ia.destino,base_a) or not permitido(ib.destino,base_b):continue
        if not link_equivalente(ia.destino,ib.destino,base_a,base_b):continue
        escolhidos.append((ia,ib))
        if len(escolhidos)>=limite:break
    return escolhidos


def _um_clique(browser,pagina,item,base,detalhar=False):
    from .paired import e_arquivo
    origem=urlsplit(base).netloc
    contexto=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},
                                  service_workers='block',accept_downloads=False)
    # A navegação só deve emitir GET/HEAD. Recursos de outros domínios são
    # bloqueados; toda tentativa de POST/PUT/DELETE é abortada.
    download_solicitado=[];bloqueios=[];respostas_http=[]
    def filtro(route):
        req=route.request
        if e_arquivo(req.url):
            download_solicitado.append(req.url);route.abort();return
        if req.method not in ('GET','HEAD') or urlsplit(req.url).netloc!=origem or PROIBIDOS.search(req.url):
            if req.is_navigation_request() or req.method not in ('GET','HEAD'):bloqueios.append(req.url)
            route.abort()
        else:route.continue_()
    contexto.route('**/*',filtro)
    pagina_teste=contexto.new_page();nova_aba=[]
    pagina_teste.on('download',lambda d:download_solicitado.append(d.url))
    contexto.on('page',lambda p:nova_aba.append(p))
    def resposta_http(response):
        if not response.request.is_navigation_request():return
        try:
            if response.request.frame.parent_frame is not None:return
        except Exception:pass # Resposta inicial de popup pode anteceder a criação do frame.
        respostas_http.append({'url':response.url,'status':response.status})
    contexto.on('response',resposta_http)
    def resultado(codigo):
        final=next((p.url for p in nova_aba if p.url!='about:blank'),pagina_teste.url)
        return {'resposta':codigo,'url_final':final,'nova_aba':bool(nova_aba),'respostas_http':respostas_http,'bloqueios':bloqueios} if detalhar else codigo
    try:
        resposta=pagina_teste.goto(pagina.url,wait_until='domcontentloaded',timeout=10000)
        if resposta and resposta.status>=400:return resultado('http_'+str(resposta.status))
        loc=pagina_teste.locator(item.seletor).first
        if not loc.count() or not loc.is_visible(timeout=1500):return resultado('inconclusivo')
        href=loc.evaluate('e => (e.tagName==="A"?e.href:"")')
        if loc.evaluate('e=>!!e.closest("form")'):return resultado('inconclusivo')
        if href and (not permitido(href,base) or e_arquivo(href)):return resultado('inconclusivo')
        if not href and not loc.evaluate('e=>!!document.getElementById(e.getAttribute("aria-controls"))'):return resultado('inconclusivo')
        conteudo_antes=pagina_teste.locator('body').inner_text(timeout=1500)
        expandido=loc.get_attribute('aria-expanded')
        antes=pagina_teste.url
        try:loc.click(timeout=3200,no_wait_after=True)
        except Exception as ex:return resultado('timeout' if 'timeout' in str(ex).lower() else 'inconclusivo')
        pagina_teste.wait_for_timeout(1100)
        url_final=pagina_teste.url
        if bloqueios:return resultado('inconclusivo')
        erros=[r for r in respostas_http if r['status']>=400]
        if erros:return resultado('http_'+str(erros[-1]['status']))
        # Popup para o mesmo domínio é navegação válida.
        if any(p.url!= 'about:blank' and urlsplit(p.url).netloc==origem for p in nova_aba):return resultado('navegou')
        if download_solicitado:return resultado('download_solicitado')
        if url_final!=antes and url_final!='about:blank':return resultado('navegou')
        if pagina_teste.locator('body').inner_text(timeout=1500)!=conteudo_antes or loc.get_attribute('aria-expanded')!=expandido:return resultado('resposta_conteudo')
        return resultado('sem_navegacao_observada')
    except Exception as ex:return resultado('timeout' if 'timeout' in str(ex).lower() else 'inconclusivo')
    finally:contexto.close()


def verificar_par(browser,pa,pb,ia,ib,nome_a,nome_b,base_a,base_b,log,diagnosticos=None):
    obs_a=_um_clique(browser,pa,ia,base_a,detalhar=True)
    obs_b=_um_clique(browser,pb,ib,base_b,detalhar=True)
    a=obs_a.get('resposta') if isinstance(obs_a,dict) else obs_a
    b=obs_b.get('resposta') if isinstance(obs_b,dict) else obs_b
    final_a=obs_a.get('url_final') if isinstance(obs_a,dict) else None
    final_b=obs_b.get('url_final') if isinstance(obs_b,dict) else None
    from .paired import link_equivalente
    destinos_diferentes=bool(a==b=='navegou' and final_a and final_b and not link_equivalente(final_a,final_b,base_a,base_b))
    observados={'navegou','resposta_conteudo','sem_navegacao_observada','download_solicitado'}
    if diagnosticos is not None:diagnosticos.append({'elemento_a':ia.nome,'elemento_b':ib.nome,'a':a,'b':b,'url_a':pa.url,'url_b':pb.url,'url_final_a':final_a,'url_final_b':final_b,'conclusivo':a in observados and b in observados})
    if a!=b and (str(a).startswith('http_') or str(b).startswith('http_')):
        return {'tipo':'Falha de acesso','categoria':'Falhas de acesso','elemento':ia.nome,'presente_em':nome_a,'nao_identificado_em':nome_b,'url_presente':pa.url,'url_comparada':pb.url,'local':ia.local,
            'resultado_funcional_a':a,'resultado_funcional_b':b,'destino_final_a':final_a,'destino_final_b':final_b,'grau_confianca':'confirmada_observacao','teste_funcional_executado':False,'tentativa_funcional':True,
            'situacao':'Respostas HTTP observadas diferentes','descricao':f'Respostas observadas: {nome_a}: {a}; {nome_b}: {b}. Isso pode envolver acesso/bloqueio ou automação; não comprova defeito permanente nem funcionamento do controle.'}
    if (a==b and not destinos_diferentes) or a not in observados or b not in observados:return None
    log('[Clique] Comportamento diferente: '+ia.nome[:70]+' '+a+'/'+b)
    return {'destino_final_a':final_a,'destino_final_b':final_b,'teste_funcional_executado':True,'resultado_funcional_a':a,'resultado_funcional_b':b,'tag_observacao':'FALHA_FUNCIONAL_OBSERVADA','tipo':'Clique','categoria':'Funcionamento dos links',
        'presente_em':nome_a,'nao_identificado_em':nome_b,'pagina':pa.titulo,
        'url_presente':pa.url,'url_comparada':pb.url,'local':ia.local,
        'caminho':' → '.join(pa.trilha),'elemento':ia.nome,
        'destino_a':ia.destino,'destino_b':ib.destino,
        'situacao':'Clique de navegação com comportamento diferente (revisar)',
        'descricao':f'Ao clicar no link "{ia.nome}", o resultado observado foi {nome_a}: {a} e {nome_b}: {b}. '
                     'Teste limitado a links internos e requisições GET/HEAD. '
                     f'Destinos finais observados: {final_a or "não disponível"} / {final_b or "não disponível"}. Não comprova defeito permanente nem determina qual ambiente está correto.'}
