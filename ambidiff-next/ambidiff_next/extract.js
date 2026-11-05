() => {
  const text = e => String(e?.getAttribute('aria-label') || (e?.getAttribute('aria-labelledby') || '').split(/\s+/).map(id=>document.getElementById(id)?.textContent || '').join(' ') || e?.getAttribute('alt') || e?.innerText || e?.textContent || e?.getAttribute('title') || e?.getAttribute('name') || '').replace(/\s+/g,' ').trim().slice(0,300);
  const role = e => e.getAttribute('role') || ({A:'link',BUTTON:'button',NAV:'navigation',IMG:'img',FORM:'form',INPUT:'textbox',SELECT:'combobox',TEXTAREA:'textbox',SUMMARY:'button'}[e.tagName] || (e.matches('h1,h2,h3,h4,h5,h6')?'heading':''));
  const section = e => {const p=e.closest('nav,[role=navigation],header,footer,aside,section,article,main,[role=tabpanel]');return p ? text(p.querySelector('h1,h2,h3,h4')) || p.getAttribute('aria-label') || p.getAttribute('role') || p.tagName.toLowerCase() : 'Conteúdo principal';};
  const selector = e => {const bits=[];let n=e;while(n && n.nodeType===1 && n!==document.documentElement){let i=1;for(let p=n.previousElementSibling;p;p=p.previousElementSibling)if(p.tagName===n.tagName)i++;bits.unshift(n.tagName.toLowerCase()+':nth-of-type('+i+')');n=n.parentElement;}return bits.join(' > ');};
  const editorial = e => {
    if(e.closest('nav,header,footer,[role=navigation]'))return false;
    const label=text(e).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    if(/audio|servico|consulta|legisla|institucional/.test(label))return false;
    const parent=e.closest('section,article');
    const context=String(parent?.getAttribute('aria-label') || parent?.querySelector('h1,h2,h3')?.textContent || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    return e.matches('time') || !!e.closest('[class*=news i],[class*=noticia i],[class*=galeria i]') || /noticia|evento|galeria|historico/.test(context) || /\/(noticias?|news|eventos?|galerias?|historico)\//i.test(e.getAttribute('href') || '');
  };
  const items=[];
  for(const e of document.querySelectorAll('a[href],button,[role=button],[role=tab],summary,nav,[role=navigation],form,input,select,textarea,img,h1,h2,h3,section[aria-label],[role=region]')){
    const r=e.getBoundingClientRect(),s=getComputedStyle(e),ro=role(e),name=text(e);
    const visible=!!(r.width && r.height && s.display!=='none' && s.visibility!=='hidden' && Number(s.opacity)!==0 && !e.closest('[hidden],[aria-hidden=true],[inert]'));
    const cx=Math.min(innerWidth-1,Math.max(0,r.x+r.width/2)),cy=Math.min(innerHeight-1,Math.max(0,r.y+r.height/2));
    const top=(visible && r.x<innerWidth && r.y<innerHeight && r.right>0 && r.bottom>0)?document.elementFromPoint(cx,cy):null;
    const occluded=!!top && top!==e && !e.contains(top) && !top.contains(e);
    const target=e.getAttribute('aria-controls');
    const panel=target?document.getElementById(target):null;
    const kind=e.tagName==='A'?'link':ro==='tab'?'tab':e.matches('button,[role=button],summary')?'button':e.matches('nav,[role=navigation]')?'menu':e.tagName==='IMG'?'image':e.tagName==='FORM'?'form':e.matches('input,select,textarea')?'field':ro==='heading'?'heading':'section';
    const parent=e.parentElement?.closest('nav,[role=navigation],section,article,main,[role=tabpanel]');
    const label=kind==='menu' ? (e.getAttribute('aria-label') || e.getAttribute('title') || 'Menu de navegação') : kind==='form' ? (e.getAttribute('aria-label') || e.getAttribute('title') || 'Formulário') : name;
    items.push({kind,name:label || (kind==='field' ? 'Campo sem rótulo' : kind),role:ro,section:section(e),parent:parent?.getAttribute('aria-label') || parent?.tagName.toLowerCase() || '',
      selector:selector(e),url:e.href || (e.tagName==='IMG'?e.currentSrc || e.src:''),visible,enabled:!e.disabled && e.getAttribute('aria-disabled')!=='true',
      bbox:{x:r.x,y:r.y,width:r.width,height:r.height},editorial:editorial(e),attrs:{tag:e.tagName.toLowerCase(),type:e.getAttribute('type') || '',
        aria_controls:target || '',aria_expanded:e.getAttribute('aria-expanded'),aria_selected:e.getAttribute('aria-selected'),panel_visible:panel?!!(panel.getBoundingClientRect().height && getComputedStyle(panel).display!=='none'):null,
        download:e.hasAttribute('download'),inline_handler:!!e.getAttribute('onclick'),occluded,clipped:!!(e.scrollWidth>e.clientWidth+2 && s.overflowX==='hidden') || !!(e.scrollHeight>e.clientHeight+2 && s.overflowY==='hidden'),
        style:{color:s.color,background:s.backgroundColor,font:s.fontFamily,font_size:s.fontSize,font_weight:s.fontWeight,visibility:s.visibility,display:s.display,opacity:s.opacity},
        text_only:!e.querySelector('img,svg,canvas,video') && getComputedStyle(e,'::before').content.match(/^(none|normal)$/)!==null && getComputedStyle(e,'::after').content.match(/^(none|normal)$/)!==null && s.backgroundImage==='none',visible_text:String(e.innerText || '').trim(),
        dynamic:e.matches('time') || !!e.closest('[aria-live],[class*=carousel i],[class*=counter i]'),password:e.matches('input[type=password]')}});
  }
  return {title:document.title,ready:document.readyState,items,auth:!!document.querySelector('input[type=password]'),viewport:{width:innerWidth,height:innerHeight}};
}
