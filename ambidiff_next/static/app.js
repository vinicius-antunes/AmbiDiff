'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const token = document.querySelector('meta[name="next-token"]').content;
  const state = {id: null, report: null, cursor: 0, revision: 0, busy: false, mutation: Promise.resolve()};
  const running = new Set(['running', 'pending', 'queued', 'stop_requested']);
  const statuses = {running:'Executando', pending:'Aguardando', queued:'Aguardando', stop_requested:'Interrupção solicitada — aguardando operação atual', interrupted:'Interrompida · parcial preservado', failed:'Falha · consulte o diagnóstico', completed:'Trabalho planejado concluído', partial:'Parcial'};
  const reviews = {pending:'Pendente',confirmed:'Confirmar DIV',false_positive:'Falso positivo',editorial:'Diferença editorial',corrected:'Corrigida',hidden:'Ocultar sem apagar'};
  const metricNames = {pages_discovered:'Páginas descobertas',pages_visited:'Páginas visitadas',pages_paired:'Páginas com contraparte',pages_unpaired:'Sem contraparte comprovada',components_mapped:'Componentes mapeados',elements_matched:'Elementos equivalentes',components_compared:'Componentes comparados',functional_executed:'Testes funcionais executados',functional_inconclusive:'Funções inconclusivas',redirects_checked:'Redirecionamentos verificados',links_checked:'Links avaliados',visual_compared:'Comparações visuais',technical_failures:'Falhas técnicas',raw_occurrences:'Ocorrências brutas',consolidated_divs:'DIVs consolidadas',tasks_done:'Tarefas processadas',page_pairs_compared:'Pares de páginas comparados',pages_without_counterpart:'Sem contraparte comprovada',equivalent_elements:'Elementos equivalentes',elements_checked:'Elementos verificados',links_evaluated:'Links avaliados',tasks_pending:'Tarefas pendentes'};
  const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  function element(tag, text, className) { const node=document.createElement(tag); if(text!==undefined)node.textContent=String(text); if(className)node.className=className; return node; }
  function message(text,error=false) { $('message').textContent=text; $('message').className='notice'+(error?' error':''); $('message').hidden=false; }
  async function api(path,options={}) {
    const response=await fetch(path,{...options,headers:{'Content-Type':'application/json','X-Next-Token':token,...options.headers}});
    const data=await response.json(); if(!response.ok)throw new Error(data.error || 'Não foi possível concluir a operação.'); return data;
  }
  function reviewFor(row) {
    const source=state.report.reviews || {};
    const value=Array.isArray(source) ? source.find(x => x.id===row.id || x.finding_id===row.id) : source[row.id];
    return {...(typeof value==='string'?{status:value}:value || {}), selected:(value && value.selected)!==undefined?value.selected:!!row.selected, status:(value && value.status) || row.review_status || 'pending'};
  }
  function idQuery(query) {
    if(!query.trim() || !/^(?:\s*(?:DIV[\s-]*)?\d+\s*(?:-\s*(?:DIV[\s-]*)?\d+\s*)?)(?:[,;\s]+(?:DIV[\s-]*)?\d+\s*(?:-\s*(?:DIV[\s-]*)?\d+\s*)?)*$/i.test(query))return null;
    const groups=query.trim().split(/[,;]+/).flatMap(part => part.trim().split(/\s+(?=(?:DIV[\s-]*)?\d)/i));
    const result=[];
    for(const group of groups) { const match=/^(?:DIV[\s-]*)?(\d+)\s*(?:-\s*(?:DIV[\s-]*)?(\d+))?$/i.exec(group.trim()); if(!match)return null; const a=Number(match[1]),b=Number(match[2] || match[1]); result.push([Math.min(a,b),Math.max(a,b)]); }
    return result;
  }
  function filtered() {
    if(!state.report)return [];
    const query=$('search').value.trim(), ranges=idQuery(query);
    return (state.report.findings || []).filter(row => {
      const rev=reviewFor(row),filter=$('filter-review').value;
      if(rev.status==='hidden' && filter!=='hidden')return false;
      if(filter && rev.status!==filter)return false;
      if($('filter-nature').value && row.nature!==$('filter-nature').value)return false;
      if($('filter-impact').value && row.impact!==$('filter-impact').value)return false;
      if($('filter-confidence').value && row.confidence!==$('filter-confidence').value)return false;
      const env=$('filter-environment').value;
      if(env && row.environment && row.environment!==env)return false;
      if(env==='a' && !row.page_a || env==='b' && !row.page_b)return false;
      if(ranges) { const number=Number(String(row.id).replace(/\D/g,'')); return ranges.some(([a,b])=>number>=a && number<=b); }
      return !query || normalize(JSON.stringify(row)).includes(normalize(query));
    });
  }
  function persistFilters() {
    if(!state.id)return;
    const ids=['search','filter-nature','filter-impact','filter-confidence','filter-environment','filter-review'];
    try { localStorage.setItem('ambidiff-next-filters:'+state.id,JSON.stringify(Object.fromEntries(ids.map(id=>[id,$(id).value])))); } catch (_) { /* Local storage is optional; review is stored on disk. */ }
  }
  function restoreFilters() {
    const ids=['search','filter-nature','filter-impact','filter-confidence','filter-environment','filter-review'];
    let saved={}; try{saved=JSON.parse(localStorage.getItem('ambidiff-next-filters:'+state.id) || '{}');}catch(_){}
    ids.forEach(id=>{$(id).value=saved[id] || '';});
  }
  function link(url,label) { if(!/^https?:\/\//i.test(url || ''))return element('span',label || 'Não disponível'); const a=element('a',label || url);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a; }
  function evidenceNames(value) { if(typeof value==='string')return /\.png$/i.test(value)?[value]:[];if(Array.isArray(value))return value.flatMap(evidenceNames);if(value && typeof value==='object')return Object.values(value).flatMap(evidenceNames);return []; }
  function renderFindings() {
    $('findings').replaceChildren();const rows=filtered();$('empty').hidden=rows.length!==0;
    $('result-count').textContent=`${rows.length} de ${(state.report.findings || []).length} DIVs`;
    $('selected-count').textContent=`${(state.report.findings || []).filter(row=>reviewFor(row).selected && reviewFor(row).status!=='hidden').length} selecionadas para exportação`;
    for(const row of rows) {
      const rev=reviewFor(row),card=element('article',undefined,'finding'),top=element('div',undefined,'finding-top');
      const label=element('label'),check=element('input');check.type='checkbox';check.checked=!!rev.selected;check.setAttribute('aria-label',`Selecionar ${row.id} para exportação`);
      check.addEventListener('change',()=>mutate([row.id],'select',check.checked));label.append(check,element('span',`${row.id} · ${row.element || row.code}`));top.append(label);card.append(top);
      card.append(element('p',`${row.nature || ''} · impacto ${row.impact || 'não informado'} · confiança ${row.confidence || 'inconclusivo'} · ${row.count || 1} ocorrência(s)`,'meta'));
      card.append(element('p',row.fact || row.code,'fact'),element('p',`Local: ${row.section || 'Não informado'}${row.path?' · '+(Array.isArray(row.path)?row.path.join(' → '):row.path):''}`));
      const columns=element('div',undefined,'columns');
      [['Ambiente A',row.page_a,row.observed_a],['Ambiente B',row.page_b,row.observed_b]].forEach(([title,url,observed])=>{const col=element('div');col.append(element('strong',title),element('br'),link(url),element('p',typeof observed==='object'?JSON.stringify(observed):observed || 'Não observado'));columns.append(col);});card.append(columns);
      card.append(element('p',`Possível causa: ${row.possible_cause || 'Não determinada'}`),element('p',`Verificação recomendada: ${row.recommendation || 'Revisão humana'}`));
      const names=[...new Set(evidenceNames(row.evidence || {}))];
      if(names.length) { const box=element('div',undefined,'evidence');for(const name of names){const figure=element('figure'),img=element('img');img.src=`/api/runs/${encodeURIComponent(state.id)}/evidence/${name.split('/').map(encodeURIComponent).join('/')}`;img.alt=`Evidência ${name}`;img.loading='lazy';img.addEventListener('error',()=>{img.hidden=true;});figure.append(img,element('figcaption',name));box.append(figure);}card.append(box); }
      else card.append(element('p','Sem imagens disponíveis para esta observação.','muted'));
      const reviewLabel=element('label','Revisão manual','review'),select=element('select');
      for(const [value,text] of Object.entries(reviews)){const option=element('option',text);option.value=value;option.selected=value===rev.status;select.append(option);}select.addEventListener('change',()=>mutate([row.id],select.value));reviewLabel.append(select);card.append(reviewLabel);$('findings').append(card);
    }
  }
  function renderReport(report) {
    state.report=report;const run=report.run || {},metrics={...(run.metrics || {}),raw_occurrences:(report.occurrences || []).length,consolidated_divs:(report.findings || []).length};
    $('execution').hidden=false;$('results').hidden=false;$('run-title').textContent=run.config?.name || 'Comparação de ambientes';$('run-state').textContent=statuses[run.status] || run.status || 'Aguardando';
    $('current').textContent=typeof run.current==='object'?JSON.stringify(run.current):run.current || '';
    const stopRequested=run.status==='stop_requested';$('stop').disabled=stopRequested || !report.worker_active;$('stop').textContent=stopRequested?'Interrupção solicitada':'Interromper';$('start').disabled=!!report.worker_active;
    $('resume').hidden=!report.can_resume;
    const elapsed=metrics.elapsed_seconds || metrics.duration_seconds || Math.max(0,(Date.now()-Date.parse(run.created_at || new Date()))/1000);$('elapsed').textContent=`Tempo registrado: ${Math.round(elapsed)} s`;
    $('metrics').replaceChildren();for(const [key,name] of Object.entries(metricNames)){if(metrics[key]===undefined)continue;const metric=element('div',undefined,'metric');metric.append(element('b',metrics[key]),element('span',name));$('metrics').append(metric);}
    if(metrics.coverage){const detail=element('div',undefined,'metric');detail.append(element('span','Cobertura por categoria'),element('pre',JSON.stringify(metrics.coverage,null,2)));$('metrics').append(detail);}
    const selectedNature=$('filter-nature').value,allNature=element('option','Todas');allNature.value='';$('filter-nature').replaceChildren(allNature);
    for(const nature of [...new Set((report.findings || []).map(row=>row.nature))].filter(Boolean).sort()){const option=element('option',nature);option.value=nature;$('filter-nature').append(option);}$('filter-nature').value=selectedNature;
    renderFindings();
  }
  async function loadReport() { if(!state.id)return;const revision=state.revision,id=state.id;const report=await api(`/api/runs/${encodeURIComponent(id)}`);if(revision===state.revision && id===state.id)renderReport(report); }
  async function openRun(id) {
    state.id=id;state.report=null;state.cursor=0;state.revision++;$('logs').textContent='';await loadReport();restoreFilters();renderFindings();
    try{localStorage.setItem('ambidiff-next-last-run',id);}catch(_){}
  }
  function mutate(ids,action,selected) {
    state.revision++;const runId=state.id;
    state.mutation=state.mutation.then(async()=>{await api(`/api/runs/${encodeURIComponent(runId)}/review`,{method:'POST',body:JSON.stringify({ids,action,selected})});if(state.id===runId)await loadReport();}).catch(error=>message(error.message,true));
    return state.mutation;
  }
  async function history() {
    const runs=await api('/api/runs');$('history').replaceChildren();
    if(!runs.length)$('history').append(element('p','Nenhuma comparação do Next registrada.','muted'));
    for(const run of runs){const box=element('div',undefined,'history-row'),text=element('div');text.append(element('strong',run.config?.name || run.id),element('div',`${statuses[run.status] || run.status} · ${run.created_at || ''}`,'muted'));const button=element('button','Abrir','secondary');button.addEventListener('click',()=>openRun(run.id).catch(error=>message(error.message,true)));box.append(text,button);$('history').append(box);}
  }
  $('start-form').addEventListener('submit',async event=>{event.preventDefault();$('start').disabled=true;try{const form=new FormData(event.target),labels=[form.get('label_a'),form.get('label_b')],outdated=form.get('outdated');const result=await api('/api/runs',{method:'POST',body:JSON.stringify({name:form.get('name'),roots:[form.get('url_a'),form.get('url_b')],labels,outdated:outdated==='a'?labels[0]:outdated==='b'?labels[1]:'',max_pages:Number(form.get('max_pages')),viewport:{width:Number(form.get('width')),height:Number(form.get('height'))}})});await openRun(result.id);await history();}catch(error){message(error.message,true);$('start').disabled=false;}});
  $('stop').addEventListener('click',async()=>{$('stop').disabled=true;$('stop').textContent='Interrupção solicitada';$('current').textContent='Interrupção solicitada — aguardando operação atual';try{const response=await api(`/api/runs/${encodeURIComponent(state.id)}/stop`,{method:'POST',body:'{}'});message(response.message);await loadReport();}catch(error){message(error.message,true);$('stop').disabled=false;}});
  $('resume').addEventListener('click',async()=>{$('resume').disabled=true;try{await api(`/api/runs/${encodeURIComponent(state.id)}/resume`,{method:'POST',body:'{}'});await loadReport();}catch(error){message(error.message,true);}finally{$('resume').disabled=false;}});
  ['search','filter-nature','filter-impact','filter-confidence','filter-environment','filter-review'].forEach(id=>$(id).addEventListener('input',()=>{persistFilters();renderFindings();}));
  $('select-filtered').addEventListener('click',()=>mutate(filtered().filter(row=>reviewFor(row).status!=='hidden').map(row=>row.id),'select',true));
  $('clear-filtered').addEventListener('click',()=>mutate(filtered().map(row=>row.id),'select',false));
  $('reload-history').addEventListener('click',()=>history().catch(error=>message(error.message,true)));
  $('export-scope').addEventListener('change',()=>{document.querySelector(`input[name="format"][value="${$('export-scope').value==='selected'?'csv':'html'}"]`).checked=true;});
  $('download').addEventListener('click',async()=>{
    const button=$('download'),format=document.querySelector('input[name="format"]:checked').value,scope=$('export-scope').value;
    if(scope==='selected' && !(state.report.findings || []).some(row=>reviewFor(row).selected && reviewFor(row).status!=='hidden')){message('Selecione ao menos uma DIV visível para exportar.',true);return;}
    button.disabled=true;
    try {
      let handle=null;
      if(window.showSaveFilePicker) {
        try { handle=await window.showSaveFilePicker({suggestedName:`AmbiDiff_Next_${scope==='selected'?'Selecionadas':'Comparacao'}.${format}`,id:'ambidiff-next-export'}); }
        catch(error) { if(error.name==='AbortError')throw error;message('Seletor de arquivo indisponível. A exportação usará o download padrão do navegador.'); }
      }
      const response=await fetch(`/api/runs/${encodeURIComponent(state.id)}/export?format=${format}&scope=${scope}`);
      if(!response.ok){const error=await response.json();throw new Error(error.error || 'Falha ao gerar exportação.');}
      const blob=await response.blob();
      if(handle){const stream=await handle.createWritable();await stream.write(blob);await stream.close();}
      else { const url=URL.createObjectURL(blob),a=element('a');a.href=url;const match=/filename\*=UTF-8''([^;]+)|filename="?([^";]+)/i.exec(response.headers.get('Content-Disposition') || '');a.download=match?decodeURIComponent(match[1] || match[2]):`AmbiDiff_Next.${format}`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000); }
      message('Exportação entregue ao navegador. Confira o arquivo no local escolhido.');
    }catch(error){if(error.name!=='AbortError')message(error.message,true);}finally{button.disabled=false;}
  });
  async function tick() {
    if(state.busy)return;state.busy=true;
    try{if(state.id){const id=state.id;await loadReport();const result=await api(`/api/runs/${encodeURIComponent(id)}/logs?after=${state.cursor}`);if(id===state.id){const rows=result.entries || [];if(rows.length){$('logs').textContent+=rows.map(row=>`${row.time || ''} ${row.message}`).join('\n')+'\n';const lines=$('logs').textContent.split('\n');if(lines.length>1000)$('logs').textContent=lines.slice(-1000).join('\n');$('logs').scrollTop=$('logs').scrollHeight;}state.cursor=result.cursor || state.cursor;}}}catch(error){message(error.message,true);}finally{state.busy=false;}
  }
  history().then(async()=>{let last=null;try{last=localStorage.getItem('ambidiff-next-last-run');}catch(_){}if(last)await openRun(last);}).catch(error=>message(error.message,true));
  setInterval(tick,1800);
})();
