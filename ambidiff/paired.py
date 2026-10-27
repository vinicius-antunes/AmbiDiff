"""Varredura pareada (v1.5).

Uma opção só é seguida quando seus destinos são equivalentes entre ambientes.
Diferença de destino encerra SOMENTE o ramo daquela opção. Não faz auditoria
no conteúdo para decidir qual destino está correto.
"""
from __future__ import annotations
from collections import Counter, deque, defaultdict
from functools import lru_cache
from dataclasses import replace, asdict
from pathlib import Path
import re
import os
import shutil
import time
import unicodedata
from urllib.parse import urlsplit, urljoin, unquote

from .smart import Metricas, Inteligencia,estrutura_funcional
from .documents import Documentos
from .intelligence import separar_editoriais,agrupar_variacoes,sinais_extraidos,item_editorial
from .diagnostics import classificar_erro
from .visual import comparar_visuais
from .functional import escolher_candidatos,verificar_par
from .core import (ARQUIVOS, MAX_URLS_SEGURANCA,
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
    try:return _e_arquivo(url)
    except (TypeError,ValueError):return False


@lru_cache(maxsize=8192)
def _e_arquivo(url: str) -> bool:
    p=urlsplit(url)
    # Liferay publica muitos PDFs sem extensão na URL. Não são páginas HTML.
    if re.search(r'\.(?:svg|png|jpe?g|gif|ico|webp)(?:/|$)',p.path,re.I):return False
    if re.search(r'^/documents/d/[^/]+/[^/]+',unquote(p.path),re.I):return True
    return any(re.search(re.escape(ext)+r'(?:/|$)',unquote(p.path),re.I) for ext in ARQUIVOS)


def link_equivalente(url_a:str,url_b:str,base_a:str,base_b:str)->bool:
    try:return _link_equivalente(url_a,url_b,base_a,base_b)
    except (ValueError,TypeError,AttributeError):return False


@lru_cache(maxsize=8192)
def _link_equivalente(url_a:str,url_b:str,base_a:str,base_b:str)->bool:
    """Ignora SOMENTE a troca de host entre os dois ambientes na MESMA rota.

    URLs externas devem ser iguais. Rotas internas e parâmetros distintos
    representam divergência de destino (ainda que duas páginas possam ser iguais).
    """
    if urlsplit(url_a).fragment!=urlsplit(url_b).fragment:return False
    a,b=url_limpa(url_a),url_limpa(url_b)
    pa,pb,ba,bb=map(urlsplit,(a,b,base_a,base_b))
    int_a=pa.netloc==ba.netloc
    int_b=pb.netloc==bb.netloc
    # URLs literalmente iguais (mesmo host e rota) nunca são divergência.
    if a == b: return True
    if int_a and int_b:
        root_a=ba.path.rstrip('/')
        root_b=bb.path.rstrip('/')
        path_a='/' if root_a and pa.path.rstrip('/')==root_a else pa.path[len(root_a):] if root_a and pa.path.startswith(root_a+'/') else pa.path
        path_b='/' if root_b and pb.path.rstrip('/')==root_b else pb.path[len(root_b):] if root_b and pb.path.startswith(root_b+'/') else pb.path
        return (path_a or '/',pa.query)==(path_b or '/',pb.query)
    if int_a!=int_b:return False
    return a==b



def imagem_equivalente(url_a:str,url_b:str,base_a:str,base_b:str)->bool:
    try:return _imagem_equivalente(url_a,url_b,base_a,base_b)
    except (ValueError,TypeError):return False


def _imagem_equivalente(url_a:str,url_b:str,base_a:str,base_b:str)->bool:
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
    metricas.tempos['espera_carregamento']+=resumo.get('espera_carregamento_segundos',0)
    if resumo.get('espera_reduzida'):metricas.contagens['preparacoes_com_espera_reduzida']+=1
    inicio_extracao=time.perf_counter()
    if not resumo['estavel'] or resumo['rolagem_limitada']:
        log('[Coleta] Página com estabilidade limitada: '+url[:100])
    for tentativa in range(2):
        try:
            dados=page.evaluate(JS_EXTRAIR)
            if not isinstance(dados,dict) or not dados.get('itens'):raise RuntimeError('DOM vazio ou extração incompleta')
            break
        except Exception:
            if tentativa or (metricas.parar and metricas.parar.is_set()):raise
            metricas.contagens['tentativas_extracao_adicionais']+=1
            log('[Coleta] Nova tentativa controlada de extração: '+url[:100])
            page.wait_for_timeout(200)
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
    resumo['componentes_restritos']=dados.get('componentes_restritos',[])
    resumo['nome_site']=dados.get('nome_site','')
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


def _link_pairs(pa:Pagina,pb:Pagina,aceitar_rotulos=False,base_a=None,base_b=None):
    """Correspondência conservadora: texto + região + ordem de aparição.

    Itens repetidos em áreas diferentes nunca são casados apenas pela palavra
    "Consultar". Se um rótulo for ambíguo, não adivinhar o par.
    """
    base_a=base_a or pa.url;base_b=base_b or pb.url
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
                ib.funcao==ia.funcao and estrutura_funcional(ib.estrutura)==estrutura_funcional(ia.estrutura) and normalizar(ib.local)==normalizar(ia.local) and
                link_equivalente(ia.destino,ib.destino,base_a,base_b)]
            if len(candidates)!=1:continue
            ib=candidates[0]
            reverse=[i for i in list_a if id(i) not in paired_a and i.tipo==ib.tipo and i.funcao==ib.funcao and
                estrutura_funcional(i.estrutura)==estrutura_funcional(ib.estrutura) and normalizar(i.local)==normalizar(ib.local) and
                link_equivalente(i.destino,ib.destino,base_a,base_b)]
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
             destinos,r.get('referencia',''),r.get('texto_a',''),r.get('texto_b',''),r.get('assinatura_a',''),r.get('assinatura_b',''))
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
    """Compatibilidade: apenas HEAD, nunca extrair conteúdo ou explorar links."""
    from .destinations import Destinos
    checker=Destinos(metricas or Metricas(),parar,externos=True)
    return [{'url':url,'origem':origem,'status':checker.conferir(url)['classificacao'],'opcoes':[]}
            for url,origem in urls[:_MAX_EXTERNOS] if not parar.is_set()]


def _salvar_evidencias(browser,registros,evidencias_dir,parar,log,nome_a='PRD',nome_b='DES',metricas=None):
    """Captura duas telas por DIV, claramente identificadas por ambiente.

    A captura correspondente pode mostrar somente a área aproximada; ausência de
    destaque NÃO comprova ausência do elemento. Os dois ramos divergentes não
    são visitados: apenas as páginas onde os links foram encontrados.
    """
    if not evidencias_dir:return
    pasta=Path(evidencias_dir);pasta.mkdir(parents=True,exist_ok=True)
    contexts={};pages={};atuais={};cache={};sondas={}
    origens={(urlsplit(r.get(k,'')).scheme,urlsplit(r.get(k,'')).netloc) for r in registros for k in ('url_presente','url_comparada') if r.get(k)}
    def filtro_captura(route):
        req=route.request;p=urlsplit(req.url)
        from .documents import ACOES_ESCRITA
        if req.method not in ('GET','HEAD','OPTIONS') or ACOES_ESCRITA.search(unquote(req.url)) or (req.is_navigation_request() and (p.scheme,p.netloc) not in origens):route.abort()
        else:route.continue_()
    for env in (nome_a,nome_b):
        context=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},service_workers='block',accept_downloads=False)
        contexts[env]=context
        if metricas:context.on('request',lambda _:metricas.contagens.update(['requisicoes_navegador']))
        context.route('**/*',filtro_captura);pages[env]=context.new_page()
    qtd=0;inicio_capturas=time.monotonic()
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
                url=urls[env];page=pages[env]
                try:
                    from .adaptive import sondar
                    atual=sondar(page) if atuais.get(env)==url else {}
                    anterior=sondas.get(env,{})
                    seguro=bool(atual and anterior and atual['versao']==anterior['versao'] and atual['pronto'] and not any(atual[k] for k in ('scripts','lazy','abas','carregando','imagens_pendentes')))
                    key=(env,url,selector,referencia_y)
                    if seguro and key in cache:
                        result[env],mark[env],y=cache[key]
                        if referencia_y is None:referencia_y=y
                        if metricas:metricas.contagens['capturas_reutilizadas']+=1
                        continue
                    if not seguro:
                        response=page.goto(url,wait_until='domcontentloaded',timeout=12000)
                        if response and response.status>=400:raise RuntimeError('HTTP '+str(response.status))
                        page.wait_for_timeout(450);atuais[env]=url
                        cache={k:v for k,v in cache.items() if k[0]!=env}
                        if metricas:metricas.contagens['navegacoes_evidencias']+=1
                    page.evaluate('''() => {document.querySelectorAll('[data-ambidiff-outline]').forEach(x=>{x.style.outline=x.dataset.ambidiffOutline;x.style.outlineOffset=x.dataset.ambidiffOffset;delete x.dataset.ambidiffOutline;delete x.dataset.ambidiffOffset;});window.scrollTo(0,0);}''')
                    found=False
                    if selector:
                        loc=page.locator(selector).first
                        if loc.count() and loc.is_visible(timeout=1300):
                            loc.scroll_into_view_if_needed(timeout=1300)
                            loc.evaluate('''x => {x.dataset.ambidiffOutline=x.style.outline;x.dataset.ambidiffOffset=x.style.outlineOffset;x.style.outline='4px solid #f4a646';
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
                    if metricas:metricas.contagens['capturas_geradas']+=1
                    result[env]=pasta.name+'/'+filename
                    mark[env]='Elemento localizado pelo seletor DOM' if found else 'Área da página; elemento não localizado nesta captura'
                    sondas[env]=sondar(page)
                    cache[key]=(result[env],mark[env],referencia_y)
                except Exception as exc:
                    log('[Evidência] '+r['id']+' '+env+': '+str(exc)[:90])
            if result:
                if metricas:metricas.contagens['referencias_evidencias']+=len(result)
                r['evidencias']=result
                r['marcacoes']=mark
                r['evidencia']=next(iter(result.values()))
                qtd+=1
    finally:
        for context in contexts.values():context.close()

def executar_pareado(url_a,url_b,nome_a,nome_b,parar,log,progresso,site_nome='',evidencias_dir=None, _preparar_contextos=None, auditar_externos=False, ambiente_desatualizado='', checkpoint=None, verificar_cliques=False, varredura_inteligente=False,observador=None,retomada=None,estrategia=None,orcamento_minutos=None):
    from playwright.sync_api import sync_playwright
    metricas=Metricas();metricas.parar=parar;inteligencia=Inteligencia(metricas);documentos=Documentos(metricas,parar,permitir_range=False,observacao_por_execucao=True)
    from .destinations import Destinos
    destinos=Destinos(metricas,parar,(url_a,url_b),externos=auditar_externos)
    verificacoes_destinos=[]
    resultados_funcionais=[]
    diferencas_esteticas=[]
    documentos_relatorio=[]
    from .core import _url_limpa
    cache_inicial=_url_limpa.cache_info();equiv_inicial=_link_equivalente.cache_info()
    pares_falhos=set()
    andamento={'etapa':'inicio','par_atual':0,'ultimo_par_processado':0}
    base_a,base_b=validacao_inicial(url_a,url_b)
    from .frontier import Fila
    fila=Fila([(base_a,base_b,['Página inicial'])])
    pares_enfileirados={(base_a,base_b)}
    visitados=set();paginas_a={};paginas_b={};brutos=[];falhas=[];pendencias=[];refs=[]
    excluded=Counter();externos=[];avisos_coleta=[];consecutivos=0;parada='';inicio=time.monotonic()
    eventos=[];editoriais=[];cliques_testados=0;MAX_CLIQUES=12;modo_defasado=ambiente_desatualizado if ambiente_desatualizado in (nome_a,nome_b) else ''
    from .strategy import Escopo,grupo_editorial
    estado=None
    if retomada:
        from .checkpoints import validar
        with metricas.medir('checkpoint_recuperacao_validacao'):estado=validar(retomada,(base_a,base_b))
    anterior=estado['configuracao'] if estado else {}
    estrategia=estrategia if estrategia is not None else anterior.get('estrategia','dinamica')
    orcamento_minutos=orcamento_minutos if orcamento_minutos is not None else anterior.get('orcamento_minutos',0)
    escopo=Escopo(estrategia,orcamento_minutos);motivo_encerramento=''
    from .strategy import LIMITE_PARES_HTML
    from .frontier import categoria
    dinamica=estrategia=='dinamica';categorias={};candidatos=Fila(dinamica=True,categorias=categorias)
    candidatos_vistos=set();nao_html=set();estados_pares={};exclusivas={nome_a:{},nome_b:{}}
    limite_html=max(LIMITE_PARES_HTML,len(estado['pares_enfileirados'])) if estado else LIMITE_PARES_HTML
    if dinamica:fila=Fila(fila,dinamica=True,categorias=categorias)
    configuracao=dict(url_a=base_a,url_b=base_b,nome_a=nome_a,nome_b=nome_b,site_nome=site_nome,
        auditar_externos=auditar_externos,verificar_cliques=verificar_cliques,
        varredura_inteligente=varredura_inteligente,ambiente_desatualizado=ambiente_desatualizado,estrategia=estrategia,orcamento_minutos=orcamento_minutos)
    segmentos=[];bloqueios={};tentativas_fatais={}
    from .security import registrar,Resumos,url_diagnostica
    resumos_seguranca=Resumos()
    if retomada:
        from .checkpoints import validar,restaurar_pagina
        esperado=dict(configuracao,estrategia=anterior.get('estrategia','profunda'),orcamento_minutos=anterior.get('orcamento_minutos',0))
        legado=dict(anterior,estrategia=anterior.get('estrategia','profunda'),orcamento_minutos=anterior.get('orcamento_minutos',0))
        if legado!=esperado:
            raise ValueError('Configuração incompatível: preserve ambientes/opções; aprofundar ou renovar o orçamento é permitido.')
        categorias.update({tuple(x['par']):x['categoria'] for x in estado.get('categorias_html',[])})
        fila=Fila(estado['fila'],dinamica=dinamica,categorias=categorias);visitados=set(map(tuple,estado['visitados']));fila.saidas=estado.get('fila_saidas',len(visitados))
        pares_enfileirados=set(map(tuple,estado['pares_enfileirados']))
        candidatos=Fila(estado.get('candidatos_html',[]),dinamica=True,categorias=categorias)
        candidatos.saidas=estado.get('candidatos_saidas',0);candidatos.rodada=estado.get('candidatos_rodada',0)
        fila.rodada=estado.get('fila_rodada',0)
        candidatos_vistos=set(map(tuple,estado.get('candidatos_vistos',[])))
        nao_html=set(map(tuple,estado.get('pares_nao_html',[])))
        estados_pares={tuple(x['par']):x['estado'] for x in estado.get('estados_pares',[])}
        exclusivas={env:{u:restaurar_pagina(p) for u,p in estado.get('paginas_exclusivas',{}).get(env,{}).items()} for env in (nome_a,nome_b)}
        limite_html=estado.get('limite_html',limite_html)
        # Checkpoints anteriores podem já ter mais de mil admissões. Honra a
        # fila histórica; não abre novas vagas nem descarta trabalho aceito.
        if dinamica and anterior.get('estrategia')!='dinamica':limite_html=max(limite_html,len(pares_enfileirados-nao_html))
        pares_falhos=set(map(tuple,estado.get('pares_falhos',[])))
        if not pares_falhos:
            urls_falhas={f.get('url') for f in estado['falhas']}
            pares_falhos={par for par in visitados if par[0] in urls_falhas or par[1] in urls_falhas}
        paginas_a={k:restaurar_pagina(v) for k,v in estado['paginas_a'].items()}
        paginas_b={k:restaurar_pagina(v) for k,v in estado['paginas_b'].items()}
        brutos=estado['brutos'];falhas=estado['falhas'];pendencias=estado['pendencias'];refs=estado['refs']
        editoriais=estado['editoriais'];eventos=estado['eventos'];avisos_coleta=estado['avisos_coleta']
        documentos_relatorio=estado['documentos_relatorio'];verificacoes_destinos=estado['verificacoes_destinos']
        resultados_funcionais=estado['resultados_funcionais'];diferencas_esteticas=estado['diferencas_esteticas']
        excluded.update(estado['excluded']);cliques_testados=estado['cliques_testados']
        validacao_atual=metricas.tempos.get('checkpoint_recuperacao_validacao',0)
        metricas.tempos.update(estado['metricas']['tempos_segundos'])
        metricas.tempos['checkpoint_recuperacao_validacao']+=validacao_atual
        escopo.editoriais_observados=set(map(tuple,estado.get('editoriais_observados',[])))
        metricas.contagens.update(estado['metricas']['contagens'])
        metricas.releituras=estado['metricas'].get('releituras',[])
        metricas.inicio-=estado['duracao_acumulada'];metricas.iniciado_em=estado['iniciado_em']
        for attr in ('equivalencias','inconclusivos','omissoes','estruturas'):setattr(inteligencia,attr,estado['inteligencia'][attr])
        inteligencia.componentes=set(estado['inteligencia']['componentes'])
        inteligencia.templates.update(estado['inteligencia']['templates'])
        inteligencia.nao_pareadas=set(map(tuple,estado['inteligencia']['nao_pareadas']))
        segmentos=estado.get('segmentos',[]);tentativas_fatais=estado.get('tentativas_fatais',{})
        from .security import restaurar
        bloqueios=restaurar(estado.get('bloqueios',{}))
        if not estados_pares:
            for par in visitados:
                estados_pares[par]='comparado' if par[0] in paginas_a and par[1] in paginas_b and par not in pares_falhos else 'falha' if par in pares_falhos else 'inconclusivo'
        log('[Retomada] Fila e resultados restaurados; novas observações terão outro horário.')
    from datetime import datetime
    segmentos=segmentos+[{'iniciado_em':datetime.now().astimezone().isoformat(),'retomada':bool(retomada),'estrategia':estrategia,'orcamento_minutos':orcamento_minutos,'amostras_editoriais':escopo.representantes}]
    ultimo_checkpoint=time.monotonic();custo_checkpoint=0
    from .checkpoints import PaginasSerializadas
    cache_paginas=PaginasSerializadas()
    evidencias_preservadas=estado.get('evidencias_preservadas',{}) if estado else {}
    contagens_estados=Counter(estados_pares.values())
    def comparados():return contagens_estados['comparado']
    def inconclusivos():return sum(n for v,n in contagens_estados.items() if v not in ('comparado','nao_html','falha'))
    def admitidos():return len(pares_enfileirados-nao_html)
    def repor_fila():
        if not dinamica:return
        with metricas.medir('descoberta'):
            while candidatos.ativos and admitidos()<limite_html and len(fila)<8:
                par=candidatos.popleft();key=tuple(par[:2])
                if key in pares_enfileirados:continue
                pares_enfileirados.add(key);fila.append(par)
    urls_vistas=[{p[lado] for p in pares_enfileirados|candidatos_vistos if p[lado]} for lado in (0,1)]
    def propor(par,contexto=''):
        with metricas.medir('descoberta'):_propor(par,contexto)
    def _propor(par,contexto=''):
        key=tuple(par[:2])
        if dinamica and (not key[0] or not key[1]):
            lado=0 if key[0] else 1
            # Mesma URL exata já observada neste ambiente: reaproveita a
            # inspeção, sem dispensar a comparação dos rótulos nos menus.
            if key[lado] in urls_vistas[lado]:
                metricas.contagens['urls_duplicadas']+=1;return
        if key in pares_enfileirados or key in candidatos_vistos:
            metricas.contagens['urls_duplicadas']+=1;return
        if dinamica:
            if admitidos()>=limite_html:
                metricas.contagens['referencias_apos_teto']+=1;return
            if len(candidatos_vistos)>=MAX_URLS_SEGURANCA:
                excluded['Teto preventivo de referências candidatas']+=1;return
            categorias[key]=categoria(par,contexto);candidatos_vistos.add(key);candidatos.append(par)
        else:
            if len(pares_enfileirados)>=MAX_URLS_SEGURANCA:return
            fila.append(par);pares_enfileirados.add(key)
        for lado in (0,1):
            if key[lado]:urls_vistas[lado].add(key[lado])
    def terminar(ua,ub,estado_par):
        anterior=estados_pares.get((ua,ub))
        if anterior:contagens_estados[anterior]-=1
        estados_pares[(ua,ub)]=estado_par
        contagens_estados[estado_par]+=1
        andamento['ultimo_par_processado']=len(estados_pares)
        repor_fila();emitir('par_processado')
    def emitir(etapa):
        from datetime import datetime
        andamento.update(estrategia=estrategia,orcamento_minutos=orcamento_minutos,orcamento_restante_segundos=escopo.restante(),pares_nao_aprofundados=len(fila.adiados),pares_editoriais_amostrados=len(escopo.representantes))
        if brutos and 'ate_primeira_div_relevante' not in metricas.tempos:
            from .relevance import classificar
            if any(classificar(d,{nome_a:base_a,nome_b:base_b})[0]=='relevante' for d in brutos):metricas.tempos['ate_primeira_div_relevante']=time.perf_counter()-escopo.inicio
        andamento.update(etapa=etapa,pares_descobertos=len(pares_enfileirados),pares_visitados=len(visitados),pares_comparados=comparados(),pares_pendentes=len(fila),pares_com_falha=len(pares_falhos),ocorrencias_preliminares=len(brutos),ultima_atividade=datetime.now().astimezone().isoformat(),pares_admitidos_html=admitidos(),referencias_candidatas=len(candidatos),pares_inconclusivos=inconclusivos(),limite_pares_html=limite_html)
        if observador:observador(dict(andamento))
    def resumo_cobertura():
        return {'estrategia':estrategia,'orcamento_minutos':orcamento_minutos,'motivo_encerramento':motivo_encerramento,
                'pares_dom_aprofundado':sum(p.coleta.get('inspecao_profunda',True) for p in paginas_a.values()),
                'pares_dom_estrutural':sum(not p.coleta.get('inspecao_profunda',True) for p in paginas_a.values()),
                'pares_nao_inspecionados':len(fila),'pares_adiados_editoriais':len(fila.adiados),
                'representantes_segmento':escopo.representantes,
                'importantes_pendentes':sum(1 for p in fila if grupo_editorial(p,escopo.editoriais_observados) is None),
                'limite_pares_html':limite_html if dinamica else None,'pares_admitidos_html':admitidos(),
                'teto_atingido':bool(dinamica and admitidos()>=limite_html),
                'referencias_nao_admitidas':len(candidatos)+metricas.contagens['referencias_apos_teto'],
                'paginas_exclusivas_inspecionadas':sum(map(len,exclusivas.values())),
                'limite':'Fila admitida não representa cobertura integral do portal. Representantes não validam outras páginas. DOM não comprova funcionamento integral.'}

    def snapshot():
        from .checkpoints import empacotar
        inicio_snapshot=time.perf_counter();inicio_conversao=time.perf_counter()
        serial_a=cache_paginas.converter(paginas_a);serial_b=cache_paginas.converter(paginas_b)
        conversao=time.perf_counter()-inicio_conversao
        metricas.tempos['checkpoint_conversao_paginas']+=conversao
        metricas.contagens['checkpoint_paginas_convertidas']=cache_paginas.convertidas
        metricas.contagens['checkpoint_paginas_reutilizadas']=cache_paginas.reutilizadas
        estado=dict(evidencias_preservadas=evidencias_preservadas,politica_html=1,limite_html=limite_html,categorias_html=[{'par':list(k),'categoria':v} for k,v in categorias.items()],
            candidatos_html=[list(p) for p in candidatos],candidatos_saidas=candidatos.saidas,candidatos_rodada=candidatos.rodada,fila_rodada=fila.rodada,
            candidatos_vistos=[list(p) for p in sorted(candidatos_vistos)],pares_nao_html=[list(p) for p in sorted(nao_html)],
            estados_pares=[{'par':list(k),'estado':v} for k,v in estados_pares.items()],
            paginas_exclusivas={env:cache_paginas.converter(pags) for env,pags in exclusivas.items()},
            editoriais_observados=[list(p) for p in sorted(escopo.editoriais_observados)],fila_saidas=fila.saidas,amostragem_representantes=escopo.representantes,motivo_encerramento=motivo_encerramento,pares_falhos=[list(p) for p in sorted(pares_falhos)],configuracao=configuracao,fila=[list(p) for p in fila],visitados=[list(p) for p in sorted(visitados)],
            pares_enfileirados=[list(p) for p in sorted(pares_enfileirados)],
            paginas_a=serial_a,paginas_b=serial_b,
            brutos=brutos,falhas=falhas,pendencias=pendencias,refs=refs,editoriais=editoriais,eventos=eventos,
            avisos_coleta=avisos_coleta,documentos_relatorio=documentos_relatorio,verificacoes_destinos=verificacoes_destinos,
            resultados_funcionais=resultados_funcionais,diferencas_esteticas=diferencas_esteticas,
            excluded=dict(excluded),cliques_testados=cliques_testados,metricas=metricas.resultado(),
            duracao_acumulada=metricas.temporal()['duracao_segundos'],iniciado_em=metricas.iniciado_em,segmentos=segmentos,bloqueios=bloqueios,tentativas_fatais=tentativas_fatais,
            inteligencia={**{k:getattr(inteligencia,k) for k in ('equivalencias','inconclusivos','omissoes','estruturas')},
                'componentes':list(inteligencia.componentes),'templates':dict(inteligencia.templates),'nao_pareadas':list(inteligencia.nao_pareadas)})
        assinatura_antes=metricas.tempos['checkpoint_assinatura_json']
        pacote=empacotar(estado,metricas)
        resultado={'retomada':pacote,'evidencias_preservadas':evidencias_preservadas,'cobertura':resumo_cobertura(),'motivo_encerramento':motivo_encerramento,**metricas.temporal(),'site_nome':site_nome,'ambientes':{nome_a:base_a,nome_b:base_b},
            'paginas':{nome_a:len(paginas_a),nome_b:len(paginas_b)},
            'bloqueios_seguranca':list(bloqueios.values()),'andamento':dict(andamento),'brutos':brutos,'variacoes_editoriais':editoriais,'falhas':falhas,
            'modo_varredura':'inteligente' if varredura_inteligente else 'atual',
            'otimizacao':inteligencia.resultado(),'resultados_funcionais':resultados_funcionais,'diferencas_esteticas':diferencas_esteticas,'documentos_verificados':documentos_relatorio,'verificacoes_destinos':verificacoes_destinos,
            'metricas':metricas.resultado(),'registros_editoriais':editoriais,
            'eventos_diagnostico':eventos,'pendencias':pendencias,
            'meta_varredura':{nome_a:{'visitadas':len(visitados),'pendentes':len(fila),'motivo_parada':parada or 'Execução ainda em andamento','referencias_excluidas':dict(excluded)},
              nome_b:{'visitadas':len(visitados),'pendentes':len(fila),'motivo_parada':parada or 'Execução ainda em andamento','referencias_excluidas':{}}},
            'ambiente_desatualizado':modo_defasado}
        assinatura=metricas.tempos['checkpoint_assinatura_json']-assinatura_antes
        metricas.tempos['checkpoint_construcao_exclusiva']+=max(0,time.perf_counter()-inicio_snapshot-conversao-assinatura)
        return resultado
    def salvar_checkpoint(motivo,forcar=False):
        nonlocal ultimo_checkpoint,custo_checkpoint
        if not checkpoint:return
        # Um único agendamento: evita disparos de tempo e de contagem no mesmo par.
        if not forcar and time.monotonic()-ultimo_checkpoint<max(30,min(120,custo_checkpoint*20)):return
        inicio_cp=time.perf_counter()
        try:
            metricas.contagens['operacoes_checkpoint']+=1
            dados=snapshot();dados['motivo_checkpoint']=motivo
            io=checkpoint(dados)
            if isinstance(io,dict):
                for k in ('serializacao_json','gravacao'):metricas.tempos['checkpoint_'+k]+=io.get(k,0)
                metricas.contagens['checkpoint_bytes_gravados']+=io.get('bytes',0)
            metricas.contagens['checkpoints_salvos']+=1
        except Exception as exc:
            metricas.contagens['checkpoint_falhas']+=1
            log('[Diagnóstico] Checkpoint não salvo; último arquivo válido preservado: '+str(exc)[:110])
        finally:
            custo_checkpoint=time.perf_counter()-inicio_cp
            metricas.tempos['checkpoint']+=custo_checkpoint
            ultimo_checkpoint=time.monotonic()
    def registrar_fatal(ua,ub,trilha,ex):
        key=ua+' | '+ub;tentativas_fatais[key]=tentativas_fatais.get(key,0)+1
        if tentativas_fatais[key]<2:
            visitados.discard((ua,ub));fila.append((ua,ub,trilha))
        else:
            pares_falhos.add((ua,ub))
            falhas.append({'ambiente':'AUTOMAÇÃO','url':ua,'url_b':ub,'tipo_erro':'EXTRACAO','erro':'Limite de duas tentativas fatais: '+str(ex)[:180]})
            pendencias.append({'ambiente':nome_a+' / '+nome_b,'url':ua,'url_b':ub,'motivo':'Par falho após duas tentativas; outras páginas permanecem na fila'})
            terminar(ua,ub,'falha')
        emitir('falha')
        salvar_checkpoint('falha_fatal',True)
    def validar_itens(pag):
        for i in pag.itens:
            if not i.destino:continue
            from .resources import classificar
            contexto='midia' if i.tipo=='Imagem' or i.imagem_link and i.natureza=='editorial' else ''
            if re.search(r'pdf|portaria|legisla|requerimento',i.nome,re.I):contexto='documento'
            i.recurso=classificar(i.destino,contexto)
            if i.recurso=='midia' and i.tipo=='Documento':i.tipo='Opção'
            if i.tipo=='Imagem' and i.destino.startswith('data:image/'):continue
            try:
                destino=urljoin(pag.url,i.destino);url_limpa(destino);i.destino=destino
            except (ValueError,TypeError) as exc:
                pendencias.append({'ambiente':'Referência','url':pag.url,'referencia':url_diagnostica(i.destino),'elemento':i.nome,'motivo':'URL inválida: '+str(exc)[:160]})
                pag.coleta.setdefault('referencias_invalidas',[]).append(i.nome);i.destino=''
    salvar_checkpoint('inicial',True)
    with sync_playwright() as pw:
        try:
            browser=pw.chromium.launch(headless=os.environ.get('AMBIDIFF_HEADLESS')=='1')
        except Exception:
            # Fallback para Linux de desenvolvimento, quando os binários do Playwright
            # ainda não foram instalados. O instalador Windows baixa Chromium normalmente.
            executable=shutil.which('chromium') or shutil.which('chromium-browser')
            if not executable:raise
            browser=pw.chromium.launch(headless=os.environ.get('AMBIDIFF_HEADLESS')=='1',executable_path=executable,args=['--no-sandbox'])
        ctx_a=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},service_workers='block',accept_downloads=False)
        ctx_b=browser.new_context(locale='pt-BR',viewport={'width':1366,'height':850},service_workers='block',accept_downloads=False)
        def contar_requisicao(_req):metricas.contagens['requisicoes_navegador']+=1
        for contexto in (ctx_a,ctx_b):contexto.on('request',contar_requisicao)
        origens_autorizadas={(urlsplit(u).scheme,urlsplit(u).netloc) for u in (base_a,base_b)}
        def somente_leitura(route):
            req=route.request;p=urlsplit(req.url)
            from .documents import ACOES_ESCRITA
            inseguro=req.method not in ('GET','HEAD','OPTIONS') or bool(ACOES_ESCRITA.search(unquote(req.url)))
            if req.is_navigation_request() and not any(permitido(req.url,base) for base in (base_a,base_b)):inseguro=True
            if inseguro:
                try:origem=req.frame.page.url
                except Exception:origem=''
                registrar(bloqueios,req.url,req.method,'método/ação' if req.method not in ('GET','HEAD','OPTIONS') or ACOES_ESCRITA.search(unquote(req.url)) else 'navegação fora do escopo',origem)
                metricas.contagens['bloqueios_seguranca']+=1
                resumos_seguranca.emitir(bloqueios,log)
                route.abort()
            else:route.continue_()
        for contexto in (ctx_a,ctx_b):contexto.route('**/*',somente_leitura)
        if _preparar_contextos:
            _preparar_contextos(ctx_a,ctx_b)
        for contexto in (ctx_a,ctx_b):
            # Limite de locadores/interações; evaluate() síncrono não recebe
            # timeout pelo Playwright. Não há prazo global da varredura.
            contexto.set_default_timeout(12000) if hasattr(contexto,'set_default_timeout') else None
        page_a=ctx_a.new_page();page_b=ctx_b.new_page()
        try:
            repor_fila()
            while fila and not parar.is_set():
                if escopo.expirou():
                    motivo_encerramento='orcamento';parada='Orçamento de tempo alcançado — cobertura parcial, continuação disponível';break
                if not fila.ativos:
                    motivo_encerramento='estrategia_editorial';parada='Amostragem editorial encerrada — cobertura parcial, continuação disponível';break
                if len(visitados)>=MAX_URLS_SEGURANCA:
                    parada='Limite preventivo interno de páginas alcançado';break
                if not dinamica and consecutivos>=MAX_FALHAS_CONSECUTIVAS:
                    parada='Muitas falhas consecutivas';break
                salvar_checkpoint('periodico')
                ua,ub,trilha=fila.popleft()
                if (ua,ub) in visitados:continue
                if escopo.adiar((ua,ub,trilha)):
                    fila.adiar((ua,ub,trilha));emitir('adiamento_editorial');continue
                visitados.add((ua,ub))
                andamento.update(par_atual=len(visitados),url_a=ua,url_b=ub)
                if dinamica and (not ua or not ub):
                    env,page,url,base=(nome_a,page_a,ua,base_a) if ua else (nome_b,page_b,ub,base_b)
                    try:
                        with metricas.medir('navegacao'):resp=_abrir(page,url)
                        if resp and resp.status>=400:raise RuntimeError('HTTP '+str(resp.status))
                        mime=getattr(resp,'headers',{}).get('content-type','').lower().split(';')[0].strip()
                        if mime and mime not in ('text/html','application/xhtml+xml'):
                            nao_html.add((ua,ub));terminar(ua,ub,'nao_html');continue
                        if not permitido(page.url,base):raise RuntimeError('Destino fora do escopo da página exclusiva')
                        with metricas.medir('inspecao_exclusiva'):pag=_extrair_page(page,url,trilha,log,metricas=metricas)
                        if parar.is_set():
                            visitados.discard((ua,ub));fila.append((ua,ub,trilha));break
                        validar_itens(pag);exclusivas[env][url]=pag
                        for item in pag.itens:
                            if item.destino and item.recurso=='navegacao' and not e_arquivo(item.destino) and permitido(item.destino,base):
                                u=url_limpa(item.destino);propor((u,'',(trilha+[item.nome])[-12:]) if ua else ('',u,(trilha+[item.nome])[-12:]),item.posicao+' '+item.local)
                        pendencias.append({'ambiente':env,'url':url,'motivo':'Página exclusiva inspecionada; sem contraparte comprovada, conteúdo não comparado'})
                        terminar(ua,ub,'sem_contraparte')
                    except Exception as exc:
                        if any(t in str(exc).lower() for t in ('target closed','browser has been closed','target page, context or browser has been closed')):
                            registrar_fatal(ua,ub,trilha,exc);raise
                        pares_falhos.add((ua,ub));falhas.append({'ambiente':env,'url':url,'erro':str(exc)[:200],**classificar_erro(str(exc))});terminar(ua,ub,'falha')
                    continue
                if e_arquivo(ua) or e_arquivo(ub):
                    excluded['Arquivos não tratados como páginas HTML']+=1
                    if len(eventos)<600:eventos.append({'par':len(visitados),'tipo':'ARQUIVO_NAO_HTML','urls':{nome_a:ua,nome_b:ub},'trilha':trilha,'resultado':'Ignorado sem incrementar falhas'})
                    nao_html.add((ua,ub));terminar(ua,ub,'nao_html');consecutivos=0;continue
                andamento.update(etapa='navegacao',par_atual=len(visitados),url_a=ua,url_b=ub)
                emitir('navegacao')
                log('[PARES] '+str(len(visitados))+': '+ ' → '.join(trilha[-3:]))
                statuses=[];pares=[];houve_documento=False;nao_html_ambientes=set()
                for env,page,url in ((nome_a,page_a,ua),(nome_b,page_b,ub)):
                    try:
                        antes_nav=time.perf_counter()
                        with metricas.medir('navegacao'):response=_abrir(page,url)
                        from .frontier import prioridade
                        if prioridade((ua,ub,trilha))>=4:metricas.tempos['navegacao_editorial_paginacao_heuristica']+=time.perf_counter()-antes_nav
                        if response and response.status>=400:raise RuntimeError('HTTP '+str(response.status))
                        headers=getattr(response,'headers',{})
                        mime=headers.get('content-type','').lower().split(';')[0].strip()
                        if mime and mime not in ('text/html','application/xhtml+xml'):
                            houve_documento=True;nao_html_ambientes.add(env);statuses.append((url,'Resposta não HTML: '+mime));continue
                        statuses.append((getattr(response,'url',None) or page.url,None))
                    except Exception as ex:
                        if any(t in str(ex).lower() for t in ('target closed','browser has been closed','target page, context or browser has been closed')):
                            registrar_fatal(ua,ub,trilha,ex);raise
                        msg=str(ex)[:300]
                        # Downloads não devem provocar 15 falhas consecutivas.
                        if 'Download is starting' in msg or 'download is starting' in msg.lower():
                            excluded['Downloads tratados fora da navegação HTML']+=1
                            houve_documento=True;nao_html_ambientes.add(env)
                            statuses.append((url,'Arquivo para download'))
                        else:
                            falhas.append({'ambiente':env,'url':url,'erro':msg,**classificar_erro(msg)})
                            if len(eventos)<600:eventos.append({'par':len(visitados),'ambiente':env,'url':url,'trilha':trilha,'erro':msg,**classificar_erro(msg)})
                            statuses.append((url,msg))
                final_a,err_a=statuses[0];final_b,err_b=statuses[1]
                if err_a or err_b:
                    acesso_falhou=any(erro and env not in nao_html_ambientes for env,(_,erro) in zip((nome_a,nome_b),statuses))
                    if acesso_falhou:pares_falhos.add((ua,ub));consecutivos+=1
                    else:consecutivos=0
                    if len(nao_html_ambientes)==2:nao_html.add((ua,ub))
                    if houve_documento and len(eventos)<600:eventos.append({'par':len(visitados),'tipo':'DOWNLOAD_DE_DOCUMENTO',
                        'urls':{nome_a:ua,nome_b:ub},'resultado':'Tipo não HTML observado; falhas de acesso do outro ambiente continuam registradas'})
                    pendencias.append({'ambiente':nome_a+' / '+nome_b,'url':ua,'pagina':'Página não comparada',
                        'motivo':('Acesso a pelo menos um dos ambientes falhou. Não há evidência de conteúdo ausente.' if acesso_falhou else
                                  'Tipo não HTML observado; comparação HTML indisponível. Uma resposta HTML no outro lado continua reservando vaga.'),
                        'caminho':' → '.join(trilha),'url_b':ub,'ambientes_nao_html':sorted(nao_html_ambientes)})
                    terminar(ua,ub,'falha' if acesso_falhou else 'nao_html' if len(nao_html_ambientes)==2 else 'inconclusivo');continue
                try:url_limpa(final_a);url_limpa(final_b)
                except (ValueError,TypeError) as exc:
                    pendencias.append({'ambiente':nome_a+' / '+nome_b,'url':ua,'url_b':ub,'motivo':'Destino final inválido: '+str(exc)[:160]});pares_falhos.add((ua,ub));terminar(ua,ub,'falha');continue
                if not link_equivalente(final_a,final_b,base_a,base_b):
                    brutos.append(_diff_redir_page(ua,ub,final_a,final_b,trilha,nome_a,nome_b))
                    terminar(ua,ub,'redirecionamento');consecutivos=0
                    continue
                if not permitido(final_a,base_a) or not permitido(final_b,base_b):
                    # Ambos podem redirecionar para exatamente a mesma página externa.
                    if final_a==final_b:externos.append((final_a,' → '.join(trilha)))
                    else:brutos.append(_diff_redir_page(ua,ub,final_a,final_b,trilha,nome_a,nome_b))
                    terminar(ua,ub,'fora_escopo');consecutivos=0
                    continue
                emitir('extracao')
                try:
                    # Observação independente em cada página já navegada. O
                    # tempo de estabilidade do segundo ambiente decorre enquanto
                    # o primeiro é inspecionado; nenhuma coleta/cookie é compartilhada.
                    from .adaptive import sondar
                    for page in (page_a,page_b):
                        try:
                            with metricas.medir('observacao_inicial'):sondar(page)
                        except Exception:pass  # A extração mantém seu diagnóstico/retry.
                    if varredura_inteligente:
                        pa,pb=inteligencia.preparar_par(page_a,page_b,ua,ub,trilha,log,base_a,base_b,
                            modo_defasado,_extrair_page,parar)
                        for pag in (pa,pb):
                            for item in pag.itens:
                                if item.posicao in ('Menu de navegação','Menu lateral','Cabeçalho','Rodapé'):item.natureza='estrutura'
                                if item.tipo!='Imagem' and item.destino and e_arquivo(item.destino):item.tipo='Documento'
                    else:
                        pa=_extrair_page(page_a,ua,trilha,log,metricas=metricas)
                        pb=_extrair_page(page_b,ub,trilha,log,metricas=metricas)
                except Exception as ex:
                    if any(t in str(ex).lower() for t in ('target closed','browser has been closed','target page, context or browser has been closed')):
                        registrar_fatal(ua,ub,trilha,ex);raise
                    pares_falhos.add((ua,ub))
                    msg='Falha de extração: '+str(ex)[:160]
                    falhas.append({'ambiente':'AMBOS','url':ua,'erro':msg,**classificar_erro(msg)})
                    if len(eventos)<600:eventos.append({'par':len(visitados),'ambiente':'AMBOS','url':ua,'trilha':trilha,'erro':msg,**classificar_erro(msg)})
                    pendencias.append({'ambiente':nome_a+' / '+nome_b,'url':ua,'url_b':ub,'motivo':msg,'pagina':'Extração inconclusiva'})
                    consecutivos+=1
                    terminar(ua,ub,'falha');continue
                if parar.is_set():
                    visitados.discard((ua,ub));fila.append((ua,ub,trilha));break
                validar_itens(pa);validar_itens(pb)
                consecutivos=0
                for env,pag in ((nome_a,pa),(nome_b,pb)):
                    if not pag.coleta.get('estavel') or pag.coleta.get('rolagem_limitada'):
                        avisos_coleta.append({'ambiente':env,'url':pag.url})
                chave=(ua,ub)
                paginas_a[ua]=pa;paginas_b[ub]=pb
                emitir('comparacao')
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
                    emitir('segunda_leitura')
                    inicio_releitura=time.perf_counter()
                    registro={'url_a':ua,'url_b':ub,'motivos':motivos,'diagnostico_modificado':False,
                              'adotada':False,'diferencas_antes':len(comps),
                              'primeira_coleta':{'a':asdict(pa),'b':asdict(pb),'divergencias':comps}}
                    try:
                        pa2=_extrair_page(page_a,ua,trilha,log,metricas=metricas)
                        pb2=_extrair_page(page_b,ub,trilha,log,metricas=metricas)
                        validar_itens(pa2);validar_itens(pb2)
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
                from .sections import comparar_secoes
                comps=comparar_secoes(comps,pa,pb,nome_a,nome_b)
                if any(g.get('categoria') in ('reCAPTCHA','Consentimento') for g in bloqueios.values()):
                    for row in comps:
                        pag=pa if row.get('presente_em')==nome_a else pb
                        if any(row.get('seletor','').startswith(sel) for sel in pag.coleta.get('componentes_restritos',[])):
                            row.update(verificacao_limitada=True,situacao='Avaliação inconclusiva por restrição da automação')
                            row['descricao']+=' O componente depende de recurso bloqueado; não foi comprovado defeito funcional.'
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
                tecnicos=[r for r in novos_icones if r.get('situacao')=='Código do ícone diferente — revisão visual' or r.get('decorativo')]
                diferencas_esteticas.extend(tecnicos)
                brutos.extend(r for r in novos_icones if r not in tecnicos)
                refs.extend(novos_layouts)
                ordens=diferencas_de_ordem(pa,pb,nome_a,nome_b)
                if modo_defasado:
                    # Ordem de notícias pode variar naturalmente entre bases antigas.
                    # Menus e listas institucionais continuam no relatório principal.
                    ordens=[d for d in ordens if d.get('natureza')!='editorial' and not any(t in normalizar(d.get('local','')) for t in ('noticia','notícia','publicaç'))]
                brutos.extend(ordens)
                emitir('links_documentos')
                # 2. Compara links pareados por nome/contexto.
                with metricas.medir('links'):pares_links=_link_pairs(pa,pb,aceitar_rotulos=varredura_inteligente,base_a=base_a,base_b=base_b)
                controles=[]
                for ia in pa.itens:
                    matches=[ib for ib in pb.itens if ia.controle_alvo and ib.controle_alvo and normalizar(ia.nome)==normalizar(ib.nome) and normalizar(ia.local)==normalizar(ib.local)]
                    if len(matches)==1:controles.append((ia,matches[0]))
                if verificar_cliques and cliques_testados<MAX_CLIQUES:
                    for ca,cb in escolher_candidatos(pares_links+controles,base_a,base_b,limite=min(2,MAX_CLIQUES-cliques_testados)):
                        # A inspeção só é executada quando o usuário opta por ela.
                        cliques_testados+=1
                        with metricas.medir('cliques'):candidato=verificar_par(browser,pa,pb,ca,cb,nome_a,nome_b,base_a,base_b,log,diagnosticos=resultados_funcionais)
                        if candidato:brutos.append(candidato)
                if varredura_inteligente:
                    pareados={id(i) for par in pares_links for i in par}
                    for env,pag in ((nome_a,pa),(nome_b,pb)):
                        for item in pag.itens:
                            base=base_a if env==nome_a else base_b
                            if item.destino and item.tipo!='Documento' and not e_arquivo(item.destino) and permitido(item.destino,base) and id(item) not in pareados and (env,item.destino) not in inteligencia.nao_pareadas:
                                inteligencia.nao_pareadas.add((env,item.destino))
                                inteligencia.omissoes.append({'categoria':'Página sem par inequívoco','elemento':item.nome,
                                    'url_a':item.destino if env==nome_a else '', 'url_b':item.destino if env==nome_b else '',
                                    'quantidade_paginas':1,'motivo':'Link exclusivo ou ambíguo registrado; conteúdo profundo sem par não foi comparado. Não presume ausência de conteúdo.'})
                            if item.destino and (item.tipo=='Documento' or e_arquivo(item.destino)) and id(item) not in pareados:
                                documentos_relatorio.append({'classificacao':'Verificação inconclusiva','ambiente':env,
                                    'elemento':item.nome,'destino':item.destino,'motivo':'Documento sem par inequívoco; não acessado'})
                if not varredura_inteligente:
                    pareados={id(i) for par in pares_links for i in par}
                    for env,pag in ((nome_a,pa),(nome_b,pb)):
                        for item in pag.itens:
                            if item.destino and (item.tipo=='Documento' or e_arquivo(item.destino)) and id(item) not in pareados:
                                documentos_relatorio.append({'classificacao':'Verificação inconclusiva','ambiente':env,'elemento':item.nome,'destino':item.destino,'motivo':'Documento sem par; referência não acessada'})
                if dinamica:
                    pareados={id(i) for par in pares_links for i in par}
                    for env,pag,base in ((nome_a,pa,base_a),(nome_b,pb,base_b)):
                        for item in pag.itens:
                            if id(item) not in pareados and item.destino and item.recurso=='navegacao' and not e_arquivo(item.destino) and permitido(item.destino,base):
                                u=url_limpa(item.destino)
                                # Não inventa URL no ambiente oposto nem segue destino divergente pareado.
                                propor((u,'',(trilha+[item.nome])[-12:]) if env==nome_a else ('',u,(trilha+[item.nome])[-12:]),item.posicao+' '+item.local)
                pares_links.sort(key=lambda par: (0 if re.search(r'portaria|legisla|requerimento|normativ|servi',normalizar(par[0].nome)) else 2 if par[0].imagem_link else 1))
                for ia,ib in pares_links:
                    from .urlpolicy import fragmento
                    classe_fragmento=fragmento(ia,ib,page_a,page_b,base_a,base_b)
                    if classe_fragmento in ('rolagem','inconclusivo'):
                        refs.append({'tipo':'Fragmento de URL','elemento':ia.nome,'caminho':' → '.join(trilha),
                            'url_presente':pa.url,'url_comparada':pb.url,'ambiente_a':nome_a,'ambiente_b':nome_b,
                            'destino_a':ia.destino,'destino_b':ib.destino,'motivo':'Âncora de rolagem observada; caminho e query equivalentes' if classe_fragmento=='rolagem' else 'Fragmento diferente sem evidência de função ou rolagem; não declarado defeito',
                            'classificacao':'baixa' if classe_fragmento=='rolagem' else 'inconclusivo'})
                        metricas.contagens['fragmentos_'+classe_fragmento]+=1
                        if classe_fragmento=='inconclusivo':pendencias.append({'ambiente':nome_a+' / '+nome_b,'url':ia.destino,'url_b':ib.destino,'motivo':'Fragmento exige conferência manual'})
                    elif classe_fragmento=='funcional':
                        brutos.append(_diff_destino(pa,pb,ia,ib,nome_a,nome_b))
                    try:da,db=url_limpa(ia.destino),url_limpa(ib.destino)
                    except (TypeError,ValueError):continue
                    if referencia_invalida(da) or referencia_invalida(db):
                        excluded['Referências codificadas não navegáveis']+=1;continue
                    if ia.recurso in ('midia','auxiliar') or ib.recurso in ('midia','auxiliar'):
                        refs.append({'tipo':'Recurso de mídia/auxiliar','elemento':ia.nome,'destino_a':da,'destino_b':db,'ambiente_a':nome_a,'ambiente_b':nome_b,'caminho':' → '.join(trilha),'motivo':'Referência classificada por caminho e contexto; sem inspeção binária'})
                        # Evitar leitura/crawl de mídia não dispensa comparar o
                        # destino da opção, especialmente nos menus estruturais.
                        if not link_equivalente(da,db,base_a,base_b):
                            if modo_defasado and (item_editorial(ia,pa) or item_editorial(ib,pb)):
                                editoriais.append({'tipo':'Link editorial','elemento':ia.nome,'presente_em':nome_a,'url_presente':pa.url,'url_comparada':pb.url})
                            else:brutos.append(_diff_destino(pa,pb,ia,ib,nome_a,nome_b))
                        continue
                    documental=ia.tipo=='Documento' or ib.tipo=='Documento' or e_arquivo(da) or e_arquivo(db)
                    if documental:
                        resultado_doc=documentos.comparar(ia,ib,base_a,base_b)
                        documentos_relatorio.append({**resultado_doc,'pagina_a':pa.url,'pagina_b':pb.url})
                        ma=resultado_doc.get('a',{});mb=resultado_doc.get('b',{})
                        diferentes=bool(ma.get('url') and mb.get('url') and not link_equivalente(ma['url'],mb['url'],base_a,base_b))
                        falha_documental='falha_acesso' in (ma.get('situacao'),mb.get('situacao'))
                        if diferentes or falha_documental or resultado_doc.get('divergencia_tipo_observada'):
                            registro=_diff_destino(pa,pb,ia,ib,nome_a,nome_b)
                            registro.update(tipo='Destino verificado',categoria='Documentos',situacao='DESTINO_DIVERGENTE' if diferentes else 'TIPO_DIVERGENTE' if resultado_doc.get('divergencia_tipo_observada') else 'LINK_INACESSIVEL',
                                destino_final_a=ma.get('url'),destino_final_b=mb.get('url'),verificacao_destino=resultado_doc,
                                descricao='Cabeçalhos e destinos documentais observados por HEAD. Acesso, tipo de recurso ou referência diferente; conteúdo dos documentos não lido.')
                            brutos.append(registro)
                    externo=(not permitido(da,base_a) or not permitido(db,base_b))
                    if externo:
                        if auditar_externos:
                            with metricas.medir('destinos'):verificacao=destinos.comparar(da,db,base_a,base_b)
                        else:verificacao={'classificacao':'VERIFICACAO_INCONCLUSIVA','destino_a':da,'destino_b':db,'motivo':'Destino externo não acessado: autorização de conferência desmarcada'}
                        verificacoes_destinos.append(dict(verificacao,elemento=ia.nome,pagina_a=pa.url,pagina_b=pb.url))
                        if verificacao['classificacao'] in ('DESTINO_DIVERGENTE','LINK_INACESSIVEL'):
                            registro=_diff_destino(pa,pb,ia,ib,nome_a,nome_b)
                            registro.update(tipo='Destino verificado',situacao=verificacao['classificacao'],verificacao_destino=verificacao,
                                descricao='Resultado da conferência HEAD de destinos. Não houve exploração nem análise de conteúdo externo.')
                            brutos.append(registro)
                        if link_equivalente(da,db,base_a,base_b):continue
                    if not link_equivalente(da,db,base_a,base_b):
                        if modo_defasado and (item_editorial(ia,pa) or item_editorial(ib,pb)):
                            editoriais.append({'tipo':'Link editorial','elemento':ia.nome,
                               'presente_em':nome_a,'url_presente':pa.url,'url_comparada':pb.url})
                            continue
                        # REGISTRA e PARA AQUI. Não enfileira nem abre o destino.
                        brutos.append(_diff_destino(pa,pb,ia,ib,nome_a,nome_b))
                        continue
                    if documental:
                        excluded['Documentos vinculados (não percorridos como HTML)']+=1
                        continue
                    if permitido(da,base_a) and permitido(db,base_b):
                        if item_editorial(ia,pa) and item_editorial(ib,pb):escopo.editoriais_observados.add((da,db))
                        propor((da,db,(trilha+[ia.nome])[-12:]),ia.posicao+' '+ia.local+' '+ib.posicao+' '+ib.local)
                    elif (urlsplit(da).netloc!=urlsplit(base_a).netloc and
                          urlsplit(db).netloc!=urlsplit(base_b).netloc):
                        if da==db and not e_arquivo(da):externos.append((da,' → '.join(trilha+[ia.nome])))
                    # PDFs/planilhas permanecem somente como referências (sem abrir no crawler).
                terminar(ua,ub,'comparado')
                emitir('par_processado')
                log(f'[{nome_a}/{nome_b}] {len(paginas_a)} pares, {len(brutos)} ocorrências preliminares')
                progresso(min(.92,len(visitados)/max(1,len(visitados)+len(fila))*.85))
                salvar_checkpoint('par_processado')
                time.sleep(.04)
            if parar.is_set():parada='Interrompida pelo usuário (resultado parcial preservado)'
            resumos_seguranca.emitir(bloqueios,log,final=True)
            completos=not bool((dinamica and (candidatos or admitidos()>=limite_html)) or fila or parada or falhas or any(g.get('impacto_possivel',True) for g in bloqueios.values()) or pendencias or avisos_coleta or inteligencia.omissoes or any(x.get('classificacao')=='Verificação inconclusiva' for x in documentos_relatorio) or any(x.get('classificacao')=='VERIFICACAO_INCONCLUSIVA' for x in verificacoes_destinos) or any(not x.get('conclusivo') for x in resultados_funcionais))
            if not (paginas_a and paginas_b):completos=False
            if parada:log('Varredura parcial: '+parada)
            emitir('processamento_final')
            salvar_checkpoint('encerramento',True)
            metricas.tempos['varredura']=time.perf_counter()-metricas.inicio
            inicio_final=time.perf_counter()
            emitir('processamento_final')
            divergencias=agrupar_registros(brutos)
            for registro in divergencias:registro.update(evidencias_preservadas.get(registro['id'],{}))
            if paginas_a and paginas_b and not parar.is_set() and not escopo.expirou():
                emitir('capturas')
                with metricas.medir('capturas'):_salvar_evidencias(browser,divergencias,evidencias_dir,parar,log,nome_a,nome_b,metricas=metricas)
                for registro in divergencias:
                    if registro.get('evidencias'):evidencias_preservadas[registro['id']]={k:registro[k] for k in ('evidencias','marcacoes','evidencia') if k in registro}
                if evidencias_preservadas:salvar_checkpoint('evidencias_preservadas',True)
            progresso(.94)
            emitir('auditoria')
            with metricas.medir('auditoria'):
                externos_result=[] # Conferência HEAD já registrada; nenhuma exploração externa.
            if parar.is_set():
                parada='Interrompida pelo usuário (resultado parcial preservado)';completos=False
                salvar_checkpoint('interrupcao_final',True)
            progresso(.98)
            metricas.contagens['paginas_visitadas']=metricas.contagens['operacoes_navegacao']
            metricas.contagens['paginas_coletadas']=len(paginas_a)+len(paginas_b)
            metricas.contagens['pares_documentos_avaliados']=len(documentos.resultados)
            metricas.contagens['pares_descobertos']=len(pares_enfileirados)
            metricas.contagens['verificacoes_links']=len(verificacoes_destinos)
            metas={nome_a:{'visitadas':len(visitados),'pendentes':len(fila),'motivo_parada':parada,
                           'referencias_excluidas':dict(excluded)},
                   nome_b:{'visitadas':len(visitados),'pendentes':len(fila),'motivo_parada':parada,
                           'referencias_excluidas':{}}}
            situacao='inconclusivo' if not paginas_a or not paginas_b else ('concluido' if completos else 'parcial')
            if parada and len(eventos)<600:eventos.append({'tipo':'INTERRUPCAO','par':len(visitados),'motivo':parada,
                'falhas_consecutivas':consecutivos,'pares_pendentes':len(fila)})
            metricas.tempos['processamento_final']=time.perf_counter()-inicio_final
            metricas.contagens['links_encontrados']=sum(len(p.links) if p.links else sum(bool(i.destino) for i in p.itens if i.tipo in ('Opção','Documento')) for p in [*paginas_a.values(),*paginas_b.values()])
            metricas.contagens['pares_com_falha']=len(pares_falhos)
            metricas.contagens['paginas_reutilizadas']=0  # Nenhuma coleta integral presumida equivalente.
            metricas.contagens['divs_consolidadas']=len(brutos)-len(divergencias)
            metricas.contagens['comparacoes_url_reaproveitadas']+=_link_equivalente.cache_info().hits-equiv_inicial.hits
            cache_final=_url_limpa.cache_info()
            metricas.contagens['normalizacoes_reaproveitadas']+=cache_final.hits-cache_inicial.hits
            metricas.contagens['normalizacoes_calculadas']+=cache_final.misses-cache_inicial.misses
            metricas.contagens['pares_comparados']=comparados()
            metricas.contagens['pares_pendentes']=len(fila)
            metricas.contagens['preparacoes_profundas']=metricas.contagens['operacoes_preparacao']
            metricas.contagens['pares_editoriais_amostrados']=len(escopo.representantes)
            metricas.contagens['pares_nao_aprofundados']=len(fila.adiados)
            metricas.contagens['pares_visitados']=len(visitados)
            metricas.contagens['pares_admitidos_html']=admitidos()
            metricas.contagens['referencias_candidatas']=len(candidatos)
            metricas.contagens['pares_inconclusivos']=inconclusivos()
            metricas.finalizar()
            metricas.contagens['pares_por_minuto']=round(comparados()*60/metricas.duracao,4) if metricas.duracao else 0
            cobertura=resumo_cobertura()
            return {**metricas.temporal(),'cobertura':cobertura,'motivo_encerramento':motivo_encerramento,'estados_pares':[{'par':list(k),'estado':v} for k,v in estados_pares.items()],'fila_pendente':[list(p) for p in fila],'segmentos_coleta':segmentos,'estado_execucao':'interrompido' if parar.is_set() else 'finalizado','andamento':dict(andamento),
                'media_segundos_por_par':round(metricas.duracao/len(paginas_a),6) if paginas_a else None,
                'requisicoes_por_par':round(metricas.resultado()['contagens']['requisicoes_total']/len(paginas_a),3) if paginas_a else None,
                'versao':'1.5','ambientes':{nome_a:base_a,nome_b:base_b},
                'paginas':{nome_a:len(paginas_a),nome_b:len(paginas_b)},
                'completo':{nome_a:completos,nome_b:completos},
                'meta_varredura':metas,'situacao_analise':situacao,
                'modo_varredura':'inteligente' if varredura_inteligente else 'atual',
                'metricas':metricas.resultado(),'otimizacao':inteligencia.resultado(),
                'resultados_funcionais':resultados_funcionais,'diferencas_esteticas':diferencas_esteticas,'documentos_verificados':documentos_relatorio,'verificacoes_destinos':verificacoes_destinos,
                'registros_editoriais':editoriais,
                'bloqueios_seguranca':list(bloqueios.values()),'falhas':falhas,'eventos_diagnostico':eventos,'ambiente_desatualizado':modo_defasado,
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
                'limite_paginas':limite_html if dinamica else MAX_URLS_SEGURANCA,'profundidade':None}
        finally:
            ctx_a.close();ctx_b.close();browser.close()
