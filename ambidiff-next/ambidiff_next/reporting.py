"""Exportações locais. Revisão e seleção são projeções: os dados brutos não mudam."""
import base64
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from io import BytesIO, StringIO
import json
from pathlib import Path
import re
import unicodedata
import zipfile


@dataclass
class Export:
    data: bytes
    mimetype: str
    filename: str


def review_for(report, finding_id):
    reviews=report.get('reviews',{})
    if isinstance(reviews,list):
        return next((x for x in reviews if x.get('id')==finding_id or x.get('finding_id')==finding_id),{})
    value=reviews.get(finding_id,{})
    return value if isinstance(value,dict) else {'status':value}


def selected_ids(report):
    return {r['id'] for r in report.get('findings',[]) if review_for(report,r['id']).get('selected')}


def scoped_report(report, scope='all'):
    """Retém IDs de ocorrências sem duplicar membros de DIVs consolidadas."""
    result=dict(report)
    if scope=='selected':
        selected=selected_ids(report)
        rows=[row for row in report.get('findings',[]) if row['id'] in selected and review_for(report,row['id']).get('status')!='hidden']
        occurrence_ids={v for row in rows for v in row.get('occurrence_ids',[row['id']])}
        result['findings']=rows
        result['occurrences']=[r for r in report.get('occurrences',[]) if r['id'] in occurrence_ids]
        result['reviews']={row['id']:review_for(report,row['id']) for row in rows}
        # Uma exportação de DIVs não encaminha o inventário ou o log integral.
        # Esses detalhes continuam intactos na exportação completa local.
        for key in ('pages','tasks','logs','diagnostics'):result.pop(key,None)
        run=report.get('run',{})
        result['run']={key:run[key] for key in ('id','status','metrics','created_at','updated_at') if key in run}
        config=run.get('config',{})
        result['run']['config']={key:config[key] for key in ('name','roots','labels','outdated','viewport') if key in config}
        result['export_limitations']=['Escopo selecionado: páginas, fila, logs e diagnóstico integral não são encaminhados. Consulte a exportação completa para esses dados.']
    result['export_scope']=scope
    result['exported_at']=datetime.now(timezone.utc).isoformat()
    return result


def safe_filename(name):
    value=''.join(c for c in unicodedata.normalize('NFKD',str(name or 'Comparacao')) if not unicodedata.combining(c))
    value=re.sub(r'[^a-zA-Z0-9_-]+','_',value).strip('_. ')[:64] or 'Comparacao'
    if value.upper() in {'CON','PRN','AUX','NUL',*(f'{p}{i}' for p in ('COM','LPT') for i in range(1,10))}:value='Portal_'+value
    return value


def evidence_file(root, name):
    if not isinstance(name,str) or not name or len(name)>240:return None
    root=Path(root).resolve()
    path=(root/name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower()!='.png':return None
    if path.stat().st_size>3_000_000:return None
    with path.open('rb') as stream:
        if stream.read(8)!=b'\x89PNG\r\n\x1a\n':return None
    return path


def evidence_names(value):
    if isinstance(value,str):
        if value.lower().endswith('.png'):yield value
    elif isinstance(value,dict):
        for item in value.values():yield from evidence_names(item)
    elif isinstance(value,list):
        for item in value:yield from evidence_names(item)


def csv_safe(value):
    if isinstance(value,(list,dict)):value=json.dumps(value,ensure_ascii=False)
    text=str(value if value is not None else '')
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text


def html_report(report, evidence_dir):
    run=report.get('run',{});config=run.get('config',{});budget=20_000_000
    def esc(value):return escape(str(value or ''),quote=True)
    def link(url):
        if not re.match(r'^https?://',str(url or ''),re.I):return esc(url)
        return f'<a rel="noopener noreferrer" href="{esc(url)}">{esc(url)}</a>'
    cards=[]
    for row in report.get('findings',[]):
        images=[]
        for name in dict.fromkeys(evidence_names(row.get('evidence',{}))):
            path=evidence_file(evidence_dir,name)
            if path is None:continue
            size=path.stat().st_size
            if size>budget:continue
            budget-=size
            images.append(f'<figure><img alt="{esc(name)}" src="data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}"><figcaption>{esc(name)}</figcaption></figure>')
        cards.append(f'''<article><h2>{esc(row['id'])} · {esc(row.get('element'))}</h2>
<p>{esc(row.get('nature'))} · impacto {esc(row.get('impact'))} · confiança {esc(row.get('confidence'))}</p>
<p>Local: {esc(row.get('section'))} · {esc(row.get('path'))}</p>
<p><b>Fato observado:</b> {esc(row.get('fact') or row.get('code'))}</p>
<table><tr><th>Ambiente A</th><th>Ambiente B</th></tr><tr><td>{link(row.get('page_a'))}<p>{esc(row.get('observed_a'))}</p></td><td>{link(row.get('page_b'))}<p>{esc(row.get('observed_b'))}</p></td></tr></table>
<p>Possível causa: {esc(row.get('possible_cause') or 'Não determinada')}</p>
<p>Verificação recomendada: {esc(row.get('recommendation') or 'Revisão humana')}</p>
<p>Ocorrências: {esc(row.get('count',1))} · revisão: {esc(review_for(report,row['id']).get('status','pending'))}</p>
<div class="images">{''.join(images) or '<p>Sem capturas válidas disponíveis para esta DIV.</p>'}</div></article>''')
    return f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AmbiDiff Next · {esc(config.get('name'))}</title><style>body{{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:auto;padding:24px;color:#15243a}}article{{border:1px solid #b8c9da;border-radius:10px;padding:20px;margin:20px 0;break-inside:avoid}}table{{width:100%;table-layout:fixed}}td,th{{text-align:left;vertical-align:top;overflow-wrap:anywhere}}.images{{display:flex;flex-wrap:wrap;gap:12px}}figure{{margin:0;max-width:46%}}img{{max-width:100%}}pre{{white-space:pre-wrap}}</style><h1>AmbiDiff Next · {esc(config.get('name') or 'Comparação')}</h1><p>Execução {esc(run.get('id'))} · Estado: {esc(run.get('status'))} · Escopo: {esc(report.get('export_scope'))}</p><p>Ambientes: {' · '.join(link(u) for u in config.get('roots',[]))}</p><p>Fila processada não comprova cobertura integral. Itens amostrados, não testados e inconclusivos não foram validados.</p><h2>Cobertura e métricas</h2><pre>{esc(json.dumps(run.get('metrics',{}),ensure_ascii=False,indent=2))}</pre>{''.join(cards) or '<p>Nenhuma DIV neste escopo.</p>'}<h2>Limitações e diagnóstico</h2><p>Imagens incorporadas: até 3 MB por arquivo e 20 MB no total. O ZIP permite até 100 MB no total e mantém o mesmo limite de 3 MB por imagem; arquivos maiores permanecem na pasta local de evidências. Testes locais não comprovam validação em produção.</p><pre>{esc(json.dumps(report.get('diagnostics',[]),ensure_ascii=False,indent=2))}</pre></html>'''.encode('utf-8')


def export_report(report,format,evidence_dir,scope='all'):
    if scope not in ('all','selected'):raise ValueError('Escopo inválido')
    report=scoped_report(report,scope)
    run=report.get('run',{});config=run.get('config',{})
    base=safe_filename(config.get('name'))+'_'+('DIVs_Selecionadas' if scope=='selected' else 'Comparacao')+'_'+datetime.now().strftime('%Y-%m-%d')+'_'+safe_filename(run.get('id',''))[-8:]
    if format=='json':return Export(json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8'),'application/json',base+'.json')
    if format=='html':return Export(html_report(report,evidence_dir),'text/html; charset=utf-8',base+'.html')
    if format=='csv':
        out=StringIO(newline='');fields=['id','orgao','nature','impact','confidence','element','section','path','page_a','page_b','observed_a','observed_b','fact','possible_cause','recommendation','count','review','occurrence_ids']
        writer=csv.DictWriter(out,fieldnames=fields,delimiter=';',extrasaction='ignore');writer.writeheader()
        seen=set()
        for row in report.get('findings',[]):
            if row['id'] in seen:continue
            seen.add(row['id']);data={**row,'orgao':config.get('name',''),'review':review_for(report,row['id']).get('status','pending')}
            writer.writerow({k:csv_safe(data.get(k,'')) for k in fields})
        return Export(out.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8',base+'.csv')
    if format=='zip':
        out=BytesIO();budget=100_000_000
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('relatorio.json',json.dumps(report,ensure_ascii=False,indent=2))
            archive.writestr('relatorio.html',html_report(report,evidence_dir))
            archive.writestr('diagnostico.json',json.dumps({'tasks':report.get('tasks',[]),'diagnostics':report.get('diagnostics',[]),'metrics':run.get('metrics',{})},ensure_ascii=False,indent=2))
            archive.writestr('execucao.log','\n'.join(str(x.get('time',''))+' '+str(x.get('message','')) for x in report.get('logs',[])))
            omissions=[]
            for name in dict.fromkeys(evidence_names([row.get('evidence',{}) for row in report.get('findings',[])])):
                path=evidence_file(evidence_dir,name)
                if path is None:omissions.append(name);continue
                size=path.stat().st_size
                if size>budget:omissions.append(name);continue
                budget-=size;archive.write(path,'evidencias/'+path.relative_to(Path(evidence_dir).resolve()).as_posix())
            archive.writestr('LIMITES.txt','Pacote local. Imagens: até 3 MB por arquivo e 100 MB no total.\nOmitidas: '+', '.join(omissions))
        return Export(out.getvalue(),'application/zip',base+'.zip')
    raise ValueError('Formato inválido')
