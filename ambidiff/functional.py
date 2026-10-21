"""Teste limitado de cliques de navegação, opt-in, em contexto descartável.

Somente links internos equivalentes (GET); requisições com outros métodos são
bloqueadas. Não clica botões sem href, formulários, downloads ou links externos.
"""
from __future__ import annotations
from urllib.parse import urlsplit
import re
from .core import normalizar,permitido,url_limpa
from .navigation import pagina_autenticacao,rota_autenticacao

PERMITIDOS=re.compile(r'(?:in[ií]cio|home|p[aá]gina inicial|consultar|acessar|abrir|visualizar|saiba mais|detalhes|conferir|legisla[cç][aã]o)',re.I)
PROIBIDOS=re.compile(r'(?:logout|logoff|exclu|remov|delet|apagar|delete|unsubscribe|sair|download|baixar|salvar|gravar|cadastrar|confirmar|enviar|submit|update|insert|create)',re.I)


def escolher_candidatos(pares,base_a,base_b,limite=2,equivalencia=None):
    from .paired import e_arquivo,link_equivalente
    escolhidos=[]
    for ia,ib in pares:
        if ia.tipo!='Opção' or ib.tipo!='Opção' or not ia.destino or not ib.destino:continue
        if not ia.seletor or not ib.seletor:continue
        menu=ia.posicao in ('Menu de navegação','Menu lateral','Cabeçalho','Rodapé')
        if not (PERMITIDOS.search(ia.nome) or menu):continue
        if PROIBIDOS.search(ia.nome+' '+ib.nome+' '+ia.destino+' '+ib.destino):continue
        if rota_autenticacao(ia.destino) or rota_autenticacao(ib.destino):continue
        if e_arquivo(ia.destino) or e_arquivo(ib.destino):continue
        if not permitido(ia.destino,base_a) or not permitido(ib.destino,base_b):continue
        if not (equivalencia(ia.destino,ib.destino) if equivalencia else link_equivalente(ia.destino,ib.destino,base_a,base_b)):continue
        escolhidos.append((ia,ib))
        if len(escolhidos)>=limite:break
    return escolhidos


def _um_clique(browser,pagina,item,base):
    from .paired import e_arquivo
    origem=urlsplit(base).netloc
    contexto=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},
                                  service_workers='block',accept_downloads=False)
    bloqueios=[]
    def filtro(route):
        req=route.request
        if (req.method not in ('GET','HEAD') or urlsplit(req.url).netloc!=origem
                or PROIBIDOS.search(req.url)
                or (req.is_navigation_request() and not permitido(req.url,base))):
            bloqueios.append({'url':req.url,'metodo':req.method})
            route.abort()
        else:route.continue_()
    contexto.route('**/*',filtro)
    pagina_teste=contexto.new_page();nova_aba=[]
    contexto.on('page',lambda p:nova_aba.append(p))
    def resultado(status,motivo):
        return {'status':status,'motivo':motivo,'destino_declarado':item.destino,
                'url_final':pagina_teste.url,'bloqueios':list(bloqueios)}
    try:
        resposta=pagina_teste.goto(pagina.url,wait_until='domcontentloaded',timeout=10000)
        if resposta and resposta.status>=400:return resultado('inconclusivo','HTTP '+str(resposta.status))
        auth=pagina_autenticacao(pagina_teste,pagina_teste.url)
        if auth:return resultado('autenticacao',auth)
        loc=pagina_teste.locator(item.seletor).first
        if not loc.count() or not loc.is_visible(timeout=1500):return resultado('inconclusivo','Controle não localizado ou invisível.')
        href=loc.evaluate('e => (e.tagName==="A"?e.href:"")')
        if (not href or not permitido(href,base) or e_arquivo(href)
                or PROIBIDOS.search(href) or rota_autenticacao(href)):
            return resultado('nao_testado','Destino fora da política de navegação de leitura.')
        if url_limpa(href)!=url_limpa(item.destino):
            return resultado('inconclusivo','O href mudou desde a coleta; clique não realizado.')
        antes=pagina_teste.url
        loc.click(timeout=3200,no_wait_after=True)
        pagina_teste.wait_for_timeout(1100)
        if bloqueios:return resultado('inconclusivo','Requisições bloqueadas pela política; comportamento não comprovado.')
        for p in [pagina_teste,*nova_aba]:
            if p.is_closed():continue
            auth=pagina_autenticacao(p,p.url)
            if auth:return resultado('autenticacao',auth)
        destinos=[p.url for p in nova_aba if not p.is_closed() and p.url!='about:blank']
        final=destinos[-1] if destinos else pagina_teste.url
        if url_limpa(final)==url_limpa(href):
            r=resultado('destino_atual' if url_limpa(antes)==url_limpa(href) else 'navegou','Destino observado coincide com o href.')
            r['url_final']=final
            return r
        if final!=antes:
            r=resultado('destino_diferente','Navegação terminou em outra rota; revisar redirecionamento.')
            r['url_final']=final
            return r
        return resultado('sem_navegacao_observada','URL não mudou durante a janela observada; não comprova defeito.')
    except Exception as ex:return resultado('inconclusivo','Falha da automação ou bloqueio: '+str(ex)[:250])
    finally:contexto.close()


def verificar_par(browser,pa,pb,ia,ib,nome_a,nome_b,base_a,base_b,log,resultados=None):
    a=_um_clique(browser,pa,ia,base_a)
    b=_um_clique(browser,pb,ib,base_b)
    if resultados is not None:
        resultados.append({'elemento':ia.nome,'pagina_a':pa.url,'pagina_b':pb.url,nome_a:a,nome_b:b})
    sa,sb=a['status'],b['status']
    if sa==sb or any(x in ('inconclusivo','nao_testado','autenticacao') for x in (sa,sb)):return None
    log('[Clique] Comportamento diferente: '+ia.nome[:70]+' '+sa+'/'+sb)
    return {'tipo':'Clique','categoria':'Funcionamento dos links',
        'presente_em':nome_a,'nao_identificado_em':nome_b,'pagina':pa.titulo,
        'url_presente':pa.url,'url_comparada':pb.url,'local':ia.local,
        'caminho':' → '.join(pa.trilha),'elemento':ia.nome,
        'destino_a':ia.destino,'destino_b':ib.destino,'observacoes_clique':{nome_a:a,nome_b:b},
        'situacao':'Clique de navegação com comportamento diferente (revisar)',
        'descricao':f'Ao clicar no link "{ia.nome}", o resultado observado foi {nome_a}: {sa} e {nome_b}: {sb}. '
                     'Teste limitado a links internos e requisições GET/HEAD. '
                     'Não comprova, isoladamente, erro de uma página.'}
