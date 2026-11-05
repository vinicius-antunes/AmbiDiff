"""Comparação local de componentes com geometria e pixels de capturas reais."""
from pathlib import Path
from .models import finding,stable_id,normalized


def _image_path(root,relative):
    if not relative or not isinstance(relative,str):return None
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size>15_000_000:return None
    return path


def compare_components(a,b,evidence_dir,page_a='',page_b=''):
    from PIL import Image,ImageChops,ImageDraw
    root=Path(evidence_dir);findings=[];diagnostics=[]
    metrics={'completed':False,'pixels_compared':0,'different_fraction':None,'masks':[]}
    common={'element':a.name,'page_a':page_a,'page_b':page_b,'section':a.section}
    evidence={'a':a.attrs.get('screenshot',''),'b':b.attrs.get('screenshot','')}
    geometric=[]
    for name,va,vb in [('visibilidade',a.visible,b.visible),('sobreposicao',a.attrs.get('occluded',False),b.attrs.get('occluded',False)),('recorte',a.attrs.get('clipped',False),b.attrs.get('clipped',False))]:
        if va!=vb:geometric.append((name,str(va),str(vb)))
    paths=[_image_path(root,evidence.get(side,'')) for side in ('a','b')]
    if not all(paths):
        diagnostics.append({'element':a.id,'status':'visual_inconclusivo','reason':'Capturas válidas dos dois ambientes indisponíveis. Geometria DOM não é comparação de imagem.'})
        for name,va,vb in geometric:
            findings.append(finding(name+'_dom_diferente','visual',**common,evidence=evidence,confidence='possivel',observed_a=va,observed_b=vb,
                recommendation='Observar manualmente; comparação visual incompleta por ausência de capturas.'))
        return {'findings':findings,'diagnostics':diagnostics,'metrics':metrics}
    images=[]
    try:
        for path in paths:
            with Image.open(path) as image:
                if image.width*image.height>20_000_000:raise ValueError('Captura excede 20 milhões de pixels')
                image.load();images.append(image.convert('RGB'))
    except (OSError,ValueError,Image.DecompressionBombError) as exc:
        diagnostics.append({'element':a.id,'status':'visual_inconclusivo','reason':str(exc)[:200]})
        return {'findings':findings,'diagnostics':diagnostics,'metrics':metrics}
    size=(max(x.width for x in images),max(x.height for x in images))
    padded=[]
    for im in images:
        canvas=Image.new('RGB',size,'white');canvas.paste(im,(0,0));padded.append(canvas)
    mask=Image.new('L',size,255)
    # Máscaras precisam constar explicitamente nos dois lados com motivo igual.
    masks_a=a.attrs.get('masks',[]);masks_b=b.attrs.get('masks',[])
    accepted=[]
    for entry in masks_a:
        if not isinstance(entry,dict) or entry not in masks_b or not entry.get('reason'):continue
        box=entry.get('box')
        if not isinstance(box,(list,tuple)) or len(box)!=4 or any(not isinstance(v,(int,float)) for v in box):continue
        x0,y0,x1,y1=map(int,box)
        if not (0<=x0<x1<=size[0] and 0<=y0<y1<=size[1]):continue
        if (x1-x0)*(y1-y0)>size[0]*size[1]*.25:continue
        accepted.append((x0,y0,x1,y1,entry['reason']))
    # O total também é limitado, não só cada retângulo individual.
    for x0,y0,x1,y1,reason in accepted:
        candidate=mask.copy();ImageDraw.Draw(candidate).rectangle((x0,y0,x1-1,y1-1),fill=0)
        if sum(candidate.histogram()[1:])<size[0]*size[1]*.75:
            diagnostics.append({'element':a.id,'status':'mascara_rejeitada','reason':'Máscaras excederiam 25% da área do componente.'});continue
        mask=candidate;metrics['masks'].append({'box':[x0,y0,x1,y1],'reason':reason})
    diff=ImageChops.difference(*padded)
    bands=diff.split();gray=ImageChops.lighter(ImageChops.lighter(bands[0],bands[1]),bands[2])
    changed=gray.point(lambda v:255 if v>20 else 0)
    changed=ImageChops.multiply(changed,mask)
    area=sum(mask.histogram()[1:]);different=changed.histogram()[255]
    ratio=different/area if area else 0.0
    metrics.update(completed=True,pixels_compared=area,different_fraction=round(ratio,6))
    if metrics['masks']:diagnostics.append({'element':a.id,'status':'mascaras_aplicadas','masks':metrics['masks']})
    rounding_only=(all(abs(images[0].size[i]-images[1].size[i])<=1 for i in (0,1)) and
        all(abs(a.bbox.get(k,0)-b.bbox.get(k,0))<=1 for k in ('width','height')))
    text_raster=(a.kind==b.kind=='link' and a.attrs.get('text_only') is True and b.attrs.get('text_only') is True
        and a.attrs.get('visible_text')==b.attrs.get('visible_text') and a.attrs.get('visible_text')
        and a.attrs.get('style')==b.attrs.get('style') and bool(a.attrs.get('style')) and rounding_only and not geometric and ratio<.4)
    if images[0].size!=images[1].size and not text_raster:geometric.append(('dimensoes',str(images[0].size),str(images[1].size)))
    if text_raster and ratio>.02:
        diagnostics.append({'element':a.id,'status':'rasterizacao_textual_inconclusiva','reason':'Texto visível, estilos e geometria compatíveis; diferenças de pixels podem resultar de rasterização subpixel. Não classificado automaticamente como defeito.',
            'pixel_difference':round(ratio,6),'evidence':evidence,'sizes':[images[0].size,images[1].size]})
    for name,va,vb in geometric:
        findings.append(finding(name+'_divergente','visual',**common,evidence=evidence,confidence='confirmado',observed_a=va,observed_b=vb,
            recommendation='Geometria/estado observados; revisar impacto e finalidade antes de confirmar defeito.'))
    if ratio>.02 and not text_raster:
        filename=stable_id('diff',a.id,b.id,page_a,page_b)+'.png'
        root.mkdir(parents=True,exist_ok=True)
        # Vermelho marca pixels diferentes; áreas mascaradas permanecem neutras.
        overlay=Image.new('RGB',size,'white');overlay.paste((225,45,65),(0,0,*size),changed);overlay.save(root/filename)
        evidence=dict(evidence,diff=filename)
        findings.append(finding('aparencia_diferente','editorial' if a.editorial and b.editorial and normalized(a.name)!=normalized(b.name) else 'visual',**common,evidence=evidence,
            confidence='possivel',observed_a='Captura do componente A',observed_b=f'{ratio:.1%} dos pixels avaliados diferem',
            recommendation='Revisar imagens e diferença; conteúdo dinâmico ou editorial pode explicar a observação.',
            pixel_difference=round(ratio,6),masks=metrics['masks']))
    return {'findings':findings,'diagnostics':diagnostics,'metrics':metrics}
