"""Sinais estruturais observados no DOM, sem inferir ações nem destinos."""
from collections import defaultdict


JS_SEMANTICA = r'''
  const papeis = new Set('button link tab menuitem menuitemcheckbox menuitemradio switch checkbox radio combobox'.split(' '));
  const grupos = 'nav,aside,header,footer,section,article,fieldset,form,dialog,[role="navigation"],[role="menu"],[role="menubar"],[role="tablist"],[role="group"],[role="region"],[role="dialog"],[role="tabpanel"],[role="complementary"],[role="banner"],[role="contentinfo"]';
  const controles = 'button,summary,input[type="button"],[role~="button"],[role~="link"],[role~="tab"],[role~="menuitem"],[role~="menuitemcheckbox"],[role~="menuitemradio"],[role~="switch"],[role~="checkbox"],[role~="radio"],[role~="combobox"]';
  const areasMenu = 'nav,aside,[role="navigation"],[role="menu"],[role="menubar"],[role="tablist"],ul,ol,[class*="menu" i],[class*="tabs" i],[class*="cards" i],[class*="grid" i],[class*="list" i]';
  const ariaRole = el => clean(el.getAttribute('role')).toLowerCase();
  let ids;
  const porId = id => {
    if(!ids){
      ids = new Map();
      for(const e of document.querySelectorAll('[id]')) ids.set(e.id, ids.has(e.id) ? null : e);
    }
    return ids.get(id) || null;
  };
  const referencias = (el, attr) => clean(el.getAttribute(attr)).split(' ').filter(Boolean);
  const rotuloAcessivel = el => {
    const refs = referencias(el, 'aria-labelledby');
    const partes = refs.map(id => {
      const ref = porId(id);
      return ref && clean(ref === el ? ref.getAttribute('aria-label') || ref.innerText : ref.getAttribute('aria-label') || ref.textContent);
    }).filter(Boolean);
    if(partes.length) return {nome: clean(partes.join(' ')), origem: 'aria-labelledby', incompleto: partes.length !== refs.length};
    const direto = clean(el.getAttribute('aria-label'));
    if(direto) return {nome: direto, origem: 'aria-label', incompleto: refs.length > 0};
    const labels = clean(Array.from(el.labels || [], label => clean(label.textContent)).join(' '));
    if(labels) return {nome: labels, origem: 'label'};
    return {nome: '', origem: '', incompleto: refs.length > 0};
  };
  const textoControle = el => {
    const texto = clean(el.matches('input[type="button"]') ? el.value : el.innerText);
    return /[\p{L}\p{N}]/u.test(texto) ? texto : '';
  };
  const nomeControle = (el, acessivel, alternativas='') => textoControle(el) || acessivel.nome || clean(el.innerText) || clean(alternativas);
  const foraDaArvore = el => !!el.closest('[aria-hidden="true" i],[hidden],[inert],dialog:not([open])');
  const disponivel = el => !el.matches(':disabled') && !el.closest('[aria-disabled="true" i]');
  const visivelControle = el => !foraDaArvore(el) &&
    (typeof el.checkVisibility !== 'function' || el.checkVisibility({checkOpacity:true, checkVisibilityCSS:true}));
  const papelDoGrupo = el => {
    const role = ariaRole(el);
    return role || ({NAV:'navigation',ASIDE:'complementary',HEADER:'banner',FOOTER:'contentinfo',
      DIALOG:'dialog',FIELDSET:'group',FORM:'form',SECTION:'region',ARTICLE:'article'})[el.tagName] || '';
  };
  const donos = new WeakMap();
  const hierarquia = el => {
    const grupo = el.parentElement?.closest(grupos);
    if(!grupo) return {};
    if(donos.has(grupo)) return donos.get(grupo);
    const papel = papelDoGrupo(grupo);
    const titulo = g => rotuloAcessivel(g).nome || clean(g.querySelector(':scope > h1,:scope > h2,:scope > h3,:scope > legend')?.textContent);
    const nav = grupo.closest('nav,[role="navigation"],[role="menu"],[role="menubar"]');
    const ancestral = nav?.parentElement?.closest('nav,[role="navigation"]');
    const nome = titulo(grupo) || (ancestral ? titulo(ancestral) : '');
    const res = {grupo:papel, grupo_nome:nome};
    donos.set(grupo,res);
    return res;
  };
  const alvoControle = el => {
    const refs = referencias(el, 'aria-controls');
    if(refs.length) return refs.length === 1 ? porId(refs[0]) : null;
    const ref = el.getAttribute('data-bs-target') || el.getAttribute('href') || '';
    if(ref.startsWith('#') && ref.length>1) return porId(ref.slice(1));
    return null;
  };
  const estadosARIA = {expanded:['true','false'],selected:['true','false'],
    current:['true','false','page','step','location','date','time'],checked:['true','false','mixed'],
    pressed:['true','false','mixed'],disabled:['true','false'],
    haspopup:['true','false','menu','listbox','tree','grid','dialog']};
  const descreverControle = (el, acessivel, href='') => {
    const role = ariaRole(el).split(' ').find(token => papeis.has(token));
    const nativo = {BUTTON:'button',SUMMARY:'button',INPUT:'button',SELECT:'combobox'}[el.tagName] || (href && 'link');
    const papel = role || (el.matches('[data-bs-toggle="tab"]') ? 'tab' : nativo);
    if(!papel) return null;
    const dono = hierarquia(el);
    const details = el.matches('details > summary:first-of-type') ? el.parentElement : null;
    const alvo = alvoControle(el);
    const estados = {};
    const invalidos = [];
    for(const [chave, validos] of Object.entries(estadosARIA)){
      const val = el.getAttribute('aria-'+chave);
      if(val === null) continue;
      const valor = clean(val).toLowerCase();
      if(validos.includes(valor)) estados[chave] = chave==='haspopup' && valor==='true' ? 'menu' : valor;
      else invalidos.push(chave);
    }
    if(href && !role && !Object.keys(estados).length && !invalidos.length &&
       !acessivel.origem && !acessivel.incompleto && !['navigation','menu','menubar'].includes(dono.grupo)) return null;
    estados.disabled = String(!disponivel(el));
    if(details){
      if(estados.expanded !== undefined && estados.expanded !== String(details.open)) invalidos.push('expanded');
      estados.expanded = String(details.open);
    }
    const declaracaoAlvo = el.hasAttribute('aria-controls') || el.hasAttribute('data-bs-target');
    if(declaracaoAlvo && !alvo) invalidos.push('controls');
    if(acessivel.incompleto) invalidos.push('labelledby');
    if((papel==='link' || papel==='menuitem') && !href) invalidos.push('destino');
    if(href && !['link','menuitem'].includes(papel) &&
       !(papel==='tab' && alvo && el.getAttribute('href')==='#'+alvo.id)) invalidos.push('destino');
    if(href && ['link','menuitem'].includes(papel)){
      estados.target = clean(el.getAttribute('target')) || '_self';
      estados.download = String(el.hasAttribute('download'));
    }
    // Roving tabindex é esperado em menus e abas. Um DIV apenas com role continua sem evidência de foco.
    const foco = !!nativo || el.tabIndex>=0 ||
      (el.tabIndex===-1 && el.hasAttribute('tabindex') && ['tablist','menu','menubar'].includes(dono.grupo));
    if(!foco) invalidos.push('foco');
    const expansivel = !!details || (papel==='button' && estados.expanded !== undefined);
    const alvoPapel = details ? 'disclosure' : alvo ? (expansivel ? 'disclosure' : papelDoGrupo(alvo) || 'conteudo') : '';
    if(alvo && (expansivel || (papel==='tab' && alvoPapel==='tabpanel'))){
      const estado = expansivel ? 'expanded' : 'selected';
      if(estados[estado] !== undefined && estados[estado] !== String(visivelControle(alvo))) invalidos.push(estado);
    }
    const alvoNome = alvo ? rotuloAcessivel(alvo).nome : '';
    return {...dono, papel:expansivel?'disclosure':papel, nome:acessivel.nome, origem:acessivel.origem,
      estados, alvo:alvoPapel, alvo_nome:alvoNome, invalidos};
  };
'''


def papel_funcional(item):
    papel = item.semantica.get('papel')
    if item.destino and papel in ('link', 'menuitem'):
        return 'link'
    return papel


def papeis_de_link_compativeis(a, b):
    """Preserva a comparação de destinos dos checkpoints sem metadados."""
    papel_a, papel_b = papel_funcional(a), papel_funcional(b)
    return not papel_a or not papel_b or papel_a == papel_b


def sinais_consistentes(a, b):
    return not a.semantica.get('invalidos') and not b.semantica.get('invalidos')


def _grupo(item, normalizar):
    papel = item.semantica.get('grupo', '')
    if papel in ('navigation', 'menu', 'menubar'):
        papel = 'navigation'
    nome = item.semantica.get('grupo_nome', '')
    return papel, normalizar(nome)


def _mesma_funcao(a, b, base_a, base_b, normalizar, link_equivalente):
    sa, sb = a.semantica, b.semantica
    papel = papel_funcional(a)
    if papel != papel_funcional(b) or not sinais_consistentes(a,b):
        return False
    grupo_a, grupo_b = _grupo(a, normalizar), _grupo(b, normalizar)
    if papel == 'link':
        contexto = grupo_a == grupo_b or (grupo_a[1] and grupo_a[1] == grupo_b[1]
            and 'navigation' in (grupo_a[0], grupo_b[0]))
        return bool(contexto and a.destino and b.destino and link_equivalente(a.destino, b.destino, base_a, base_b))
    if not grupo_a[0] or grupo_a != grupo_b:
        return False
    alvo_a, alvo_b = sa.get('alvo'), sb.get('alvo')
    if papel == 'tab' and (grupo_a[0] != 'tablist' or alvo_a != 'tabpanel' or alvo_b != 'tabpanel'):
        return False
    if papel == 'disclosure' and not (alvo_a and alvo_b):
        return False
    if alvo_a != alvo_b or (not alvo_a and not grupo_a[1]):
        return False
    nomes = [normalizar(s.get('alvo_nome')) for s in (sa, sb)]
    # O painel pode ser rotulado pelo próprio controle em um só ambiente.
    nomes = [n for n in nomes if n and n != normalizar(a.nome)]
    return len(set(nomes)) <= 1


def correspondencias(a, b, base_a, base_b):
    """Pareamento mútuo, indexado pelo tipo e rótulo exato de cada controle."""
    from .core import normalizar
    from .paired import link_equivalente

    def agrupar(itens):
        grupos = defaultdict(list)
        for i in itens:
            if i.tipo in ('Opção', 'Documento') and i.funcao != 'paginacao':
                grupos[(i.tipo, normalizar(i.nome))].append(i)
        return grupos

    ga, gb = agrupar(a), agrupar(b)
    for chave in ga:
        if chave not in gb:
            continue
        aa, bb = ga[chave], gb[chave]
        if not any(i.semantica for i in aa) or not any(i.semantica for i in bb):
            continue
        # Lotes repetidos permanecem inconclusivos e limitam o custo por rótulo.
        if len(aa) > 8 or len(bb) > 8:
            yield aa[0], None, 'Rótulo estrutural repetido sem par inequívoco.'
            continue
        candidatos_a = defaultdict(list)
        candidatos_b = defaultdict(list)
        for ia in aa:
            for ib in bb:
                if ia.semantica and ib.semantica and _mesma_funcao(ia, ib, base_a, base_b, normalizar, link_equivalente):
                    candidatos_a[id(ia)].append(ib)
                    candidatos_b[id(ib)].append(ia)
        for ia in aa:
            if not ia.semantica:
                continue
            candidatos = candidatos_a[id(ia)]
            if len(candidatos) != 1 or len(candidatos_b[id(candidatos[0])]) != 1:
                yield ia, None, 'Papel, contexto, destino ou duplicação impedem uma correspondência estrutural única.'
                continue
            ib = candidatos[0]
            va, vb = ia.semantica['estados'], ib.semantica['estados']
            padroes_falsos = {'current', 'haspopup'}
            comparaveis = (va.keys() & vb.keys()) | padroes_falsos
            mudancas = [k for k in comparaveis if va.get(k, 'false') != vb.get(k, 'false')]
            if mudancas:
                detalhe = ', '.join(f'{k} ({va.get(k, "false")} / {vb.get(k, "false")})' for k in sorted(mudancas))
                yield ia, ib, detalhe
            elif (va.keys() ^ vb.keys()) - padroes_falsos:
                yield ia, None, 'Estado explícito disponível em apenas um ambiente.'
            elif va.get('disabled') == 'true':
                yield ia, None, 'Controles indisponíveis nos dois ambientes.'
            else:
                yield ia, ib, ''
