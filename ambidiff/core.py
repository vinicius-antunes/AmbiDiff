"""Comparador de conteúdo entre ambientes. Navegação apenas de leitura, sem inferir culpa.

O crawler não impõe escolhas manuais de profundidade/páginas. Usa limites internos
preventivos de tempo, memória e requisições e sinaliza quando não cobre todo o portal.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re
import time
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit, unquote

# Limites de segurança internos (não opções de navegação do usuário).
MAX_URLS_SEGURANCA = 2500
MAX_MINUTOS_SEGURANCA = 45
TEMPO_PAGINA_MS = 30000
MAX_FALHAS_CONSECUTIVAS = 15
IGNORAR_QUERY = {'utm_source','utm_medium','utm_campaign','utm_content','utm_term',
                 'fbclid','gclid','jsessionid','phpsessid','sessionid','token','auth','sid'}
ARQUIVOS = {'.pdf','.doc','.docx','.xls','.xlsx','.csv','.odt','.ods','.ppt','.pptx','.zip','.rar'}
IGNORAR_EXT = {'.jpg','.jpeg','.png','.gif','.webp','.svg','.css','.js','.ico',
               '.mp4','.mov','.mp3','.woff','.woff2','.ttf','.xml','.json'} | ARQUIVOS


def normalizar(txt: str) -> str:
    txt = unicodedata.normalize('NFKC', str(txt or ''))
    return re.sub(r'\s+', ' ', txt).strip().casefold()


def titulo_normalizado(txt: str) -> str:
    txt = unicodedata.normalize('NFKD', normalizar(txt))
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in txt if not unicodedata.combining(c))).strip()


def url_limpa(url: str) -> str:
    p = urlsplit(str(url))
    if p.scheme not in ('https','http') or not p.netloc or p.username or p.password:
        raise ValueError('Informe uma URL HTTP/HTTPS completa, sem usuário ou senha.')
    if p.hostname is None: raise ValueError('Domínio inválido.')
    params = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
              if k.casefold() not in IGNORAR_QUERY and not k.casefold().startswith('utm_')]
    path = re.sub(r'/+','/',p.path or '/')
    if path != '/': path=path.rstrip('/')
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),path,urlencode(sorted(params)),''))


def validacao_inicial(url_a: str,url_b: str) -> tuple[str,str]:
    a,b=url_limpa(url_a),url_limpa(url_b)
    if a==b: raise ValueError('Os dois ambientes precisam ter URLs diferentes.')
    return a,b


def referencia_invalida(url: str) -> bool:
    """CMS/Liferay pode expor objetos JSON como atributo href — não são páginas."""
    try:
        path=unquote(urlsplit(url).path).strip()
        return (path.startswith('/{') or path.startswith('{') or
                bool(re.match(r'^/?%7b',urlsplit(url).path,re.I)))
    except (TypeError,ValueError):
        return True


def permitido(url: str,base: str) -> bool:
    try:
        if referencia_invalida(url): return False
        p,b=urlsplit(url_limpa(url)),urlsplit(url_limpa(base))
        if p.netloc != b.netloc: return False
        root=b.path.rstrip('/')
        if root and p.path != root and not p.path.startswith(root+'/'): return False
        suffix=re.search(r'\.[a-z0-9]+$',p.path.lower())
        if suffix and suffix.group() in IGNORAR_EXT:return False
        return True
    except (ValueError,TypeError): return False


def chave_caminho(url: str,base: str) -> str:
    p,b=urlsplit(url),urlsplit(base)
    root=b.path.rstrip('/')
    tail=p.path[len(root):].strip('/') if root else p.path.strip('/')
    query='&'.join(f'{k}={v}' for k,v in parse_qsl(p.query))
    return (tail or '@inicio')+(f'?{query}' if query else '')


@dataclass
class Item:
    tipo: str
    chave: str
    nome: str
    local: str = ''
    destino: str = ''
    posicao: str = ''
    seletor: str = ''
    visivel_texto: bool = True
    imagem_link: bool = False
    natureza: str = ''
    entidade: str = ''


@dataclass
class Pagina:
    url: str
    chave: str
    titulo: str
    itens: list[Item]
    trilha: list[str] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    menus: list[dict] = field(default_factory=list)
    coleta: dict = field(default_factory=dict)


JS_EXTRAIR = r'''() => {
  const clean = s => String(s || '').replace(/\s+/g,' ').trim().slice(0,450);
  const visivel = el => {
    if (!el || ['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','SVG'].includes(el.tagName)) return false;
    if (el.closest('[aria-hidden="true"],[hidden],[inert]')) return false;
    const st=getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden' && el.getClientRects().length>0;
  };
  const isCookie = el => !!el.closest('[id*="cookie" i],[class*="cookie" i],[id*="consent" i],[class*="consent" i],[id*="adopt" i],[class*="adopt" i],[aria-label*="privacidade" i]');
  const posicao = el => {
    if (el.closest('footer,[role="contentinfo"]')) return 'Rodapé';
    if (el.closest('header,[role="banner"]')) return 'Cabeçalho';
    if (el.closest('nav,[role="navigation"]')) return 'Menu de navegação';
    if (el.closest('aside,[role="complementary"]')) return 'Menu lateral';
    if (el.closest('[class*="carousel" i],[class*="banner" i],[id*="banner" i]')) return 'Banner';
    const b=el.getBoundingClientRect(), x=b.left+b.width/2, vw=innerWidth;
    if (b.top+scrollY<window.innerHeight*0.6) return x>=vw*.66?'Topo direito':x<vw*.34?'Topo esquerdo':'Parte superior';
    return x<vw*.30?'Área lateral esquerda':x>=vw*.7?'Área lateral direita':'Conteúdo central';
  };
  const selector = el => {
    const steps=[];let curr=el;
    for(let i=0;curr&&curr.nodeType===1&&i<7;i++,curr=curr.parentElement){
      if(curr.id&&/^[A-Za-z][A-Za-z0-9_:-]{1,80}$/.test(curr.id)){
        steps.unshift('#'+CSS.escape(curr.id));break;
      }
      const tag=curr.tagName.toLowerCase();
      const sib=curr.parentElement?Array.from(curr.parentElement.children).filter(x=>x.tagName===curr.tagName):[curr];
      steps.unshift(tag+(sib.length>1?':nth-of-type('+(sib.indexOf(curr)+1)+')':''));
    }
    return steps.join(' > ');
  };
  const ctx = el => {
    const local=el.closest('section,article,li,tr,[role="tabpanel"],[role="region"],[class*="card" i]');
    const header=local?.querySelector('h1,h2,h3,[role="heading"],strong');
    const row=el.closest('li,tr');
    const rowText=row?clean(row.innerText||row.textContent):'';
    const own=clean(el.innerText||el.getAttribute('aria-label')||el.title);
    const rowContext=rowText&&rowText!==own?clean(rowText.replace(own,'')):'';
    const group=el.closest('nav,header,footer,aside') || el.closest('main,article,section');
    const base=clean(header?.textContent)||rowContext||clean(group?.querySelector('h1,h2,h3')?.textContent);
    return base || (el.closest('footer')?'Rodapé':el.closest('header')?'Cabeçalho':'Conteúdo principal');
  };
  const editorialRef=el=>{
    // A região institucional prevalece sobre a aparência editorial da URL.
    if(el.closest('nav,header,footer,aside,[role="navigation"]'))return '';
    // Não inferir que qualquer item dentro de um <main> é notícia.
    // Buscar o cartão mais próximo com um link identificável para publicação.
    let cur=el;
    for(let n=0;cur&&n<7;n++,cur=cur.parentElement){
      if(cur.matches('nav,header,footer,[role="navigation"]')) return '';
      if(cur.matches('li,article,[class*="card" i],[class*="item" i],[class*="news" i],[class*="noticia" i],[class*="post" i]') || cur===el){
        const links=cur.matches('a[href]')?[cur]:[...cur.querySelectorAll('a[href]')].slice(0,12);
        for(const a of links){
          try { const p=new URL(a.href).pathname;
            if(/^\/(?:w\/|noticias\/|notícias\/|blog\/|post\/)/i.test(p))return p;
          }catch(e){}
        }
      }
      if(cur.matches('main,body'))break;
    }
    // Páginas individuais de artigos com conteúdo central.
    if(/^\/(?:w\/|noticias\/[^/]+|blog\/[^/]+)/i.test(location.pathname)
       && !el.closest('nav,header,footer,aside') )return location.pathname;
    return '';
  };
  const out=[],links=[];
  const add=(tipo,nome,chave,el,destino='',textoVisivel=true)=>{
    nome=clean(nome);chave=clean(chave);
    if(nome&&nome.length>=2)out.push({tipo,nome,chave,local:ctx(el),destino,
      posicao:posicao(el),seletor:selector(el),visivel_texto:textoVisivel,
      imagem_link:el.tagName==='A'&&!textoVisivel&&!!el.querySelector('img'),
      natureza:editorialRef(el)?'editorial':'estrutura',entidade:editorialRef(el)});
  };
  for(const el of document.querySelectorAll('h1,h2,h3,h4,p')){
    if(!visivel(el)||isCookie(el)||el.closest('header,footer,nav,[role="navigation"]'))continue;
    const val=clean(el.innerText||el.textContent);
    if(val.length>=4&&val.length<=420)add('Texto',val,val,el);
  }
  for(const el of document.querySelectorAll('img')){
    if(!visivel(el)||isCookie(el))continue;
    const url=el.currentSrc||el.src||el.getAttribute('data-src')||'';
    if(!url)continue;
    const alt=clean(el.alt||el.getAttribute('aria-label')||'');
    add('Imagem',alt||url.split('/').pop().split('?')[0]||'Imagem',alt||url,el,url,!!alt&&clean(el.innerText).includes(alt));
  }
  for(const el of document.querySelectorAll('a[href]')){
    if(!visivel(el)||isCookie(el))continue;
    const href=el.href; if(!href||!/^https?:/i.test(href))continue;
    const name=clean(el.innerText||el.getAttribute('aria-label')||el.title||el.querySelector('img')?.alt||'');
    if(!name)continue;
    const pathname=(()=>{try{return new URL(href).pathname.toLowerCase()}catch(e){return ''}})();
    const isDoc=/\.(pdf|docx?|xlsx?|csv|pptx?|zip|odt|ods)(\/|$)/i.test(pathname) || /download|baixar|documento.*pdf/i.test(name);
    const tipo=isDoc?'Documento':'Opção';
    add(tipo,name,name,el,href,!!clean(el.innerText));
    links.push({url:href,label:name,local:ctx(el),tipo,selector:selector(el)});
  }
  for(const el of document.querySelectorAll('button,[role="tab"],[role="menuitem"]')){
    if(!visivel(el)||isCookie(el))continue;
    if(el.closest('form')&&el.type==='submit')continue;
    const name=clean(el.innerText||el.getAttribute('aria-label')||'');
    if(name)add('Opção',name,name,el);
  }
  for(const el of document.querySelectorAll('select')){
    if(!visivel(el)||isCookie(el))continue;
    const label=clean(el.getAttribute('aria-label')||el.labels?.[0]?.textContent||el.name||'Seleção');
    for(const opt of el.options){
      const name=clean(opt.textContent);
      if(name&&!opt.disabled&&opt.value!=='')add('Opção',label+': '+name,label+': '+name,el);
    }
  }
  // Conjuntos ordenados de opções visíveis, para comparar posição entre PRD/DES.
  // Apenas grupos com rótulos distinguíveis, sem inferir quando itens são ambíguos.
  const menus=[];
  const areas=[...document.querySelectorAll('nav,aside,[role="navigation"],[role="tablist"],ul,ol,[class*="menu" i],[class*="tabs" i],[class*="cards" i],[class*="grid" i],[class*="list" i]')];
  const seenMenus=new Set();
  for(const area of areas){
    if(!visivel(area)||isCookie(area))continue;
    const els=[...area.querySelectorAll('a[href],button,[role="tab"]')].filter(visivel);
    // Coletar somente opções imediatamente agrupadas, não sublistas inteiras.
    const relevant=els.filter(x=>{
      const candidate=x.closest('nav,aside,[role="navigation"],[role="tablist"],ul,ol,[class*="menu" i],[class*="tabs" i],[class*="cards" i],[class*="grid" i],[class*="list" i]');
      return candidate===area;
    });
    if(relevant.length<2||relevant.length>45)continue;
    const labels=relevant.map(x=>{
      let label=clean(x.innerText||x.getAttribute('aria-label')||x.title||x.querySelector('img')?.alt);
      if(/^(consultar|visualizar|acessar|saiba mais|ver mais)$/i.test(label)){
        const card=x.closest('li,article,[class*="card" i],[class*="item" i]');
        const heading=clean(card?.querySelector('h1,h2,h3,h4,h5,strong')?.innerText);
        if(heading && heading!==label)label=heading+' → '+label;
      }
      return label;
    });
    if(labels.some(x=>!x||x.length<2)||new Set(labels.map(x=>x.toLocaleLowerCase())).size!==labels.length)continue;
    const names=[...labels].sort().join('|');
    const unique=posicao(area)+'|'+names;
    if(seenMenus.has(unique))continue;
    seenMenus.add(unique);
    const title=clean(area.getAttribute('aria-label')||area.querySelector(':scope > h2,:scope > h3,:scope > h4')?.innerText||area.closest('section,article')?.querySelector('h2,h3')?.innerText||'');
    menus.push({nome:title||'Grupo de opções',posicao:posicao(area),seletor:selector(area),opcoes:labels,
      editorial:relevant.length>0&&relevant.every(x=>!!editorialRef(x))});
  }
  // Sinais públicos: informativos, nunca ativam o modo de defasagem sozinhos.
  const avisos=[];
  const avisoRe=/(?:ambiente (?:de )?(?:desenvolvimento|homologa[cç][aã]o|teste)|(?:base|dados|conte[uú]do).{0,35}desatualizad|desatualizad.{0,35}(?:base|dados|conte[uú]do)|dados.{0,35}(?:n[aã]o|sem) atualiza[cç][aã]o)/i;
  for(const el of [...document.querySelectorAll('[role="alert"],.alert,[class*="warning" i],[class*="aviso" i],[class*="banner" i]')].slice(0,75)){
    const tx=clean(el.innerText);
    if(tx.length>=10&&tx.length<400&&avisoRe.test(tx)&&!avisos.includes(tx))avisos.push(tx);
    if(avisos.length>=5)break;
  }
  return {title:clean(document.title||document.querySelector('h1')?.textContent),itens:out,links,menus,avisos_ambiente:avisos};
}'''


def coletar_aba(page, itens: list[dict], links: list[dict], log) -> None:
    """Interage apenas com abas detectadas, sem clicar formulários ou executar ações."""
    try:
        tabs=page.locator('[role="tab"],button[data-bs-toggle="tab"],a[data-bs-toggle="tab"]')
        for i in range(min(tabs.count(),35)):
            tab=tabs.nth(i)
            if not tab.is_visible():continue
            rotulo=(tab.inner_text(timeout=1500) or '').strip()[:80]
            if not rotulo:continue
            try:
                tab.click(timeout=3000)
                page.wait_for_timeout(350)
                dados=page.evaluate(JS_EXTRAIR)
                for item in dados['itens']:
                    item['local']=f'Aba "{rotulo}" → {item["local"]}'
                itens.extend(dados['itens']);links.extend(dados['links'])
            except Exception: continue
    except Exception as e:
        log(f'Aviso: algumas abas não puderam ser abertas: {str(e)[:110]}')


def _abrir(page,url: str):
    """Tenta DOM carregado e recupera resposta quando o portal renderiza lentamente."""
    try:
        return page.goto(url,wait_until='domcontentloaded',timeout=TEMPO_PAGINA_MS)
    except Exception as ex:
        # Somente timeout: se houver conteúdo aproveitável, a navegação pode ter funcionado.
        if 'Timeout' not in type(ex).__name__ and 'Timeout' not in str(ex):raise
        try:
            dados=page.evaluate('() => ({url:location.href,n:document.body?.innerText?.trim().length||0})')
            if url_limpa(dados['url'])==url_limpa(url) and dados['n']>=80:
                return None
        except Exception: pass
        return page.goto(url,wait_until='commit',timeout=TEMPO_PAGINA_MS)


def coletar_site(browser,url_base: str,parar,log,progresso,ambiente: str,
                 *, max_paginas: int = MAX_URLS_SEGURANCA,
                 max_segundos: int = MAX_MINUTOS_SEGURANCA*60) -> tuple[dict[str,Pagina],list[dict],bool,dict]:
    contexto=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},
                                  ignore_https_errors=False,service_workers='block',accept_downloads=False)
    page=contexto.new_page()
    fila=deque([(url_base,['Página inicial'])]);enfileiradas={url_base}
    visitadas=set();paginas={};falhas=[];excluidas=Counter();falhas_seguidas=0
    motivo='';inicio=time.monotonic()
    try:
        while fila and not parar.is_set():
            if len(visitadas)>=max_paginas:
                motivo=f'Limite preventivo de segurança ({max_paginas} URLs) alcançado';break
            if time.monotonic()-inicio>=max_segundos:
                motivo='Tempo máximo preventivo de execução alcançado';break
            if falhas_seguidas>=MAX_FALHAS_CONSECUTIVAS:
                motivo='Muitas falhas consecutivas de acesso';break
            url,trilha=fila.popleft()
            if url in visitadas or not permitido(url,url_base):continue
            visitadas.add(url)
            log(f'[{ambiente}] Abrindo {url}')
            try:
                resposta=_abrir(page,url)
                if resposta and resposta.status>=400:raise RuntimeError(f'HTTP {resposta.status}')
                if not permitido(page.url,url_base):
                    raise RuntimeError('Redirecionamento para fora do escopo autorizado')
                try:
                    page.wait_for_load_state('domcontentloaded',timeout=4000)
                except Exception: pass
                page.wait_for_timeout(450)
                dados=page.evaluate(JS_EXTRAIR)
                if not dados or not isinstance(dados.get('itens'),list):
                    raise RuntimeError('Não foi possível extrair o conteúdo da página')
                itens,links=dados['itens'],dados['links']
                coletar_aba(page,itens,links,log)
                dedup={}
                for val in itens:
                    try: item=Item(**val)
                    except (TypeError,ValueError):continue
                    dedup[(item.tipo,normalizar(item.chave),normalizar(item.local))]=item
                chave=chave_caminho(url,url_base)
                paginas[chave]=Pagina(url,chave,dados.get('title') or chave,list(dedup.values()),trilha[:12])
                falhas_seguidas=0
                log(f'[{ambiente}] {len(dedup)} elementos · {len(paginas)} páginas lidas')
                for link in links:
                    if isinstance(link,dict): destino,rotulo=link.get('url',''),link.get('label','')
                    else: destino,rotulo=link,''
                    try: destino=url_limpa(urljoin(url,destino))
                    except (ValueError,TypeError): continue
                    if referencia_invalida(destino):
                        excluidas['Referências codificadas não navegáveis']+=1;continue
                    if permitido(destino,url_base) and destino not in visitadas and destino not in enfileiradas:
                        rotulo=re.sub(r'\s+',' ',rotulo).strip()[:90] or unquote(urlsplit(destino).path.rsplit('/',1)[-1]) or 'Página'
                        trilha_filha=(trilha+[rotulo])[-12:]
                        fila.append((destino,trilha_filha));enfileiradas.add(destino)
            except Exception as ex:
                falhas.append({'ambiente':ambiente,'url':url,'erro':str(ex)[:320]})
                falhas_seguidas+=1
                log(f'[{ambiente}] Acesso não verificado: {url} — {str(ex)[:110]}')
            # Progresso estimado sobre páginas já descobertas; o total muda enquanto navega.
            progresso(min(0.98,len(visitadas)/max(1,len(visitadas)+len(fila))))
            if not parar.is_set():time.sleep(.09)
    finally:
        contexto.close()
    if motivo:log(f'[{ambiente}] Varredura parcial: {motivo}.')
    completo=(not fila and not motivo and not parar.is_set() and not falhas)
    meta={'visitadas':len(visitadas),'pendentes':len(fila),'motivo_parada':motivo,
          'referencias_excluidas':dict(excluidas)}
    return paginas,falhas,completo,meta


def chave_item(i:Item)->str:
    if i.tipo=='Imagem':
        p=urlsplit(i.destino)
        return normalizar(i.nome) if i.nome and i.nome==i.chave else normalizar(unquote(p.path.rsplit('/',1)[-1]))
    return normalizar(i.chave)


def _localizador(pagina:Pagina,item:Item)->str:
    trilha=[x for x in pagina.trilha if x]
    local=item.local.strip()
    if local and local not in ('Página','Conteúdo principal') and (not trilha or normalizar(local)!=normalizar(trilha[-1])):
        trilha.append(local)
    return ' → '.join(trilha or [pagina.titulo or 'Página inicial'])


def _registro(item:Item,pa:Pagina,pb:Pagina,presente:str,ausente:str,*,referencia=False)->dict:
    caminho=_localizador(pa,item)
    inicio=(f'Na página "{pa.titulo}" ({presente}), procure a seção ou opção "{item.local}". '
            if item.local and item.local not in ('Página','Conteúdo principal') else
            f'Na página "{pa.titulo}" ({presente}), procure o elemento indicado. ')
    descricao=(f'Caminho identificado: {caminho}. {inicio}'
               f'O conteúdo do tipo {item.tipo.lower()} "{item.nome[:200]}" foi encontrado em {presente}, '
               f'mas não foi identificado na página correspondente em {ausente}. '
               f'Abra os links dos dois ambientes e confira essa seção. '
               f'A diferença não determina qual ambiente está atualizado.')
    return {'tipo':item.tipo,'presente_em':presente,'nao_identificado_em':ausente,
            'pagina':pa.titulo,'url_presente':pa.url,'url_comparada':pb.url,
            'local':item.local,'caminho':caminho,'elemento':item.nome[:250],
            'descricao':descricao,'situacao':'Divergência para revisão', 'posicao':item.posicao, 'seletor':item.seletor, 'visivel_texto':item.visivel_texto}


def _texto_parecido(a:Item,b:Item)->float:
    if len(a.nome)<24 or len(b.nome)<24:return 0
    if a.local and b.local and titulo_normalizado(a.local)!=titulo_normalizado(b.local):return 0
    return SequenceMatcher(None,normalizar(a.nome),normalizar(b.nome)).ratio()


def comparacao(itens_a:list[Item],itens_b:list[Item],pagina_a:Pagina,pagina_b:Pagina,
                ambiente_a='PRD',ambiente_b='LAB')->list[dict]:
    saida=[]
    ids_a={(i.tipo,chave_item(i)) for i in itens_a}
    ids_b={(i.tipo,chave_item(i)) for i in itens_b}
    unicos_a=[i for i in itens_a if (i.tipo,chave_item(i)) not in ids_b]
    unicos_b=[i for i in itens_b if (i.tipo,chave_item(i)) not in ids_a]
    # Textos semelhantes são apresentados como UMA substituição, não como duas ausências.
    usados_b=set();pares_a=set()
    for ia,a in enumerate(unicos_a):
        if a.tipo!='Texto':continue
        alternativas=[( _texto_parecido(a,b),ib,b ) for ib,b in enumerate(unicos_b)
                      if b.tipo=='Texto' and ib not in usados_b]
        if not alternativas:continue
        ratio,ib,b=max(alternativas,key=lambda x:x[0])
        if ratio>=.82:
            usados_b.add(ib);pares_a.add(ia)
            caminho=_localizador(pagina_a,a)
            saida.append({'tipo':'Texto','presente_em':ambiente_a,'nao_identificado_em':ambiente_b,
                'pagina':pagina_a.titulo,'url_presente':pagina_a.url,'url_comparada':pagina_b.url,
                'local':a.local,'caminho':caminho,'elemento':a.nome[:240],
                'texto_a':a.nome,'texto_b':b.nome,
                'descricao':f'Caminho identificado: {caminho}. O trecho de texto é diferente nas duas páginas correspondentes. '
                            f'Em {ambiente_a}: "{a.nome[:210]}". Em {ambiente_b}: "{b.nome[:210]}". '
                            f'Confira a seção nos dois endereços; não é possível determinar qual está atualizado.',
                'situacao':'Texto diferente','posicao':a.posicao,'seletor':a.seletor,'visivel_texto':a.visivel_texto})
    ja=set()
    for ia,item in enumerate(unicos_a):
        k=(item.tipo,chave_item(item))
        if ia in pares_a or k in ja:continue
        saida.append(_registro(item,pagina_a,pagina_b,ambiente_a,ambiente_b));ja.add(k)
    ja=set()
    for ib,item in enumerate(unicos_b):
        k=(item.tipo,chave_item(item))
        if ib in usados_b or k in ja:continue
        saida.append(_registro(item,pagina_b,pagina_a,ambiente_b,ambiente_a));ja.add(k)
    return saida



def referencias_suspeitas(pa: Pagina, pb: Pagina, nome_a: str, nome_b: str) -> list[dict]:
    """URLs distintas podem ser equivalentes: nunca contam como divergências confirmadas."""
    def destinos(pagina: Pagina):
        mapa={}
        for item in pagina.itens:
            if item.tipo not in ('Imagem','Documento','Opção') or not item.destino:continue
            if item.tipo=='Opção' and len(item.nome)<6:continue
            chave=(item.tipo,chave_item(item),titulo_normalizado(item.local))
            mapa.setdefault(chave,item)
        return mapa
    ma,mb=destinos(pa),destinos(pb)
    saida=[]
    for chave in ma.keys() & mb.keys():
        ia,ib=ma[chave],mb[chave]
        def comparar_destino(url,pagina):
            p=urlsplit(url);origem=urlsplit(pagina.url)
            return (p.path.rstrip('/'),p.query) if p.netloc==origem.netloc else (p.netloc,p.path.rstrip('/'),p.query)
        if comparar_destino(ia.destino,pa)==comparar_destino(ib.destino,pb):continue
        saida.append({'tipo':ia.tipo,'elemento':ia.nome,'caminho':_localizador(pa,ia),
            'ambiente_a':nome_a,'ambiente_b':nome_b,'pagina_a':pa.url,'pagina_b':pb.url,
            'destino_a':ia.destino,'destino_b':ib.destino,
            'motivo':'Endereços de referência diferentes; os conteúdos podem ser equivalentes. Verificação manual necessária.'})
    return saida


def comparar_sites(pag_a:dict[str,Pagina],pag_b:dict[str,Pagina],
                   nome_a='PRD',nome_b='LAB',completo_a=False,completo_b=False):
    """Retorna só diferenças de páginas efetivamente pareadas e coletadas.

    Páginas sem par são pendências à parte, nunca divergências de conteúdo.
    """
    resultados=[];pendencias=[];referencias=[];usados_b=set()
    if not pag_a or not pag_b:
        return resultados,pendencias,referencias
    for chave,pa in pag_a.items():
        pb=pag_b.get(chave)
        if pb and pb.chave in usados_b:pb=None
        if not pb:
            cand=[x for kb,x in pag_b.items() if kb not in usados_b
                  and titulo_normalizado(x.titulo)==titulo_normalizado(pa.titulo)
                  and len(titulo_normalizado(pa.titulo))>=8]
            if len(cand)==1:pb=cand[0]
        if pb:
            usados_b.add(pb.chave)
            resultados.extend(comparacao(pa.itens,pb.itens,pa,pb,nome_a,nome_b))
            referencias.extend(referencias_suspeitas(pa,pb,nome_a,nome_b))
        else:
            pendencias.append({'ambiente':nome_a,'url':pa.url,'pagina':pa.titulo,
                'motivo':f'Não foi localizada uma página correspondente em {nome_b}. Não comprova ausência.',
                'caminho':' → '.join(pa.trilha)})
    for chave,pb in pag_b.items():
        if chave not in usados_b:
            pendencias.append({'ambiente':nome_b,'url':pb.url,'pagina':pb.titulo,
                'motivo':f'Não foi localizada uma página correspondente em {nome_a}. Não comprova ausência.',
                'caminho':' → '.join(pb.trilha)})
    for n,item in enumerate(resultados,1):item['id']=f'DIV-{n:04d}'
    return resultados,pendencias,referencias


def _avisos(falhas:list[dict],metas:dict)->list[dict]:
    grupos={}
    for f in falhas:
        txt=f.get('erro','')
        if re.search(r'HTTP\s+\d{3}',txt):categoria=re.search(r'HTTP\s+\d{3}',txt).group(0)
        elif 'Timeout' in txt or 'timeout' in txt:categoria='Tempo de resposta excedido'
        elif 'Redirecionamento' in txt:categoria='Redirecionamento'
        else:categoria='Falha de acesso/coleta'
        k=(f.get('ambiente','?'),categoria)
        grupo=grupos.setdefault(k,{'ambiente':k[0],'tipo':categoria,'quantidade':0,'exemplos':[]})
        grupo['quantidade']+=1
        if len(grupo['exemplos'])<4:grupo['exemplos'].append(f['url'])
    for ambiente,meta in metas.items():
        for tipo,qtd in meta.get('referencias_excluidas',{}).items():
            grupos[(ambiente,tipo)]={'ambiente':ambiente,'tipo':tipo,
                'quantidade':qtd,'exemplos':[]}
        if meta.get('motivo_parada'):
            grupos[(ambiente,'Varredura parcial')]={'ambiente':ambiente,'tipo':'Varredura parcial',
                'quantidade':1,'exemplos':[meta['motivo_parada']]}
    return sorted(grupos.values(),key=lambda r:(r['ambiente'],r['tipo']))


def inferir_site(pag_a:dict[str,Pagina],pag_b:dict[str,Pagina],base_a:str)->str:
    for pag in (pag_a,pag_b):
        inicial=pag.get('@inicio')
        if inicial:
            titulo=re.sub(r'^(PRD|LAB|DES)\s*[-–|:]\s*','',inicial.titulo,flags=re.I).strip()
            if titulo and len(titulo)>3:return titulo[:100]
    return urlsplit(base_a).hostname or 'Comparação de ambientes'


def executar(url_a,url_b,nome_a,nome_b,parar,log,progresso,site_nome='', evidencias_dir=None, auditar_externos=False, ambiente_desatualizado='',checkpoint=None,verificar_cliques=False,rotas_equivalentes=None):
    """v1.5: comparação pareada, com variações editoriais separadas."""
    from .paired import executar_pareado
    return executar_pareado(url_a,url_b,nome_a,nome_b,parar,log,progresso,
                           site_nome=site_nome,evidencias_dir=evidencias_dir, auditar_externos=auditar_externos,
                           ambiente_desatualizado=ambiente_desatualizado,checkpoint=checkpoint,
                           verificar_cliques=verificar_cliques,rotas_equivalentes=rotas_equivalentes)
