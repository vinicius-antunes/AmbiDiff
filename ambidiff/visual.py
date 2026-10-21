"""Indícios de ícones e disposição via DOM. Não substitui comparação por pixels.

Compara somente controles identificáveis nos dois ambientes. Mudança de código
SVG/classe de ícone é sinal de revisão, não prova de imagem final distinta.
"""
from __future__ import annotations
from collections import defaultdict
from urllib.parse import urlsplit
import re
from .core import normalizar

_JS = r'''() => {
  const clean=s=>String(s||'').replace(/\s+/g,' ').trim().slice(0,110);
  const visible=el=>{
    if(!el || el.closest('[hidden],[aria-hidden="true"],nav,header,footer,[role="navigation"]'))return false;
    const st=getComputedStyle(el),r=el.getBoundingClientRect();
    return st.visibility!=='hidden'&&st.display!=='none'&&r.width>=8&&r.height>=8;
  };
  const out=[];
  for(const el of [...document.querySelectorAll('a[href],button')].slice(0,600)){
    if(!visible(el))continue;
    const name=clean(el.innerText||el.getAttribute('aria-label')||el.title||el.querySelector('img')?.alt);
    if(!name||name.length<3||name.length>90)continue;
    let href='';try{href=el.href?new URL(el.href).pathname:''}catch(e){}
    if(/^\/(w\/|noticias\/|blog\/)/i.test(href))continue;
    const svg=el.querySelector('svg'),icon=el.querySelector('i'),img=el.querySelector('img');
    const r=el.getBoundingClientRect();
    let source='',formato='';
    if(svg){formato='svg';source=[...svg.querySelectorAll('path,use,polygon,rect,circle')]
       .map(x=>x.getAttribute('d')||x.getAttribute('href')||x.getAttribute('xlink:href')||x.outerHTML).join('|').slice(0,750);}
    else if(icon){formato='classe';source=String(icon.className||'').replace(/\s+/g,' ').trim();}
    else if(img){const im=img.getBoundingClientRect();
      if(im.width<=96&&im.height<=96){formato='imagem';try{source=new URL(img.currentSrc||img.src).pathname}catch(e){source=img.getAttribute('src')||''}}
    }
    const tag=el.closest('section,article,main')?.querySelector('h1,h2,h3')?.innerText?.trim().slice(0,75)||'';
    out.push({nome:name,formato,assinatura:source,href,local:tag,
      geometria:{x:Math.round(r.left),y:Math.round(r.top+scrollY),w:Math.round(r.width),h:Math.round(r.height)}});
  }
  return out;
}'''


def comparar_visuais(page_a,page_b,pa,pb,nome_a='PRD',nome_b='DES',defasado=False):
    """Encontra alterações de ícone e grandes deslocamentos; somente em pares únicos."""
    try:a=page_a.evaluate(_JS);b=page_b.evaluate(_JS)
    except Exception:return [],[]
    ga=defaultdict(list);gb=defaultdict(list)
    for i in a:ga[normalizar(i['nome'])].append(i)
    for i in b:gb[normalizar(i['nome'])].append(i)
    icones=[];layouts=[]
    for key in ga.keys() & gb.keys():
        if len(ga[key])!=1 or len(gb[key])!=1:continue
        ia,ib=ga[key][0],gb[key][0]
        if ia.get('href') and ib.get('href') and ia['href']!=ib['href']:continue
        if ia.get('formato') and ib.get('formato') and ia.get('assinatura') and ib.get('assinatura'):
            # Comparar apenas alterações explícitas de SVG ou classes de ícone.
            # Caminhos de imagens diferentes permanecem referências inconclusivas.
            if ia['formato']==ib['formato'] and ia['formato'] in ('svg','classe') and ia['assinatura']!=ib['assinatura']:
                icones.append({'tipo':'Ícone','categoria':'Ícones e aparência',
                  'presente_em':nome_a,'nao_identificado_em':nome_b,'pagina':pa.titulo,
                  'url_presente':pa.url,'url_comparada':pb.url,'local':ia.get('local','') or 'Componente de navegação',
                  'caminho':' → '.join(pa.trilha),'posicao':'Conteúdo principal',
                  'elemento':ia['nome'],'assinatura_a':ia['assinatura'][:220],
                  'assinatura_b':ib['assinatura'][:220],
                  'situacao':'Código do ícone diferente — revisão visual',
                  'descricao':f'O controle "{ia["nome"]}" existe nos dois ambientes, mas seu ícone '
                              f'({ia["formato"]}) tem representação HTML diferente em {nome_a} e {nome_b}. '
                              'Isso sugere alteração de ícone, mas requer confirmação visual.'})
        # Somente deslocamentos muito grandes (não diferenças de 2-10 px).
        # Em conteúdo editorial defasado, a altura da lista desloca o restante.
        if defasado or len(layouts)>=5:continue
        xa,xb=ia['geometria'],ib['geometria']
        if abs(xa['x']-xb['x'])>140 or abs(xa['w']-xb['w'])>240:
            layouts.append({'tipo':'Layout','elemento':ia['nome'],'ambiente_a':nome_a,'ambiente_b':nome_b,
                'url_presente':pa.url,'url_comparada':pb.url,'caminho':' → '.join(pa.trilha),
                'motivo':f'Diferença grande de posição/tamanho do controle, a confirmar na captura. '
                         f'{nome_a}: x={xa["x"]}, largura={xa["w"]}; {nome_b}: x={xb["x"]}, largura={xb["w"]}.',
                'destino_a':'','destino_b':''})
    return icones[:8],layouts
