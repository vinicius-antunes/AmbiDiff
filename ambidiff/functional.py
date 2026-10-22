"""Teste limitado de cliques de navegação, opt-in, em contexto descartável.

Somente links internos equivalentes (GET); requisições com outros métodos são
bloqueadas. Não clica botões sem href, formulários, downloads ou links externos.
"""
from __future__ import annotations
from urllib.parse import urlsplit
import re
from .core import normalizar,permitido

PERMITIDOS=re.compile(r'(?:consultar|acessar|abrir|visualizar|saiba mais|detalhes|conferir|legisla[cç][aã]o)',re.I)
PROIBIDOS=re.compile(r'(?:logout|logoff|exclu|remov|delet|apagar|delete|unsubscribe|sair|download|baixar)',re.I)


def escolher_candidatos(pares,base_a,base_b,limite=2):
    from .paired import e_arquivo,link_equivalente
    escolhidos=[]
    for ia,ib in pares:
        if ia.tipo!='Opção' or ib.tipo!='Opção' or not ia.destino or not ib.destino:continue
        if not ia.seletor or not ib.seletor:continue
        if not PERMITIDOS.search(ia.nome) or PROIBIDOS.search(ia.nome+' '+ia.destino+' '+ib.destino):continue
        if e_arquivo(ia.destino) or e_arquivo(ib.destino):continue
        if not permitido(ia.destino,base_a) or not permitido(ib.destino,base_b):continue
        if not link_equivalente(ia.destino,ib.destino,base_a,base_b):continue
        escolhidos.append((ia,ib))
        if len(escolhidos)>=limite:break
    return escolhidos


def _um_clique(browser,pagina,item,base):
    from .paired import e_arquivo
    origem=urlsplit(base).netloc
    contexto=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},
                                  service_workers='block',accept_downloads=False)
    # A navegação só deve emitir GET/HEAD. Recursos de outros domínios são
    # bloqueados; toda tentativa de POST/PUT/DELETE é abortada.
    def filtro(route):
        req=route.request
        if req.method not in ('GET','HEAD') or urlsplit(req.url).netloc!=origem:
            route.abort()
        else:route.continue_()
    contexto.route('**/*',filtro)
    pagina_teste=contexto.new_page();nova_aba=[]
    contexto.on('page',lambda p:nova_aba.append(p))
    try:
        resposta=pagina_teste.goto(pagina.url,wait_until='domcontentloaded',timeout=10000)
        if resposta and resposta.status>=400:return 'inconclusivo'
        loc=pagina_teste.locator(item.seletor).first
        if not loc.count() or not loc.is_visible(timeout=1500):return 'inconclusivo'
        href=loc.evaluate('e => (e.tagName==="A"?e.href:"")')
        if not href or not permitido(href,base) or e_arquivo(href):return 'inconclusivo'
        antes=pagina_teste.url
        try:loc.click(timeout=3200,no_wait_after=True)
        except Exception:return 'inconclusivo'
        pagina_teste.wait_for_timeout(1100)
        url_final=pagina_teste.url
        # Popup para o mesmo domínio é navegação válida.
        if any(p.url!= 'about:blank' and urlsplit(p.url).netloc==origem for p in nova_aba):return 'navegou'
        if url_final!=antes and url_final!='about:blank':return 'navegou'
        return 'sem_navegacao_observada'
    except Exception:return 'inconclusivo'
    finally:contexto.close()


def verificar_par(browser,pa,pb,ia,ib,nome_a,nome_b,base_a,base_b,log):
    a=_um_clique(browser,pa,ia,base_a)
    b=_um_clique(browser,pb,ib,base_b)
    if a==b or 'inconclusivo' in (a,b):return None
    log('[Clique] Comportamento diferente: '+ia.nome[:70]+' '+a+'/'+b)
    return {'teste_funcional_executado':True,'resultado_funcional_a':a,'resultado_funcional_b':b,'tipo':'Clique','categoria':'Funcionamento dos links',
        'presente_em':nome_a,'nao_identificado_em':nome_b,'pagina':pa.titulo,
        'url_presente':pa.url,'url_comparada':pb.url,'local':ia.local,
        'caminho':' → '.join(pa.trilha),'elemento':ia.nome,
        'destino_a':ia.destino,'destino_b':ib.destino,
        'situacao':'Clique de navegação com comportamento diferente (revisar)',
        'descricao':f'Ao clicar no link "{ia.nome}", o resultado observado foi {nome_a}: {a} e {nome_b}: {b}. '
                     'Teste limitado a links internos e requisições GET/HEAD. '
                     'Não comprova, isoladamente, erro de uma página.'}
