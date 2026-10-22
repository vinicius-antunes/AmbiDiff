"""Exportação local de relatórios agrupados, com todas as ocorrências no JSON."""
from __future__ import annotations
import csv
import base64
from html import escape
import json
import time
from datetime import datetime
from pathlib import Path

CAMPOS=['classificacao','classificacao_automatica','motivo_relevancia','ids_agrupados','id','categoria','tipo','presente_em','nao_identificado_em','pagina',
        'caminho','posicao','local','elemento','destino_a','destino_b','ordem_a','ordem_b','texto_a','texto_b',
        'url_presente','url_comparada','ocorrencias_total','revisao_manual','evidencia','evidencias','marcacoes','descricao','situacao','tag_tecnica','tags','grau_confianca','justificativa_evidencia','teste_funcional_executado','grupos_relacionados','destino_final_a','destino_final_b','referencia','escopo','quantidade_itens','itens_resumo']


def exportar(dados:dict,pasta:Path,run_id:str)->dict:
    inicio_exportacao=time.perf_counter()
    from .relevance import preparar
    dados=preparar(dados,{r['id']:r['classificacao_manual'] for r in dados.get('divergencias',[]) if r.get('classificacao_manual')})
    completos=dados['divergencias']
    principais=[r for r in completos if r['classificacao'] not in ('baixa','editorial')]
    pasta.mkdir(parents=True,exist_ok=True)
    paths={ext:pasta/f'comparacao_{run_id}.{ext}' for ext in ('csv','json','html')}
    dados['divergencias']=completos if dados.get('exportacao_completa') else principais
    def csv_seguro(v):
        s=str(v or '')
        return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
    with paths['csv'].open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['site_nome',*CAMPOS,'paginas_afetadas'],delimiter=';',extrasaction='ignore')
        writer.writeheader()
        editoriais=[dict(r,classificacao='editorial',motivo_relevancia='Contexto editorial classificado na coleta; não comprova base desatualizada.') for r in dados.get('registros_editoriais',[])] if dados.get('exportacao_completa') else []
        for r in [*[member for row in dados['divergencias'] for member in (row.get('itens_agrupados') or [row])],*editoriais] if dados.get('exportacao_completa') else dados['divergencias']:
            linha={'site_nome':csv_seguro(dados.get('site_nome','')),
                   **{k:csv_seguro(r.get(k,'')) for k in CAMPOS}}
            linha['itens_resumo']=csv_seguro(' | '.join(x.get('elemento','') for x in r.get('itens_agrupados',[])))
            linha['paginas_afetadas']=csv_seguro(' | '.join(o.get('url_presente','') for o in r.get('ocorrencias',[])))
            writer.writerow(linha)
    esc=lambda v:escape(str(v or ''))
    def link(url):
        if not str(url or '').startswith(('http://','https://')):return esc(url or 'Não disponível')
        return f'<a href="{escape(str(url),quote=True)}" target="_blank" rel="noopener noreferrer">{esc(url)}</a>'
    cards=[]
    for d in dados['divergencias']:
        descr=esc(d.get('descricao',''))
        extra=''
        if d.get('destino_a'):
            extra=f'<p><b>Destino A:</b> {link(d["destino_a"])}<br><b>Destino B:</b> {link(d["destino_b"])}</p>'
        if d.get('destino_final_a') or d.get('destino_final_b'):extra+='<p><b>Destinos finais observados:</b> '+link(d.get('destino_final_a'))+' / '+link(d.get('destino_final_b'))+'</p>'
        if d.get('ordem_a') and d.get('ordem_b'):
            ordem1=''.join(f'<li>{esc(item)}</li>' for item in d['ordem_a'])
            ordem2=''.join(f'<li>{esc(item)}</li>' for item in d['ordem_b'])
            extra+=f'<div class="order-pair"><div><b>Ordem A</b><ol>{ordem1}</ol></div><div><b>Ordem B</b><ol>{ordem2}</ol></div></div>'
        if d.get('texto_a'):
            extra+=f'<p><b>Texto A:</b> {esc(d["texto_a"])}<br><b>Texto B:</b> {esc(d["texto_b"])}</p>'
        if d.get('visivel_texto') is False:
            extra+='<p><small>O nome pode vir de ALT/ARIA e não ser localizável por Ctrl + F.</small></p>'
        capt=''
        screens=d.get('evidencias') or {}
        if screens:
            boxes=[]
            for env in dados.get('ambientes',{}):
                relative=screens.get(env,'')
                pane='<p>Captura indisponível.</p>'
                # O nome vem da pasta de evidências gerada para esta execução.
                if (relative.startswith('evidencias_') and relative.endswith(f'_{env}.png')
                    and '..' not in relative and '/' in relative):
                    imagem_local=pasta / relative
                    if imagem_local.is_file() and imagem_local.stat().st_size<3_000_000:
                        uri='data:image/png;base64,'+base64.b64encode(imagem_local.read_bytes()).decode('ascii')
                        pane=f'<img src="{uri}" alt="Captura de {esc(env)} para {esc(d.get("id",""))}">'
                status=esc((d.get('marcacoes') or {}).get(env,'Captura sem confirmação de presença do elemento'))
                boxes.append(f'<div class="capture-panel"><b>{esc(env)}</b>{pane}<small>{status}</small></div>')
            capt='<div class="capture-grid">'+''.join(boxes)+'</div><p><small>Contornos indicam elementos encontrados pelo seletor; ausência de contorno não comprova ausência do elemento.</small></p>'
        elif d.get('evidencia'):
            img=d['evidencia']
            if img.startswith('evidencias_') and img.endswith('.png') and '..' not in img:
                imagem_local=pasta / img
                if imagem_local.is_file() and imagem_local.stat().st_size<3_000_000:
                    uri='data:image/png;base64,'+base64.b64encode(imagem_local.read_bytes()).decode('ascii')
                    capt=f'<figure><img src="{uri}" alt="Captura legada"><figcaption>Captura legada: ambiente não identificado. Refaça a comparação para gerar o par.</figcaption></figure>'
        if d.get('itens_agrupados'):
            extra+='<details><summary>Documentos agrupados</summary>'+''.join('<p>'+esc(x.get('id'))+' · '+esc(x.get('elemento'))+' · '+link(x.get('referencia'))+'</p>' for x in d['itens_agrupados'])+'</details>'
        occurrences=d.get('ocorrencias',[])
        occ=''
        if len(occurrences)>1:
            li=''.join(f'<li>{esc(o.get("caminho",""))} · {link(o.get("url_presente"))} / {link(o.get("url_comparada"))}</li>' for o in occurrences)
            occ=f'<details><summary>{len(occurrences)} páginas afetadas</summary><ol>{li}</ol></details>'
        etiqueta=('<p><b>Revisão manual:</b> Confirmada pelo revisor.</p>' if d.get('revisao_manual')=='confirmada' else '')
        cards.append(f'''<article data-div-id="{escape(str(d.get('id','')),quote=True)}"><h3>{esc(d.get('id',''))} · {esc(d.get('categoria') or d.get('tipo',''))} <small>({esc(d.get('ocorrencias_total',1))} ocorrência(s))</small> <button type="button" class="copy-id">Copiar ID</button></h3>
        <p><b>Caminho:</b> {esc(d.get('caminho',''))}<br><b>Posição visual:</b> {esc(d.get('posicao') or 'Não determinada')}</p>
        <p>{descr}</p><p>Tag: {esc(d.get('tag_tecnica'))} · Confiança: {esc(d.get('grau_confianca'))}</p><p>{esc(d.get('justificativa_evidencia'))}</p><p>Classificação: {esc(d.get('classificacao'))} — {esc(d.get('motivo_relevancia'))}</p>{etiqueta}{extra}<p><b>Página A:</b> {link(d.get('url_presente'))}<br><b>Página B:</b> {link(d.get('url_comparada'))}</p>{capt}{occ}</article>''')
    avisos=''.join(f'''<details><summary>{esc(x['ambiente'])} · {esc(x['tipo'])} ({x['quantidade']})</summary>
      <ul>{''.join('<li>'+esc(u)+'</li>' for u in x['exemplos'])}</ul></details>''' for x in dados.get('avisos_tecnicos',[]))
    external=''.join(f'''<details><summary>{esc(x['status'])} · {esc(x['url'])}</summary>
      <p>Origem: {esc(x['origem'])}</p><ul>{''.join('<li>'+esc(o['opcao'])+': '+esc(o['situacao'])+'</li>' for o in x.get('opcoes',[]))}</ul></details>'''
        for x in dados.get('verificacoes_externas',[]))
    pendencias=''.join(f'<li>{esc(x.get("ambiente"))} · {link(x.get("url"))} — {esc(x.get("motivo"))}</li>' for x in dados.get('pendencias',[])[:100])
    ref_html=''.join(f'<li><b>{esc(x.get("elemento","Imagem"))}</b> — {esc(x.get("motivo","Referências diferentes"))}<p>Local: {esc(x.get("caminho",""))}; {esc(x.get("posicao",""))}</p> {link(x.get("destino_a"))} / {link(x.get("destino_b"))}</li>' for x in dados.get('referencias_pendentes',[]))
    state=dados.get('situacao_analise','parcial')
    variations=dados.get('variacoes_dados',[])
    variance_html=''.join(f'<details><summary>{esc(v.get("categoria"))} — {v.get("quantidade_itens",0)} itens editoriais</summary>'
       + '<p>'+esc(v.get('motivo',''))+'</p><ul>'
       + ''.join('<li>'+esc(z.get('tipo',''))+' · '+esc(z.get('elemento',''))+' ('+esc(z.get('ambiente',''))+')</li>' for z in v.get('exemplos',[]))
       + '</ul></details>' for v in variations)
    diag_links=''
    if dados.get('id'):
        rid=esc(dados['id'])
        if (pasta/f'diagnostico_{dados["id"]}.json').exists():
            diag_links=f'<p><a href="diagnostico_{rid}.json">Diagnóstico JSON</a> · <a href="log_{rid}.txt">Log TXT</a></p>'
    smart_html=esc(json.dumps({'metricas':dados.get('metricas',{}),'otimizacao':dados.get('otimizacao',{}),
        'verificacoes_destinos':dados.get('verificacoes_destinos',[]),'resultados_funcionais':dados.get('resultados_funcionais',[]),'diferencas_esteticas':dados.get('diferencas_esteticas',[]),'documentos_verificados':dados.get('documentos_verificados',[]),'grupos_relacionados':dados.get('grupos_relacionados',[])},ensure_ascii=False,indent=2))
    doc=f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>AmbiDiff · {esc(dados.get('site_nome',''))}</title><style>
    body{{font:14px/1.65 system-ui,Arial;background:#10111c;color:#ededf5;max-width:1100px;margin:auto;padding:30px}}
    [hidden]{{display:none!important}}h1{{margin:4px 0}}article,details{{background:#1c1e2e;border:1px solid #383950;border-radius:11px;padding:18px;margin:12px 0;break-inside:avoid}}
    a{{color:#c0aaff;overflow-wrap:anywhere}}.notice{{background:#30293e;padding:15px;border-radius:10px}}
    .order-pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.order-pair>div{{background:#252438;padding:12px;border-radius:8px}}
    .search-div{{width:100%;padding:12px;border-radius:9px;border:1px solid #665783;background:#242338;color:white;box-sizing:border-box}}
    .copy-id{{background:#4b3365;border:1px solid #9063bf;color:white;border-radius:7px;padding:5px 9px;cursor:pointer}}
    figure{{margin:14px 0}}figure img{{max-width:100%;max-height:500px;border:2px solid #ac88ff;border-radius:8px}}small,figcaption{{color:#a6a8bd}}
    .capture-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:14px 0}}
    .capture-panel{{background:#26243a;border:1px solid #594a77;border-radius:10px;padding:12px;min-width:0}}
    .capture-panel b,.capture-panel small{{display:block;margin-bottom:9px}}
    .capture-panel img{{width:100%;max-height:450px;object-fit:contain;object-position:top left;border-radius:7px;border:1px solid #6f5c8b}}
    @media(max-width:750px){{.capture-grid{{grid-template-columns:1fr}}}}
    @media print{{body{{background:white;color:#171717}}article,details{{background:white;border-color:#bbb}}a{{color:#333}}}}
    </style></head><body><small>AMBIDIFF v1.5 · VERIFICAÇÃO LOCAL</small>
    <h1>{esc(dados.get('site_nome','Comparação de ambientes'))}</h1>
    <p>Início: {esc(dados.get('iniciado_em','não disponível'))} · Fim do processamento: {esc(dados.get('finalizado_em','não disponível'))} · Duração: {esc(dados.get('duracao_segundos','não disponível'))} s</p>
    <p>Gerado em {esc(dados.get('gerado_em',''))} · Estado: <b>{esc(state)}</b></p>
    <p>{len(dados['divergencias'])} grupo(s) de divergência · {esc(dados.get('ocorrencias_brutas',len(dados['divergencias'])))} ocorrência(s) antes do agrupamento</p>
    <p>{('DIVs excluídas pelo revisor: '+str(dados['divergencias_ocultadas'])+'.') if dados.get('divergencias_ocultadas') else ''}</p>
    <p>{' · '.join(esc(k)+': '+str(v)+' páginas lidas' for k,v in dados.get('paginas',{}).items())}</p>
    <div class="notice">URLs distintas para a mesma opção são registradas como divergências e esses destinos não são explorados. Diferenças não determinam qual ambiente está correto. {esc('A varredura não foi concluída em todas as páginas.' if state!='concluido' else '')}</div>
    <label for="search-div"><b>Pesquisar divergência por ID (DIV-0033, 0033, 33) ou texto:</b></label>
    <input type="search" id="search-div" class="search-div" placeholder="Ex.: DIV-0033 ou Radar">
    <h2>Equivalência, documentos e cobertura</h2><p>Equivalência estática não comprova funcionamento. Metadados não comprovam arquivos idênticos. Inspeções profundas omitidas limitam a cobertura.</p><details><summary>Resultados e métricas do modo {esc(dados.get("modo_varredura","atual"))}</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{smart_html}</pre></details>
    <h2>Variações de dados (base defasada: {esc(dados.get('ambiente_desatualizado') or 'não informada')})</h2>{variance_html or '<p>Sem variações editoriais classificadas.</p>'}
    <p>Relatório principal omite baixa relevância e editoriais da lista prioritária. JSON contém todos os registros.</p>
    <details><summary>Diagnóstico completo — diferenças de baixa relevância</summary><pre>{esc(json.dumps({'baixa_relevancia':[r for r in completos if r['classificacao']=='baixa'],'editoriais':dados.get('editoriais_preservados',[])},ensure_ascii=False,indent=2))}</pre></details>
    <h2>Divergências agrupadas por categoria</h2>{''.join(cards) or '<p>Nenhuma divergência encontrada nas páginas verificadas.</p>'}
    <h2>Auditoria limitada de páginas externas iguais</h2>{external or '<p>Nenhuma.</p>'}
    <h2>Referências visuais pendentes de revisão</h2><ul>{ref_html or '<li>Nenhuma.</li>'}</ul>
    <h2>Diagnósticos técnicos</h2>{diag_links}
    <h2>Avisos técnicos</h2>{avisos or '<p>Nenhum aviso.</p>'}
    <h2>Páginas que não puderam ser comparadas</h2><ul>{pendencias or '<li>Nenhuma.</li>'}</ul>
    <script>
    (()=>{{
      const input=document.getElementById('search-div');
      const records=[...document.querySelectorAll('article[data-div-id]')];
      input.addEventListener('input',()=>{{
        const q=input.value.trim().toLowerCase(),m=/^(?:div[\\s-]*)?(\\d{{1,5}})$/i.exec(q);
        const id=m?'DIV-'+m[1].padStart(4,'0'):null;
        for(const c of records){{c.hidden=id?c.dataset.divId!==id:!!q&&!c.textContent.toLowerCase().includes(q);}}
      }});
      document.querySelectorAll('.copy-id').forEach(button=>button.addEventListener('click',async()=>{{
        const id=button.closest('article').dataset.divId;
        try{{
          if(navigator.clipboard?.writeText){{await navigator.clipboard.writeText(id);}}
          else{{const tmp=document.createElement('textarea');tmp.value=id;document.body.append(tmp);tmp.select();
            const copied=document.execCommand('copy');tmp.remove();if(!copied)throw Error('Sem permissão');}}
          button.textContent='Copiado!';
        }}catch(e){{button.textContent='Selecione o ID para copiar';}}
      }}));
    }})();
    </script></body></html>'''
    paths['html'].write_text(doc,encoding='utf-8')
    dados['divergencias']=completos
    dados['exportacao']={'gerado_em':datetime.now().astimezone().isoformat(),'duracao_antes_json_segundos':round(time.perf_counter()-inicio_exportacao,6),'nota':'Exportação CSV/HTML e preparação do JSON. Exclui a escrita final deste JSON, evitando regravar evidências.'}
    from .storage import atomic_json
    atomic_json(paths['json'],dados)
    return {ext:str(path) for ext,path in paths.items()}
