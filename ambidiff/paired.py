"""Varredura pareada (v1.5).

Uma opção só é seguida quando seus destinos são equivalentes entre ambientes.
Diferença de destino encerra SOMENTE o ramo daquela opção. Não faz auditoria
no conteúdo para decidir qual destino está correto.
"""
from __future__ import annotations
from collections import Counter, deque, defaultdict
from dataclasses import replace, asdict
from pathlib import Path
import re
import shutil
import time
import unicodedata
from urllib.parse import urlsplit, urljoin, unquote

from .smart import Metricas, Inteligencia
from .documents import Documentos
from .intelligence import separar_editoriais,agrupar_variacoes,sinais_extraidos,item_editorial
from .diagnostics import classificar_erro
from .visual import comparar_visuais
from .functional import escolher_candidatos,verificar_par
from .core import (ARQUIVOS, MAX_URLS_SEGURANCA, MAX_MINUTOS_SEGURANCA,
                   MAX_FALHAS_CONSECUTIVAS, JS_EXTRAIR, Item, Pagina,
                   _abrir, coletar_aba, comparacao, inferir_site, normalizar,
                   permitido, referencia_invalida, url_limpa, validacao_inicial,
                   _avisos, titulo_normalizado)

# Evita que uma sequência de URLs de arquivos interrompa a navegação.
_MAX_EVIDENCIAS = 40
_MAX_EXTERNOS = 8
_MAX_OPCOES_EXTERNAS = 5

COOKIES_TERMS={'adopt','opt-out','controle sua privacidade','minhas opções',
               'rejeitar','aceitar','aceitar cookies','preferências de cookies','consentimento de cookies'}


def e_arquivo(url: str) -> bool:
    p=urlsplit(url)
    # Liferay publica muitos PDFs sem extensão na URL. Não são páginas HTML.
    if re.search(r'^/documents/d/[^/]+/[^/]+',unquote(p.path),re.I):return True
    return any(re.search(re.escape(ext)+r'(?:/|$)',unquote(p.path),re.I) for ext in ARQUIVOS)


def link_equivalente(url_a:str,url_b:str,base_a:str,base_b:str)->bool:
    """Ignora SOMENTE a troca de host entre os dois ambientes na MESMA rota.

    URLs externas devem ser iguais. Rotas internas e parâmetros distintos
    representam divergência de destino (ainda que duas páginas possam ser iguais).
    """
    a,b=url_limpa(url_a),url_limpa(url_b)
    pa,pb,ba,bb=map(urlsplit,(a,b,base_a,base_b))
    int_a=pa.netloc==ba.netloc
    int_b=pb.netloc==bb.netloc
    # URLs literalmente iguais (mesmo host e rota) nunca são divergência.
    if a == b: return True
    if int_a and int_b:
        root_a=ba.path.rstrip('/')
        root_b=bb.path.rstrip('/')
        path_a=pa.path[len(root_a):] if root_a and pa.path.startswith(root_a+'/') else pa.path
        path_b=pb.path[len(root_b):] if root_b and pb.path.startswith(root_b+'/') else pb.path
        return (path_a or '/',pa.query)==(path_b or '/',pb.query)
    if int_a!=int_b:return False
    return a==b



def imagem_equivalente(url_a:str,url_b:str,base_a:str,base_b:str)->bool:
    # Timestamp `t=` do logotipo Liferay é cache-buster, não mudança visual.
    from urllib.parse import parse_qsl, urlencode, urlunsplit
    def limpar_logo(u):
        p=urlsplit(u)
        if p.path.rstrip('/')=='/image/layout_set_logo':
            q=urlencode([(k,v) for k,v in parse_qsl(p.query) if k.casefold()!='t'])
            return urlunsplit((p.scheme,p.netloc,p.path,q,''))
        return u
    return link_equivalente(limpar_logo(url_a),limpar_logo(url_b),base_a,base_b)

def categoria_item(item:Item)->str:
    return 'Documentos' if item.tipo=='Documento' else 'Menus e opções' if item.tipo=='Opção' else 'Imagens e banners' if item.tipo=='Imagem' else 'Textos'


def refiltro(itens:list[Item])->list[Item]:
    saida=[];seen=set()
    for i in itens:
        if i.tipo=='Opção' and normalizar(i.nome) in COOKIES_TERMS:continue
        # Não omita duas opções com mesmo texto que apontam para destinos distintos.
        k=(i.tipo,normalizar(i.chave),normalizar(i.local),i.destino)
        if k not in seen:
            saida.append(i);seen.add(k)
    return saida


def _preparar_conteudo(page,log,delay=160,limite_segundos=7.0,parar=None):
    from .adaptive import preparar
    return preparar(page,log,delay,limite_segundos,parar)


def _extrair_page(page,url:str,trilha:list[str],log,metricas=None,profunda=True)->Pagina:
    metricas=metricas or Metricas()
    if profunda:
        with metricas.medir('preparacao'):resumo=_preparar_conteudo(page,log,parar=metricas.parar)
    else:resumo={'estavel':True,'rolagem_limitada':False,'inspecao_profunda':False}
    inicio_extracao=time.perf_counter()
    if not resumo['estavel'] or resumo['rolagem_limitada']:
        log('[Coleta] Página com estabilidade limitada: '+url[:100])
    dados=page.evaluate(JS_EXTRAIR)
    if not isinstance(dados,dict) or not isinstance(dados.get('itens'),list):
        raise RuntimeError('A página não retornou conteúdo HTML analisável.')
    its=list(dados['itens']);links=list(dados['links'])
    if profunda:
        with metricas.medir('abas'):coletar_aba(page,its,links,lambda _s:None,parar=metricas.parar)
    itens=[]
    for raw in its:
        try:itens.append(Item(**raw))
        except (TypeError,ValueError):continue
    from .adaptive import sondar
    resumo['sonda']=sondar(page)
    resumo['avisos_ambiente']=dados.get('avisos_ambiente',[])
    metricas.tempos['extracao']+=time.perf_counter()-inicio_extracao
    metricas.contagens['operacoes_extracao']+=1
    return Pagina(url, '',dados.get('title') or 'Página',refiltro(itens),trilha[:12],links, dados.get('menus',[]),resumo)

def _alinhamento_de_componentes(pa:Pagina,pb:Pagina,base_a:str,base_b:str):
    """Combina controles sem texto visível e imagens por região/posição DOM.

    Se duas imagens ocuparem a mesma posição mas os arquivos diferirem,
    NÃO afirmamos que uma esteja ausente: guardamos uma pendência para revisão.
    Elementos com ALT/ARIA diferentes não devem gerar ausências duplicadas.
    """
    skip_a=set();skip_b=set();pendencias=[]
    for tipo in ('Imagem','Opção'):
        a=[i for i in pa.itens if i.tipo==tipo and i.seletor]
        b=[i for i in pb.itens if i.tipo==tipo and i.seletor]
        mapa_a=defaultdict(list);mapa_b=defaultdict(list)
        for i in a:mapa_a[(i.seletor, i.posicao)].append(i)
        for i in b:mapa_b[(i.seletor, i.posicao)].append(i)
        for k in mapa_a.keys() & mapa_b.keys():
            if len(mapa_a[k])!=1 or len(mapa_b[k])!=1:continue
            ia,ib=mapa_a[k][0],mapa_b[k][0]
            # Componente nomeado pelo texto visível: mudança real de rótulo importa.
            if tipo=='Opção' and ia.visivel_texto and ib.visivel_texto:continue
            # Não parear controles sem texto que apontam para destinos distintos:
            # só os links com MESMO destino devem ser ignorados como duplicação.
            if tipo=='Opção' and ia.destino and ib.destino and not link_equivalente(ia.destino,ib.destino,base_a,base_b):continue
            skip_a.add(id(ia));skip_b.add(id(ib))
            if tipo=='Imagem' and ia.destino and ib.destino and not imagem_equivalente(ia.destino,ib.destino,base_a,base_b):
                pendencias.append({'tipo':'Imagem','natureza':('editorial' if item_editorial(ia,pa) or item_editorial(ib,pb) else 'estrutura'),'ambiente_a':'PRD','ambiente_b':'DES',
                    'url_presente':pa.url,'url_comparada':pb.url,
                    'caminho':' → '.join(pa.trilha),
                    'motivo':'Arquivos diferentes na mesma posição; a aparência não foi comparada visualmente.',
                    'destino_a':ia.destino,'destino_b':ib.destino,
                    'elemento':ia.nome+' / '+ib.nome,'posicao':ia.posicao,'seletor':ia.seletor})
    # Link gráfico sem texto visível não equivale a opção textual ausente.
    # Os destinos ainda são comparados por _link_pairs, via seletor.
    return [i for i in pa.itens if id(i) not in skip_a and not (i.tipo=='Opção' and i.imagem_link)], [i for i in pb.itens if id(i) not in skip_b and not (i.tipo=='Opção' and i.imagem_link)],pendencias


def diferencas_de_ordem(pa:Pagina,pb:Pagina,nome_a='PRD',nome_b='DES')->list[dict]:
    """Uma ocorrência por conjunto de opções com mesma composição e ordem diferente.

    Não sinaliza itens faltantes como ordem alterada e evita correspondências
    duvidosas quando um mesmo conjunto aparece em mais de um menu.
    """
    a=pa.menus or [];b=pb.menus or []
    def key(m):
        return tuple(sorted(titulo_normalizado(i) for i in m.get('opcoes',[])))
    by_a=defaultdict(list);by_b=defaultdict(list)
    for m in a:
        if len(m.get('opcoes',[]))>=2:by_a[key(m)].append(m)
    for m in b:
        if len(m.get('opcoes',[]))>=2:by_b[key(m)].append(m)
    candidates=[]
    for k in by_a.keys() & by_b.keys():
        if len(by_a[k])!=1 or len(by_b[k])!=1:continue
        ma,mb=by_a[k][0],by_b[k][0]
        # Dois menus com a mesma composição em áreas diferentes são ambíguos.
        if ma.get('posicao')!=mb.get('posicao'):continue
        names_a=[titulo_normalizado(x) for x in ma['opcoes']]
        names_b=[titulo_normalizado(x) for x in mb['opcoes']]
        if names_a==names_b:continue
        # Grupos aninhados: preferir o maior; nunca contar um mesmo deslocamento duas vezes.
        candidates.append((set(k),ma,mb))
    candidates.sort(key=lambda t:len(t[0]),reverse=True)
    chosen=[]
    for entries,ma,mb in candidates:
        if any(entries <= seen for seen,_,_ in chosen):continue
        chosen.append((entries,ma,mb))
    result=[]
    for _,ma,mb in chosen:
        arr_a=ma['opcoes'];arr_b=mb['opcoes']
        changes=[f'"{label}": {i+1}ª em {nome_a}, {next(j+1 for j,x in enumerate(arr_b) if titulo_normalizado(x)==titulo_normalizado(label))}ª em {nome_b}'
                 for i,label in enumerate(arr_a) if titulo_normalizado(arr_b[i])!=titulo_normalizado(label)]
        result.append({'tipo':'Ordem','categoria':'Ordem das opções',
          'presente_em':nome_a,'nao_identificado_em':nome_b,'pagina':pa.titulo,
          'url_presente':pa.url,'url_comparada':pb.url,'local':ma.get('nome') or 'Lista de opções',
          'posicao':ma.get('posicao') or 'Não determinada','seletor':ma.get('seletor',''),
          'visivel_texto':True,'natureza':('editorial' if ma.get('editorial') and mb.get('editorial') else 'estrutura'),
          'caminho':' → '.join(pa.trilha),
          'elemento':ma.get('nome') or 'Opções reordenadas',
          'ordem_a':arr_a,'ordem_b':arr_b,
          'descricao':f'A ordem das opções é diferente entre {nome_a} e {nome_b} na região {ma.get("posicao")}. '
                      'Ambos apresentam as mesmas opções. '+ '; '.join(changes[:9]) +
                      (f'; e outras {len(changes)-9} posições.' if len(changes)>9 else '.'),
          'situacao':'Mesmas opções em ordem diferente'})
    return result


def _link_chave(item:Item):
    return (item.tipo,normalizar(item.nome),titulo_normalizado(item.local))


def _link_pairs(pa:Pagina,pb:Pagina,aceitar_rotulos=False):
    """Correspondência conservadora: texto + região + ordem de aparição.

    Itens repetidos em áreas diferentes nunca são casados apenas pela palavra
    "Consultar". Se um rótulo for ambíguo, não adivinhar o par.
    """
    list_a=[i for i in pa.itens if i.tipo in ('Opção','Documento') and i.destino]
    list_b=[i for i in pb.itens if i.tipo in ('Opção','Documento') and i.destino]
    by_b=defaultdict(list)
    for i in list_b:by_b[_link_chave(i)].append(i)
    matched=[];used=set()
    for i in list_a:
        key=_link_chave(i)
        candidates=[(j,x) for j,x in enumerate(by_b.get(key,[])) if id(x) not in used]
        if not candidates:continue
        # Quando o rótulo se repete na mesma região, a posição pode ser ambígua.
        # Para evitar redirecionamento falso, só faz o par se houver um candidato
        # ou se dois destinos correspondentes tiverem a mesma rota.
        if len(candidates)>1:
            same=[(j,x) for j,x in candidates if link_equivalente(i.destino,x.destino,pa.url,pb.url)]
            if len(same)!=1:continue
            x=same[0][1]
        else:x=candidates[0][1]
        used.add(id(x));matched.append((i,x))
    # Ícones em <a><img></a> podem ter ALT/ARIA diferentes entre ambientes.
    # Compara seus destinos apenas se o seletor estável identifica um único par.
    remaining_a=[i for i in list_a if i.imagem_link and id(i) not in used and i.seletor]
    a_seletores=defaultdict(list);b_seletores=defaultdict(list)
    for i in remaining_a:a_seletores[i.seletor].append(i)
    for i in list_b:
        if i.imagem_link and id(i) not in used and i.seletor:b_seletores[i.seletor].append(i)
    paired_a={id(x) for x,_ in matched}
    for sel in a_seletores.keys() & b_seletores.keys():
        if len(a_seletores[sel])==len(b_seletores[sel])==1:
            ia,ib=a_seletores[sel][0],b_seletores[sel][0]
            if id(ia) not in paired_a and id(ib) not in used:
                matched.append((ia,ib));used.add(id(ib))
    if aceitar_rotulos:
        paired_a={id(x) for x,_ in matched}
        for ia in list_a:
            if id(ia) in paired_a or not ia.funcao or not ia.estrutura:continue
            candidates=[ib for ib in list_b if id(ib) not in used and ib.tipo==ia.tipo and
                ib.funcao==ia.funcao and ib.estrutura==ia.estrutura and normalizar(ib.local)==normalizar(ia.local) and
                link_equivalente(ia.destino,ib.destino,pa.url,pb.url)]
            if len(candidates)!=1:continue
            ib=candidates[0]
            reverse=[i for i in list_a if id(i) not in paired_a and i.tipo==ib.tipo and i.funcao==ib.funcao and
                i.estrutura==ib.estrutura and normalizar(i.local)==normalizar(ib.local) and
                link_equivalente(i.destino,ib.destino,pa.url,pb.url)]
            if len(reverse)==1:matched.append((ia,ib));paired_a.add(id(ia));used.add(id(ib))
    return matched


def _visuais(p,ia):
    return p.trilha + ([ia.local] if ia.local and ia.local not in ('Conteúdo principal','Página inicial') else [])


def _diff_destino(pa,pb,ia,ib,nome_a,nome_b):
    caminho=' → '.join(dict.fromkeys(_visuais(pa,ia))) or 'Página inicial'
    return {'tipo':'Redirecionamento','categoria':'Links e redirecionamentos',
            'presente_em':nome_a,'nao_identificado_em':nome_b,'pagina':pa.titulo,
            'url_presente':pa.url,'url_comparada':pb.url,'local':ia.local,
            'posicao':ia.posicao,'seletor':ia.seletor,'visivel_texto':ia.visivel_texto,
            'componente_id':ia.componente_id,'secao_id':ia.secao_id,
            'caminho':caminho,'elemento':ia.nome,'destino_a':ia.destino,'destino_b':ib.destino,
            'descricao':f'Na opção "{ia.nome}", localizada em {ia.posicao or "local não identificado"} ({caminho}), '
                        f'o ambiente {nome_a} aponta para {ia.destino}, enquanto {nome_b} aponta para {ib.destino}. '
                        'Apenas os destinos foram comparados; estes dois links NÃO foram percorridos. '
                        'Verifique qual redirecionamento deveria ser utilizado.',
            'situacao':'Destinos diferentes · ramo ignorado'}


def _diff_redir_page(url_a,url_b,final_a,final_b,trilha,nome_a,nome_b):
    return {'tipo':'Redirecionamento','categoria':'Links e redirecionamentos',
            'presente_em':nome_a,'nao_identificado_em':nome_b,'pagina':'Página redirecionada',
            'url_presente':url_a,'url_comparada':url_b,'local':' → '.join(trilha),
            'posicao':'Não determinada','caminho':' → '.join(trilha),
            'elemento':trilha[-1] if trilha else 'Redirecionamento',
            'destino_a':final_a,'destino_b':final_b,
            'descricao':f'Ao abrir esta página, {nome_a} redirecionou para {final_a} e {nome_b} para {final_b}. '
                        'Os destinos não são equivalentes. Nenhuma página de destino foi explorada.',
            'situacao':'Redirecionamentos finais diferentes'}


def agrupar_registros(registros:list[dict])->list[dict]:
    """Agrupa repetição do MESMO elemento no mesmo contexto, com todas as URLs."""
    grupos={}
    for indice,original in enumerate(registros,1):
        r=dict(original);r.setdefault('id_ocorrencia',f'OCO-{indice:07d}')
        tipo=r.get('tipo','')
        # Destinos diferentes não podem ser engolidos por um grupo de mesma etiqueta.
        destinos=(r.get('destino_a',''),r.get('destino_b','')) if r.get('destino_a') or r.get('destino_b') else (tuple(r.get('ordem_a',[])),tuple(r.get('ordem_b',[]))) if tipo=='Ordem' else ()
        key=(tipo,normalizar(r.get('elemento','')),r.get('presente_em',''),
             titulo_normalizado(r.get('posicao','')),titulo_normalizado(r.get('local','')),
             destinos,r.get('texto_a',''),r.get('texto_b',''),r.get('assinatura_a',''),r.get('assinatura_b',''))
        reg=grupos.get(key)
        ocorrencia={'url_presente':r.get('url_presente',''),'url_comparada':r.get('url_comparada',''),
                    'caminho':r.get('caminho',''),'local':r.get('local',''),'seletor':r.get('seletor',''),'componente_id':r.get('componente_id',''),'secao_id':r.get('secao_id','')}
        if not reg:
            reg=dict(r);reg['ocorrencias']=[ocorrencia];reg['ocorrencias_total']=1;reg['registros_individuais']=[dict(r)]
            reg['categoria']=reg.get('categoria') or categoria_item(Item(tipo,'',''))
            grupos[key]=reg
        else:
            reg['registros_individuais'].append(dict(r))
        if ocorrencia not in reg['ocorrencias']:
            reg['ocorrencias'].append(ocorrencia)
            reg['ocorrencias_total']=len(reg['ocorrencias'])
    saida=list(grupos.values())
    for n,r in enumerate(saida,1):
        r['id']=f'DIV-{n:04d}'
        if r['ocorrencias_total']>1:
            r['descricao']+=' Esta ocorrência também aparece em '+str(r['ocorrencias_total']-1)+' outra(s) página(s); consulte a lista de ocorrências.'
    from .taxonomy import enriquecer
    return enriquecer(saida)


def agrupar_referencias(refs:list[dict])->list[dict]:
    """Agrupa referências de imagens repetidas em cabeçalhos/rodapés do portal."""
    grupos={}
    for ref in refs:
        k=(ref.get('tipo',''),ref.get('seletor',''),ref.get('destino_a',''),ref.get('destino_b',''))
        occ={'url_presente':ref.get('url_presente',''),
             'url_comparada':ref.get('url_comparada',''), 'caminho':ref.get('caminho','')}
        if k not in grupos:
            grupos[k]=dict(ref);grupos[k]['ocorrencias']=[occ]
        elif occ not in grupos[k]['ocorrencias']:
            grupos[k]['ocorrencias'].append(occ)
    for r in grupos.values():r['ocorrencias_total']=len(r['ocorrencias'])
    return list(grupos.values())


def _auditar_externos(browser,urls,parar,log,metricas=None):
    """Auditoria mínima em páginas externas iguais nos dois ambientes.

    Não rastreia domínios terceiros e não infere se um conteúdo está correto.
    Acessa no máximo 8 páginas iniciais, depois no máximo 5 links de menu
    do MESMO host por página, apenas para informar se abrem HTML com texto.
    """
    saida=[]
    if not urls:return saida
    ctx=browser.new_context(locale='pt-BR',accept_downloads=False)
    if metricas:ctx.on('request',lambda _:metricas.contagens.update(['requisicoes_navegador']))
    page=ctx.new_page();ja=set()
    try:
        for url,origem in urls[:_MAX_EXTERNOS]:
            if parar.is_set():break
            if url in ja:continue
            ja.add(url)
            p=urlsplit(url)
            result={'url':url,'origem':origem,'status':'Não verificado','opcoes':[]}
            if e_arquivo(url):
                result['status']='Arquivo externo (sem varredura HTML)';saida.append(result);continue
            try:
                r=page.goto(url,wait_until='domcontentloaded',timeout=9000)
                if urlsplit(page.url).netloc!=p.netloc:
                    result['status']='Redirecionamento externo adicional (não seguido)';saida.append(result);continue
                if r and r.status>=400:raise RuntimeError('HTTP '+str(r.status))
                menu=page.evaluate('''() => [...document.querySelectorAll('aside a[href],nav a[href],[role="navigation"] a[href]')]
                  .filter(x=>x.getClientRects().length&&x.innerText.trim())
                  .map(x=>({label:x.innerText.trim().slice(0,90),url:x.href})).slice(0,100)''')
                texto=page.evaluate('() => document.body?.innerText?.trim().length||0')
                result['status']='Página acessível' if texto>50 else 'Página sem conteúdo textual suficiente'
                for link in menu[:_MAX_OPCOES_EXTERNAS]:
                    item={'opcao':link['label'],'destino':link['url'],'situacao':'Não verificado'}
                    if urlsplit(link['url']).netloc!=p.netloc:
                        item['situacao']='Outro domínio (não acessado)';result['opcoes'].append(item);continue
                    if e_arquivo(link['url']):
                        item['situacao']='Arquivo (não verificado)';result['opcoes'].append(item);continue
                    try:
                        if metricas:metricas.contagens['requisicoes_api_externa']+=1
                        res=ctx.request.get(link['url'],timeout=6500,max_redirects=0)
                        if res.status>=400:item['situacao']='HTTP '+str(res.status)
                        elif 300<=res.status<400:item['situacao']='Redireciona (destino não visitado)'
                        elif 'html' not in res.headers.get('content-type','').lower():item['situacao']='Resposta não HTML'
                        else:
                            sample=res.text()[:300000]
                            # Heurística não prova informação correta. Avalia somente presença de texto.
                            stripped=re.sub('<[^>]+>',' ',sample)
                            item['situacao']='Conteúdo HTML presente' if len(re.sub(r'\\s+','',stripped))>60 else 'Possível página vazia'
                    except Exception as exc:item['situacao']='Não verificado: '+str(exc)[:100]
                    result['opcoes'].append(item)
            except Exception as exc:result['status']='Não verificado: '+str(exc)[:120]
            saida.append(result)
    finally:ctx.close()
    return saida


def _salvar_evidencias(browser,registros,evidencias_dir,parar,log,nome_a='PRD',nome_b='DES',metricas=None):
    """Captura duas telas por DIV, claramente identificadas por ambiente.

    A captura correspondente pode mostrar somente a área aproximada; ausência de
    destaque NÃO comprova ausência do elemento. Os dois ramos divergentes não
    são visitados: apenas as páginas onde os links foram encontrados.
    """
    if not evidencias_dir:return
    pasta=Path(evidencias_dir);pasta.mkdir(parents=True,exist_ok=True)
    context=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},
                                service_workers='block',accept_downloads=False)
    if metricas:context.on('request',lambda _:metricas.contagens.update(['requisicoes_navegador']))
    page=context.new_page();qtd=0;inicio_capturas=time.monotonic()
    try:
        for r in registros:
            if qtd>=_MAX_EVIDENCIAS or time.monotonic()-inicio_capturas>240 or parar.is_set():break
            urls={r.get('presente_em'):r.get('url_presente'),
                  r.get('nao_identificado_em'):r.get('url_comparada')}
            if not all(urls.get(n) for n in (nome_a,nome_b)):continue
            result={};mark={}
            selector=r.get('seletor') or ''
            referencia_y=None
            for env in (r.get('presente_em'),r.get('nao_identificado_em')):
                url=urls[env]
                try:
                    response=page.goto(url,wait_until='domcontentloaded',timeout=12000)
                    if response and response.status>=400:raise RuntimeError('HTTP '+str(response.status))
                    page.wait_for_timeout(450)
                    found=False
                    if selector:
                        loc=page.locator(selector).first
                        if loc.count() and loc.is_visible(timeout=1300):
                            loc.scroll_into_view_if_needed(timeout=1300)
                            loc.evaluate('''x => {x.style.outline='4px solid #f4a646';
                                x.style.outlineOffset='3px';}''')
                            found=True
                            if referencia_y is None:
                                referencia_y=page.evaluate('() => window.scrollY')
                    elif referencia_y is not None:
                        page.evaluate('(y) => window.scrollTo(0,y)',referencia_y)
                        page.wait_for_timeout(200)
                    filename=f'{r["id"]}_{env}.png'
                    page.screenshot(path=str(pasta/filename),timeout=9000,
                                    animations='disabled',full_page=False)
                    result[env]=pasta.name+'/'+filename
                    mark[env]='Elemento localizado pelo seletor DOM' if found else 'Área da página; elemento não localizado nesta captura'
                except Exception as exc:
                    log('[Evidência] '+r['id']+' '+env+': '+str(exc)[:90])
            if result:
                r['evidencias']=result
                r['marcacoes']=mark
                r['evidencia']=next(iter(result.values()))
                qtd+=1
    finally:context.close()

def executar_pareado(url_a,url_b,nome_a,nome_b,parar,log,progresso,site_nome='',evidencias_dir=None, _preparar_contextos=None, auditar_externos=False, ambiente_desatualizado='', checkpoint=None, verificar_cliques=False, varredura_inteligente=False):
    from playwright.sync_api import sync_playwright
    metricas=Metricas();metricas.parar=parar;inteligencia=Inteligencia(metricas);documentos=Documentos(metricas,parar)
    documentos_relatorio=[]
    andamento={'etapa':'inicio','par_atual':0,'ultimo_par_processado':0}
    base_a,base_b=validacao_inicial(url_a,url_b)
    fila=deque([(base_a,base_b,['Página inicial'])])
    pares_enfileirados={(base_a,base_b)}
    visitados=set();paginas_a={};paginas_b={};brutos=[];falhas=[];pendencias=[];refs=[]
    excluded=Counter();externos=[];avisos_coleta=[];consecutivos=0;parada='';inicio=time.monotonic()
    eventos=[];editoriais=[];cliques_testados=0;MAX_CLIQUES=12;modo_defasado=ambiente_desatualizado if ambiente_desatualizado in (nome_a,nome_b) else ''
    def snapshot():
        return {**metricas.temporal(),'site_nome':site_nome,'ambientes':{nome_a:base_a,nome_b:base_b},
            'paginas':{nome_a:len(paginas_a),nome_b:len(paginas_b)},
            'andamento':dict(andamento),'brutos':brutos,'variacoes_editoriais':editoriais,'falhas':falhas,
            'modo_varredura':'inteligente' if varredura_inteligente else 'atual',
            'otimizacao':inteligencia.resultado(),'documentos_verificados':documentos_relatorio,
            'metricas':metricas.resultado(),'registros_editoriais':editoriais,
            'eventos_diagnostico':eventos,'pendencias':pendencias,
            'meta_varredura':{nome_a:{'visitadas':len(visitados),'pendentes':len(fila),'motivo_parada':parada or 'Execução ainda em andamento','referencias_excluidas':dict(excluded)},
              nome_b:{'visitadas':len(visitados),'pendentes':len(fila),'motivo_parada':parada or 'Execução ainda em andamento','referencias_excluidas':{}}},
            'ambiente_desatualizado':modo_defasado}
    with sync_playwright() as pw:
        try:
            browser=pw.chromium.launch(headless=True)
        except Exception:
            # Fallback para Linux de desenvolvimento, quando os binários do Playwright
            # ainda não foram instalados. O instalador Windows baixa Chromium normalmente.
            executable=shutil.which('chromium') or shutil.which('chromium-browser')
            if not executable:raise
            browser=pw.chromium.launch(headless=True,executable_path=executable,args=['--no-sandbox'])
        ctx_a=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},service_workers='block',accept_downloads=False)
        ctx_b=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},service_workers='block',accept_downloads=False)
        def contar_requisicao(_req):metricas.contagens['requisicoes_navegador']+=1
        for contexto in (ctx_a,ctx_b):contexto.on('request',contar_requisicao)
        if _preparar_contextos:
            _preparar_contextos(ctx_a,ctx_b)
        page_a=ctx_a.new_page();page_b=ctx_b.new_page()
        try:
            while fila and not parar.is_set():
                if len(visitados)>=MAX_URLS_SEGURANCA:
                    parada='Limite preventivo interno de páginas alcançado';break
                if time.monotonic()-inicio>MAX_MINUTOS_SEGURANCA*60:
                    parada='Tempo máximo preventivo alcançado';break
                if consecutivos>=MAX_FALHAS_CONSECUTIVAS:
                    parada='Muitas falhas consecutivas';break
                ua,ub,trilha=fila.popleft()
                if (ua,ub) in visitados:continue
                visitados.add((ua,ub))
                if e_arquivo(ua) or e_arquivo(ub):
                    excluded['Arquivos não tratados como páginas HTML']+=1
                    if len(eventos)<600:eventos.append({'par':len(visitados),'tipo':'ARQUIVO_NAO_HTML','urls':{nome_a:ua,nome_b:ub},'trilha':trilha,'resultado':'Ignorado sem incrementar falhas'})
                    consecutivos=0;continue
                andamento.update(etapa='navegacao',par_atual=len(visitados),url_a=ua,url_b=ub)
                log('[PARES] '+str(len(visitados))+': '+ ' → '.join(trilha[-3:]))
                statuses=[];pares=[];houve_documento=False
                for env,page,url in ((nome_a,page_a,ua),(nome_b,page_b,ub)):
                    try:
                        with metricas.medir('navegacao'):response=_abrir(page,url)
                        if response and response.status>=400:raise RuntimeError('HTTP '+str(response.status))
                        statuses.append((getattr(response,'url',None) or page.url,None))
                    except Exception as ex:
                        msg=str(ex)[:300]
                        # Downloads não devem provocar 15 falhas consecutivas.
                        if 'Download is starting' in msg or 'download is starting' in msg.lower():
                            excluded['Downloads tratados fora da navegação HTML']+=1
                            houve_documento=True
                            statuses.append((url,'Arquivo para download'))
                        else:
                            falhas.append({'ambiente':env,'url':url,'erro':msg,**classificar_erro(msg)})
                            if len(eventos)<600:eventos.append({'par':len(visitados),'ambiente':env,'url':url,'trilha':trilha,'erro':msg,**classificar_erro(msg)})
                            statuses.append((url,msg))
                final_a,err_a=statuses[0];final_b,err_b=statuses[1]
                if err_a or err_b:
                    if houve_documento:
                        consecutivos=0
                        if len(eventos)<600:eventos.append({'par':len(visitados),'tipo':'DOWNLOAD_DE_DOCUMENTO',
                          'urls':{nome_a:ua,nome_b:ub},'resultado':'Separado da navegação HTML; não conta como falha consecutiva'})
                    else:consecutivos+=1
                    pendencias.append({'ambiente':nome_a+' / '+nome_b,'url':ua,'pagina':'Página não comparada',
                        'motivo':('Download de documento fora da navegação HTML; não prova falha do site.' if houve_documento else
                                  'Acesso a pelo menos um dos ambientes falhou. Não há evidência de conteúdo ausente.'),
                        'caminho':' → '.join(trilha),'url_b':ub})
                    continue
                if not link_equivalente(final_a,final_b,base_a,base_b):
                    brutos.append(_diff_redir_page(ua,ub,final_a,final_b,trilha,nome_a,nome_b))
                    consecutivos=0
                    continue
                if not permitido(final_a,base_a) or not permitido(final_b,base_b):
                    # Ambos podem redirecionar para exatamente a mesma página externa.
                    if final_a==final_b:externos.append((final_a,' → '.join(trilha)))
                    else:brutos.append(_diff_redir_page(ua,ub,final_a,final_b,trilha,nome_a,nome_b))
                    consecutivos=0
                    continue
                andamento['etapa']='extracao'
                try:
                    if varredura_inteligente:
                        pa,pb=inteligencia.preparar_par(page_a,page_b,ua,ub,trilha,log,base_a,base_b,
                            modo_defasado,_extrair_page,parar)
                        for pag in (pa,pb):
                            for item in pag.itens:
                                if item.posicao in ('Menu de navegação','Menu lateral','Cabeçalho','Rodapé'):item.natureza='estrutura'
                                if item.destino and e_arquivo(item.destino):item.tipo='Documento'
                    else:
                        pa=_extrair_page(page_a,ua,trilha,log,metricas=metricas)
                        pb=_extrair_page(page_b,ub,trilha,log,metricas=metricas)
                except Exception as ex:
                    msg='Falha de extração: '+str(ex)[:160]
                    falhas.append({'ambiente':'AMBOS','url':ua,'erro':msg,**classificar_erro(msg)})
                    if len(eventos)<600:eventos.append({'par':len(visitados),'ambiente':'AMBOS','url':ua,'trilha':trilha,'erro':msg,**classificar_erro(msg)})
                    consecutivos+=1
                    continue
                consecutivos=0
                for env,pag in ((nome_a,pa),(nome_b,pb)):
                    if not pag.coleta.get('estavel') or pag.coleta.get('rolagem_limitada'):
                        avisos_coleta.append({'ambiente':env,'url':pag.url})
                chave=(ua,ub)
                paginas_a[ua]=pa;paginas_b[ub]=pb
                andamento['etapa']='comparacao'
                # 1. Compara texto/imagens/opções SEM navegar nas diferenças.
                itens_a,itens_b,pendencias_imgs=_alinhamento_de_componentes(pa,pb,base_a,base_b)
                if modo_defasado:
                    for v in pendencias_imgs:
                        if v.get('natureza')=='editorial':
                            editoriais.append({'tipo':'Imagem','presente_em':nome_a,'elemento':v.get('elemento',''),
                                'url_presente':pa.url,'url_comparada':pb.url})
                        else:refs.append(v)
                else:refs.extend(pendencias_imgs)
                with metricas.medir('comparacao'):
                    comps=(inteligencia.comparar(itens_a,itens_b,pa,pb,nome_a,nome_b,base_a,base_b) if varredura_inteligente else
                           comparacao(itens_a,itens_b,pa,pb,nome_a,nome_b))
                from .adaptive import decidir_releitura,cobertura_nao_piorou
                with metricas.medir('sonda_releitura'):
                    motivos=decidir_releitura(page_a,page_b,pa,pb,comps,parar)
                if motivos and not parar.is_set():
                    log('[Coleta] Segunda leitura: '+', '.join(motivos)+' — '+ua[:85])
                    inicio_releitura=time.perf_counter()
                    registro={'url_a':ua,'url_b':ub,'motivos':motivos,'diagnostico_modificado':False,
                              'adotada':False,'diferencas_antes':len(comps),
                              'primeira_coleta':{'a':asdict(pa),'b':asdict(pb),'divergencias':comps}}
                    try:
                        pa2=_extrair_page(page_a,ua,trilha,log,metricas=metricas)
                        pb2=_extrair_page(page_b,ub,trilha,log,metricas=metricas)
                        ai,bi,pend2=_alinhamento_de_componentes(pa2,pb2,base_a,base_b)
                        comps2=(inteligencia.comparar(ai,bi,pa2,pb2,nome_a,nome_b,base_a,base_b) if varredura_inteligente else comparacao(ai,bi,pa2,pb2,nome_a,nome_b))
                        registro['diferencas_depois']=len(comps2)
                        registro['segunda_coleta']={'a':asdict(pa2),'b':asdict(pb2),'divergencias':comps2}
                        if cobertura_nao_piorou(pa,pa2) and cobertura_nao_piorou(pb,pb2):
                            registro['diagnostico_modificado']=comps2!=comps
                            registro['adotada']=True
                            pa,pb,comps=pa2,pb2,comps2
                            paginas_a[ua]=pa;paginas_b[ub]=pb
                            refs.extend(v for v in pend2 if not modo_defasado or v.get('natureza')!='editorial')
                            omitidas_antes=len(inteligencia.omissoes)
                            inteligencia.omissoes[:]=[x for x in inteligencia.omissoes if not (x.get('categoria')=='Notícia de template repetido' and x['url_a']==ua and x['url_b']==ub)]
                            metricas.contagens['preparacoes_profundas_evitadas']-=2*(omitidas_antes-len(inteligencia.omissoes))
                        else:registro['limitacao']='Primeira coleta preservada: releitura menos completa ou instável.'
                    except Exception as ex:
                        registro['erro']=str(ex)[:200]
                        log('[Coleta] Releitura não concluída: '+str(ex)[:100])
                    finally:
                        registro['duracao_segundos']=round(time.perf_counter()-inicio_releitura,6)
                        metricas.releituras.append(registro)
                        metricas.tempos['segunda_leitura']+=registro['duracao_segundos']
                        metricas.contagens['operacoes_segunda_leitura']+=1
                        metricas.contagens['releituras_com_diagnostico_modificado']+=int(registro['diagnostico_modificado'])
                else:metricas.contagens['releituras_dispensadas_dom_estavel' if not motivos else 'releituras_nao_executadas_cancelamento']+=1
                if varredura_inteligente:
                    for pag in (pa,pb):
                        for item in pag.itens:
                            if item.posicao in ('Menu de navegação','Menu lateral','Cabeçalho','Rodapé'):item.natureza='estrutura'
                itens_a,itens_b,_=_alinhamento_de_componentes(pa,pb,base_a,base_b)
                comps,editoriais_atuais=separar_editoriais(comps,pa,pb,itens_a,itens_b,(nome_a,nome_b),modo_defasado)
                editoriais.extend(editoriais_atuais)
                brutos.extend(comps)
                if varredura_inteligente:
                    for estrutura in inteligencia.estruturas:
                        if (estrutura['url_a'],estrutura['url_b'])==(ua,ub):
                            brutos.append({'tipo':'Estrutura editorial','categoria':'Estrutura de Notícias',
                                'elemento':'Seção editorial','presente_em':nome_a,'nao_identificado_em':nome_b,
                                'url_presente':ua,'url_comparada':ub,'caminho':' → '.join(trilha),
                                'descricao':estrutura['motivo'],'situacao':'Estrutura para revisão'})
                novos_icones,novos_layouts=comparar_visuais(page_a,page_b,pa,pb,nome_a,nome_b,bool(modo_defasado))
                for reg in novos_icones:
                    encontrados=[i for i in pa.itens if i.tipo=='Opção' and normalizar(i.nome)==normalizar(reg['elemento'])]
                    if len(encontrados)==1:
                        reg['seletor']=encontrados[0].seletor
                        reg['posicao']=encontrados[0].posicao
                        reg['visivel_texto']=encontrados[0].visivel_texto
                        reg['componente_id']=encontrados[0].componente_id
                        reg['secao_id']=encontrados[0].secao_id
                brutos.extend(novos_icones)
                refs.extend(novos_layouts)
                ordens=diferencas_de_ordem(pa,pb,nome_a,nome_b)
                if modo_defasado:
                    # Ordem de notícias pode variar naturalmente entre bases antigas.
                    # Menus e listas institucionais continuam no relatório principal.
                    ordens=[d for d in ordens if d.get('natureza')!='editorial' and not any(t in normalizar(d.get('local','')) for t in ('noticia','notícia','publicaç'))]
                brutos.extend(ordens)
                andamento['etapa']='links_documentos'
                # 2. Compara links pareados por nome/contexto.
                with metricas.medir('links'):pares_links=_link_pairs(pa,pb,aceitar_rotulos=varredura_inteligente)
                if verificar_cliques and cliques_testados<MAX_CLIQUES:
                    for ca,cb in escolher_candidatos(pares_links,base_a,base_b,limite=min(2,MAX_CLIQUES-cliques_testados)):
                        # A inspeção só é executada quando o usuário opta por ela.
                        cliques_testados+=1
                        with metricas.medir('cliques'):candidato=verificar_par(browser,pa,pb,ca,cb,nome_a,nome_b,base_a,base_b,log)
                        if candidato:brutos.append(candidato)
                if varredura_inteligente:
                    pareados={id(i) for par in pares_links for i in par}
                    for env,pag in ((nome_a,pa),(nome_b,pb)):
                        for item in pag.itens:
                            base=base_a if env==nome_a else base_b
                            if item.destino and permitido(item.destino,base) and id(item) not in pareados and (env,item.destino) not in inteligencia.nao_pareadas:
                                inteligencia.nao_pareadas.add((env,item.destino))
                                inteligencia.omissoes.append({'categoria':'Página sem par inequívoco','elemento':item.nome,
                                    'url_a':item.destino if env==nome_a else '', 'url_b':item.destino if env==nome_b else '',
                                    'quantidade_paginas':1,'motivo':'Link exclusivo ou ambíguo registrado; conteúdo profundo sem par não foi comparado. Não presume ausência de conteúdo.'})
                            if item.destino and e_arquivo(item.destino) and id(item) not in pareados:
                                documentos_relatorio.append({'classificacao':'Verificação inconclusiva','ambiente':env,
                                    'elemento':item.nome,'destino':item.destino,'motivo':'Documento sem par inequívoco; não acessado'})
                for ia,ib in pares_links:
                    try:da,db=url_limpa(ia.destino),url_limpa(ib.destino)
                    except (TypeError,ValueError):continue
                    if referencia_invalida(da) or referencia_invalida(db):
                        excluded['Referências codificadas não navegáveis']+=1;continue
                    if varredura_inteligente and (e_arquivo(da) or e_arquivo(db)):
                        resultado_doc=documentos.comparar(ia,ib,base_a,base_b)
                        documentos_relatorio.append({**resultado_doc,'pagina_a':pa.url,'pagina_b':pb.url})
                    if not link_equivalente(da,db,base_a,base_b):
                        if modo_defasado and (item_editorial(ia,pa) or item_editorial(ib,pb)):
                            editoriais.append({'tipo':'Link editorial','elemento':ia.nome,
                               'presente_em':nome_a,'url_presente':pa.url,'url_comparada':pb.url})
                            continue
                        # REGISTRA e PARA AQUI. Não enfileira nem abre o destino.
                        brutos.append(_diff_destino(pa,pb,ia,ib,nome_a,nome_b))
                        continue
                    if e_arquivo(da) or e_arquivo(db):
                        excluded['Documentos vinculados (não percorridos como HTML)']+=1
                        continue
                    if permitido(da,base_a) and permitido(db,base_b):
                        if (da,db) not in visitados and (da,db) not in pares_enfileirados:
                            fila.append((da,db,(trilha+[ia.nome])[-12:]))
                            pares_enfileirados.add((da,db))
                        else:metricas.contagens['urls_duplicadas']+=1
                    elif (urlsplit(da).netloc!=urlsplit(base_a).netloc and
                          urlsplit(db).netloc!=urlsplit(base_b).netloc):
                        if da==db and not e_arquivo(da):externos.append((da,' → '.join(trilha+[ia.nome])))
                    # PDFs/planilhas permanecem somente como referências (sem abrir no crawler).
                andamento.update(etapa='par_processado',ultimo_par_processado=len(visitados))
                log(f'[{nome_a}/{nome_b}] {len(paginas_a)} pares, {len(brutos)} ocorrências preliminares')
                progresso(min(.92,len(visitados)/max(1,len(visitados)+len(fila))*.85))
                if checkpoint and len(visitados)%20==0:
                    try:checkpoint(snapshot())
                    except Exception as ex:log('[Diagnóstico] Checkpoint não salvo: '+str(ex)[:110])
                time.sleep(.04)
            if parar.is_set():parada='Interrompida pelo usuário (resultado parcial preservado)'
            completos=not bool(fila or parada or falhas or pendencias or avisos_coleta or inteligencia.omissoes or (varredura_inteligente and documentos_relatorio))
            if varredura_inteligente and not (paginas_a and paginas_b):completos=False
            if parada:log('Varredura parcial: '+parada)
            andamento['etapa']='processamento_final'
            if checkpoint:
                try:checkpoint(snapshot())
                except Exception as ex:log('[Diagnóstico] Checkpoint final não salvo: '+str(ex)[:110])
            metricas.tempos['varredura']=time.perf_counter()-metricas.inicio
            inicio_final=time.perf_counter()
            andamento['etapa']='processamento_final'
            divergencias=agrupar_registros(brutos)
            if paginas_a and paginas_b and not parar.is_set():
                with metricas.medir('capturas'):_salvar_evidencias(browser,divergencias,evidencias_dir,parar,log,nome_a,nome_b,metricas=metricas)
            progresso(.94)
            with metricas.medir('auditoria'):
                externos_result=_auditar_externos(browser,externos,parar,log,metricas=metricas) if auditar_externos and not parar.is_set() else []
            if parar.is_set():
                parada='Interrompida pelo usuário (resultado parcial preservado)';completos=False
                if varredura_inteligente and checkpoint:
                    try:checkpoint(snapshot())
                    except Exception as ex:log('[Diagnóstico] Checkpoint final não salvo: '+str(ex)[:110])
            progresso(.98)
            metricas.contagens['paginas_visitadas']=metricas.contagens['operacoes_navegacao']
            metricas.contagens['paginas_coletadas']=len(paginas_a)+len(paginas_b)
            metricas.contagens['pares_documentos_avaliados']=len(documentos.resultados)
            metas={nome_a:{'visitadas':len(visitados),'pendentes':len(fila),'motivo_parada':parada,
                           'referencias_excluidas':dict(excluded)},
                   nome_b:{'visitadas':len(visitados),'pendentes':len(fila),'motivo_parada':parada,
                           'referencias_excluidas':{}}}
            situacao='inconclusivo' if not paginas_a or not paginas_b else ('concluido' if completos else 'parcial')
            if parada and len(eventos)<600:eventos.append({'tipo':'INTERRUPCAO','par':len(visitados),'motivo':parada,
                'falhas_consecutivas':consecutivos,'pares_pendentes':len(fila)})
            metricas.tempos['processamento_final']=time.perf_counter()-inicio_final
            metricas.contagens['pares_comparados']=len(paginas_a)
            metricas.contagens['pares_pendentes']=len(fila)
            metricas.contagens['preparacoes_profundas']=metricas.contagens['operacoes_preparacao']
            metricas.finalizar()
            return {**metricas.temporal(),'estado_execucao':'interrompido' if parar.is_set() else 'finalizado','andamento':dict(andamento),
                'media_segundos_por_par':round(metricas.duracao/len(paginas_a),6) if paginas_a else None,
                'requisicoes_por_par':round(metricas.resultado()['contagens']['requisicoes_total']/len(paginas_a),3) if paginas_a else None,
                'versao':'1.5','ambientes':{nome_a:base_a,nome_b:base_b},
                'paginas':{nome_a:len(paginas_a),nome_b:len(paginas_b)},
                'completo':{nome_a:completos,nome_b:completos},
                'meta_varredura':metas,'situacao_analise':situacao,
                'modo_varredura':'inteligente' if varredura_inteligente else 'atual',
                'metricas':metricas.resultado(),'otimizacao':inteligencia.resultado(),
                'documentos_verificados':documentos_relatorio,
                'registros_editoriais':editoriais,
                'falhas':falhas,'eventos_diagnostico':eventos,'ambiente_desatualizado':modo_defasado,
                'sinais_desatualizacao':sinais_extraidos(paginas_a,nome_a)+sinais_extraidos(paginas_b,nome_b),
                'variacoes_dados':agrupar_variacoes(editoriais,modo_defasado),
                'itens_editoriais_agrupados':len(editoriais),'avisos_tecnicos':_avisos(falhas,metas)+([
                    {'ambiente':'PRD/DES','tipo':'Coleta dinâmica possivelmente incompleta',
                     'quantidade':len(avisos_coleta),'exemplos':[x['url'] for x in avisos_coleta[:8]]}]
                    if avisos_coleta else []),
                'pendencias':pendencias,'referencias_pendentes':agrupar_referencias(refs),
                'divergencias':divergencias,'verificacoes_externas':externos_result,
                'verificacao_externa_ativa':bool(auditar_externos),
                'verificacao_cliques_ativa':bool(verificar_cliques),
                'cliques_testados':cliques_testados,
                'ocorrencias_brutas':len(brutos)+len(editoriais),
                'site_nome':(site_nome or inferir_site({'@inicio':next(iter(paginas_a.values()),None)},
                            {'@inicio':next(iter(paginas_b.values()),None)},base_a)).strip()[:120],
                'limite_paginas':None,'profundidade':None}
        finally:
            ctx_a.close();ctx_b.close();browser.close()
