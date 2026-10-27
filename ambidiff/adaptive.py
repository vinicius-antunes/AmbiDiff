"""Sondas locais de DOM e política de releitura; nenhuma prova de equivalência."""
import time

JS_SONDA=r'''() => {
 if(!window.__ambidiffObserver){
   const state={versao:0,ultima:performance.now(),inicio:performance.now(),semantica:null,versaoSemantica:0,ultimaSemantica:performance.now()};
   const observer=new MutationObserver(records=>{
     if(records.length){state.versao+=records.length;state.ultima=performance.now();}
   });
   observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true});
   window.__ambidiffObserver=state;
 }
 const s=window.__ambidiffObserver;
 const observado=JSON.stringify([[...document.querySelectorAll('h1,h2,h3,h4,p,dt,dd,time[datetime],[role="heading"],[data-field],[itemprop]')].map(e=>[e.innerText,!!e.getClientRects().length,getComputedStyle(e).visibility]),[...document.querySelectorAll('a,button,input,select,img,section,article,nav,[role]')].map(e=>[e.tagName,['A','BUTTON','SELECT'].includes(e.tagName)?e.innerText:'',getComputedStyle(e).visibility,e.getAttribute('role'),e.getAttribute('href'),e.getAttribute('aria-label'),e.getAttribute('aria-expanded'),e.getAttribute('aria-hidden'),e.hasAttribute('disabled'),e.tagName==='IMG'&&e.getAttribute('aria-hidden')!=='true'?[e.alt,e.getAttribute('src')]:null,!!e.getClientRects().length])]);
 const limitada=observado.length>1000000;
 if(s.semantica!==observado){s.semantica=observado;s.versaoSemantica++;s.ultimaSemantica=performance.now();}
 return {versao:s.versaoSemantica,mutacoes_tecnicas:s.versao,observacao_ms:performance.now()-s.inicio,quieto_ms:performance.now()-s.ultimaSemantica,limitacao_sonda:limitada,
   pronto:document.readyState==='complete'&&!limitada,
   carregando:document.querySelectorAll('[aria-busy="true"],[role="progressbar"]').length,
   imagens_pendentes:[...document.images].filter(i=>!i.complete&&i.loading!=='lazy').length,
   lazy:document.querySelectorAll('[loading="lazy"],[data-src],[data-lazy-src]').length,
   abas:document.querySelectorAll('[role="tab"],[data-bs-toggle="tab"]').length,
   scripts:document.scripts.length,
   scroll:Math.max(document.body?.scrollHeight||0,document.documentElement.scrollHeight),
   win:innerHeight,y:scrollY};
}'''

def sondar(page):
    return page.evaluate(JS_SONDA)

def preparar(page,log,delay=160,limite_segundos=7.0,parar=None):
    """Percorre toda a altura, mantém abas no extrator e espera quietude observada.

    Janela mínima 350 ms, 1,3 s com scripts/lazy/abas. Orçamento limitado; nunca
    bloqueia recursos ou depende de silêncio de rede. Não certifica timers futuros.
    """
    inicio=time.monotonic();passos=0;estavel=False;limitado=False;espera=0
    def esperar(ms):
        nonlocal espera
        antes=time.perf_counter();page.wait_for_timeout(ms);espera+=time.perf_counter()-antes
    try:
        s=sondar(page);complexa=bool(s['scripts'] or s['lazy'] or s['abas'])
        minimo=1300 if complexa else 350
        while True:
            if parar and parar.is_set():limitado=True;break
            if time.monotonic()-inicio>=limite_segundos+2:limitado=True;break
            if s['y']+s['win']<s['scroll']-8:
                if passos>=35 or time.monotonic()-inicio>=limite_segundos:limitado=True;break
                page.evaluate('() => window.scrollBy(0,Math.max(350,innerHeight*0.80))')
                passos+=1;esperar(delay)
            else:
                if s['y']:
                    page.evaluate('() => window.scrollTo(0,0)')
                # Não rolar novamente do topo; a extensão é conferida abaixo.
                altura=s['scroll']
                while time.monotonic()-inicio<limite_segundos+2:
                    if parar and parar.is_set():limitado=True;break
                    s=sondar(page)
                    if s['scroll']>altura+8:break
                    if max(s.get('observacao_ms',0),(time.monotonic()-inicio)*1000)>=minimo and s['quieto_ms']>=350 and s['pronto'] and not s['carregando'] and not s['imagens_pendentes']:
                        estavel=True;break
                    esperar(100)
                if estavel or limitado:break
                if s['scroll']<=altura+8:limitado=True;break
                # Crescimento após rolagem: retoma do fim já percorrido.
                page.evaluate('(h)=>window.scrollTo(0,Math.max(0,h-innerHeight))',altura)
            s=sondar(page)
        page.evaluate('() => window.scrollTo(0,0)')
        return {'passos_rolagem':passos,'rolagem_limitada':limitado,'estavel':estavel,
                'espera_carregamento_segundos':round(espera,6),
                'sonda':sondar(page),'preparacao':'adaptativa completa','janela_minima_ms':minimo,
                'verificacoes_omitidas':[],'espera_reduzida':not complexa,'motivo_preparacao':'Janela observada neste documento; quietude semântica de 350 ms, 1.300 ms com scripts/lazy/abas; rolagem mantida','duracao_segundos':round(time.monotonic()-inicio,6)}
    except Exception as ex:
        log('[Coleta] Preparação adaptativa parcial: '+str(ex)[:110])
        return {'passos_rolagem':passos,'rolagem_limitada':True,'estavel':False,'erro':str(ex)[:180],'espera_carregamento_segundos':round(espera,6)}

def decidir_releitura(page_a,page_b,pa,pb,comps,parar):
    """Uma diferença persistente não é sinal de carregamento incompleto."""
    motivos=[];sondas=[]
    for page,pag in ((page_a,pa),(page_b,pb)):
        try:
            atual=sondar(page);antes=pag.coleta.get('sonda')
            if not antes:motivos.append('Sonda anterior indisponível')
            elif atual['versao']!=antes['versao']:motivos.append('DOM mudou após a coleta')
            if not pag.coleta.get('estavel') or pag.coleta.get('rolagem_limitada'):motivos.append('Preparação inicial incompleta')
            if atual['carregando'] or atual['imagens_pendentes'] or not atual['pronto']:motivos.append('Carregamento ainda pendente')
            sondas.append(atual)
        except Exception:motivos.append('Não foi possível verificar estabilidade')
    # Confirma também uma ausência isolada: a espera sobreposta entre ambientes
    # não pode transformar uma atualização tardia em divergência definitiva.
    ausencias=sum(d.get('tipo') in ('Texto','Imagem','Opção') for d in comps)
    if not motivos and ausencias and not parar.is_set():
        page_a.wait_for_timeout(200)
        for page,antes in zip((page_a,page_b),sondas):
            if sondar(page)['versao']!=antes['versao']:motivos.append('DOM mudou na confirmação curta')
    return sorted(set(motivos))

def cobertura_nao_piorou(antes,depois):
    """Não troca por DOM vazio nem perde referências previamente coletadas."""
    controles_antes={(i.tipo,i.nome,i.destino) for i in antes.itens if i.tipo in ('Opção','Documento')}
    controles_depois={(i.tipo,i.nome,i.destino) for i in depois.itens if i.tipo in ('Opção','Documento')}
    return (depois.coleta.get('estavel',False) and not depois.coleta.get('rolagem_limitada') and
            len(depois.itens)>=len(antes.itens) and len(depois.links)>=len(antes.links) and
            controles_antes<=controles_depois)
