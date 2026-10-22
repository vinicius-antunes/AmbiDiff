"""Fragmentos: equivalência somente com âncora de rolagem observada no DOM."""
from urllib.parse import urlsplit,unquote

JS_ANCORA=r'''({fragmento,seletor})=>{
 const a=document.querySelector(seletor),id=decodeURIComponent(fragmento),target=document.getElementById(id)||document.getElementsByName(id)[0];
 if(!a||a.hasAttribute('onclick')||a.getAttribute('role')==='tab')return false;
 if([...document.scripts].some(s=>/location\s*\.\s*hash|hashchange|pushState|replaceState/.test(s.textContent)))return false;
 return !!target&&!target.matches('[role="tabpanel"],[role="tab"],input,button,select')&&!a.hasAttribute('aria-controls');
}'''


def fragmento(ia,ib,page_a,page_b,base_a,base_b):
    from .paired import link_equivalente
    a,b=urlsplit(ia.destino),urlsplit(ib.destino)
    if a.fragment==b.fragment or not link_equivalente(a._replace(fragment='').geturl(),b._replace(fragment='').geturl(),base_a,base_b):return None
    if any(f.startswith(('/','!')) or '=' in f for f in (a.fragment,b.fragment)):return 'funcional'
    for item,page,p in ((ia,page_a,a),(ib,page_b,b)):
        if not p.fragment:continue
        atual=urlsplit(page.url)
        if (atual.scheme,atual.netloc,atual.path,atual.query)!=(p.scheme,p.netloc,p.path,p.query):return 'inconclusivo'
        try:
            if not item.seletor or not page.evaluate(JS_ANCORA,{'fragmento':p.fragment,'seletor':item.seletor}):return 'inconclusivo'
        except Exception:return 'inconclusivo'
    return 'rolagem'
