'use strict';
let currentReport=null,currentId=null,timer=null,renderedCount=0,lastLogCount=0,filtered=[];
let allHistory=[],selectedCategory='todas',selectionMode=false,selectedRuns=new Set();
const $=id=>document.getElementById(id);
function element(tag,text,cls){const x=document.createElement(tag);if(text!==undefined&&text!==null)x.textContent=text;if(cls)x.className=cls;return x;}
function nav(section){
  document.querySelectorAll('.screen').forEach(x=>x.classList.toggle('active',x.id==='section-'+section));
  document.querySelectorAll('.nav-btn').forEach(x=>x.classList.toggle('active',x.dataset.section===section));
  $('breadcrumb').textContent=({dashboard:'Visão geral / Dashboard',comparar:'Verificações / Comparar',resultados:'Relatórios / Divergências',historico:'Sistema / Histórico',ajuda:'Sistema / Guia'})[section];
  $('sidebar').classList.remove('show');
  if(section==='historico')loadHistory();
}
document.querySelectorAll('.nav-btn').forEach(x=>x.addEventListener('click',()=>nav(x.dataset.section)));
$('mobile-menu').addEventListener('click',()=>$('sidebar').classList.toggle('show'));
$('go-compare').addEventListener('click',()=>nav('comparar'));
$('go-history').addEventListener('click',()=>nav('historico'));
async function api(url,options){const r=await fetch(url,options);let d=await r.json();if(!r.ok)throw Error(d.erro||'Falha na comunicação.');return d;}
function setRunning(b){$('run-button').disabled=b;$('stop-button').disabled=!b;$('running-label').textContent=b?'Executando...':'Aguardando';}
function printLogs(logs){
  if(logs.length<lastLogCount){$('terminal').replaceChildren();lastLogCount=0;}
  if(!lastLogCount)$('terminal').replaceChildren();
  for(const msg of logs.slice(lastLogCount)){
    const e=element('div','› '+msg);
    if(msg.startsWith('ERRO'))e.style.color='#fd8895';
    if(msg.includes('Finalizado'))e.style.color='#75e6bc';
    $('terminal').append(e);
  }
  lastLogCount=logs.length;$('terminal').scrollTop=$('terminal').scrollHeight;
}
function preferenceKey(){
  try{return 'ambidiff:base:'+new URL($('url-a').value.trim()).host.toLowerCase();}
  catch(e){return null;}
}
function restoreBasePreference(){
  const key=preferenceKey();
  if(!key)return;
  try{$('ambiente-desatualizado').value=localStorage.getItem(key)||'';}
  catch(e){}
}
$('url-a').addEventListener('change',restoreBasePreference);
$('ambiente-desatualizado').addEventListener('change',()=>{
  const key=preferenceKey();if(!key)return;
  try{localStorage.setItem(key,$('ambiente-desatualizado').value);}catch(e){}
});
restoreBasePreference();
async function openReport(id){
  try{currentReport=await api('/api/relatorio/'+encodeURIComponent(id));currentId=id;
    displayReport();nav('resultados');}
  catch(e){alert('Não foi possível abrir o relatório: '+e.message);}
}
async function poll(){
  try{
    const s=await api('/api/status');$('progress-fill').style.width=s.progresso+'%';printLogs(s.logs||[]);
    const busy=s.status==='executando';setRunning(busy);
    const diag=$('failure-diagnostics');diag.hidden=!(s.status==='erro' && s.ultimo_id);
    if(!diag.hidden){$('failure-json').href='/download/'+encodeURIComponent(s.ultimo_id)+'/diagnostico-json';
                     $('failure-txt').href='/download/'+encodeURIComponent(s.ultimo_id)+'/diagnostico-txt';}
    $('running-label').textContent=({executando:'Executando',concluido:'Concluído',erro:'Erro',interrompido:'Interrompido',pronto:'Aguardando'})[s.status]||s.status;
    $('stat-status').textContent=$('running-label').textContent;
    if(!busy){clearInterval(timer);timer=null;
      if(s.status==='concluido'&&s.ultimo_id){await loadHistory();await openReport(s.ultimo_id);}
      if(s.erro)$('form-error').textContent=s.erro;
    }
  }catch(e){clearInterval(timer);timer=null;setRunning(false);$('form-error').textContent=e.message;}
}
$('compare-form').addEventListener('submit',async e=>{
  e.preventDefault();$('form-error').textContent='';$('failure-diagnostics').hidden=true;lastLogCount=0;$('terminal').replaceChildren();$('progress-fill').style.width='0%';
  const payload={varredura_inteligente:$('varredura-inteligente').checked,url_a:$('url-a').value.trim(),url_b:$('url-b').value.trim(),nome_a:$('nome-a').value,nome_b:$('nome-b').value,site_nome:$('site-nome').value.trim(),auditar_externos:$('auditar-externos').checked,verificar_cliques:$('verificar-cliques').checked,
    ambiente_desatualizado:$('ambiente-desatualizado').value==='A'?$('nome-a').value: $('ambiente-desatualizado').value==='B'?$('nome-b').value:''};
  try{await api('/api/comparar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    setRunning(true);clearInterval(timer);await poll();if($('run-button').disabled)timer=setInterval(poll,1500);
  }catch(e){$('form-error').textContent=e.message;setRunning(false);}
});
$('stop-button').addEventListener('click',async()=>{try{await api('/api/parar',{method:'POST'});$('running-label').textContent='Interrompendo...';}catch(e){$('form-error').textContent=e.message;}});
function safeLink(url){
  if(!/^https?:\/\//i.test(url||''))return element('span','Não disponível','dim-copy');
  const a=element('a',url);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;
}
function row(label,value,link=false){const dt=element('dt',label),dd=element('dd');dd.append(link?safeLink(value):element('span',value||'—'));return[dt,dd];}
function filters(){
  const d=currentReport||{divergencias:[]};
  const sides=[...new Set(d.divergencias.map(x=>x.presente_em))].sort(),types=[...new Set(d.divergencias.map(x=>x.tipo))].sort();
  $('filter-side').replaceChildren(new Option('Todos os ambientes','todos'));
  $('filter-type').replaceChildren(new Option('Todos os tipos','todos'));
  sides.forEach(s=>$('filter-side').add(new Option('Encontrado em '+s,s)));
  types.forEach(s=>$('filter-type').add(new Option(s,s)));
  $('search-results').value='';selectedCategory='todas';categories();
}
function categories(){
  const box=$('category-toolbar');box.replaceChildren();
  const groups=new Map();for(const d of (currentReport?.divergencias||[])){
    const c=d.categoria||d.tipo||'Outros';groups.set(c,(groups.get(c)||0)+1);
  }
  function tab(name,count){
    const btn=element('button',null,'category-tab');btn.type='button';
    btn.classList.toggle('selected',selectedCategory===name);
    btn.append(element('span',name),element('strong',String(count)));
    btn.addEventListener('click',()=>{selectedCategory=name;categories();refilter();});box.append(btn);
  }
  tab('todas',(currentReport?.divergencias||[]).length);
  for(const [cat,count] of groups)tab(cat,count);
}
function occurrences(card,d){
  const occ=d.ocorrencias||[];
  if(occ.length<=1)return;
  const details=element('details',null,'warning-group');
  details.append(element('summary','Ver as '+occ.length+' páginas afetadas'));
  const ul=element('ul');for(const item of occ){
    const li=element('li');li.append(element('strong',item.caminho||'Página'),element('div','Ambiente A: '),safeLink(item.url_presente),element('div','Ambiente B: '),safeLink(item.url_comparada));
    ul.append(li);
  }
  details.append(ul);card.append(details);
}
function normalizedDivSearch(query){
  const m=/^(?:div[\s-]*)?(\d{1,5})$/i.exec(query.trim());
  return m?'DIV-'+m[1].padStart(4,'0'):null;
}
async function copyId(id,button){
  try{
    if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(id);}
    else{
      const tmp=document.createElement('textarea');tmp.value=id;tmp.style.position='fixed';tmp.style.left='-9999px';
      document.body.append(tmp);tmp.select();const ok=document.execCommand('copy');tmp.remove();if(!ok)throw Error('Sem acesso à área de transferência');
    }
    button.textContent='✓ Copiado';setTimeout(()=>button.textContent='Copiar ID',1600);
  }catch(e){button.textContent='Não foi possível copiar';setTimeout(()=>button.textContent='Copiar ID',2400);}
}
function renderNext(){
  const end=Math.min(filtered.length,renderedCount+40);
  for(let i=renderedCount;i<end;i++){
    const d=filtered[i],card=element('article',null,'result-card');
    const head=element('div',null,'result-heading');
    head.append(element('strong',d.id),element('span',d.categoria||d.tipo,'result-chip section'),element('span',d.situacao,'result-chip'));
    if(d.revisao_manual==='confirmada')head.append(element('span','✓ Confirmada manualmente','result-chip'));
    const review=element('button',d.revisao_manual==='confirmada'?'✓ Desmarcar confirmação':'✓ Confirmar DIV','outline-button');
    review.type='button';review.title='Marcar esta ocorrência como validada por inspeção manual';
    review.addEventListener('click',()=>reviewDiv(d.id,d.revisao_manual==='confirmada'?'pendente':'confirmada'));
    head.append(review);
    const classification=element('select');classification.setAttribute('aria-label','Reclassificar '+d.id);
    for(const [value,label] of [['automatica','Automática'],['relevante','Relevante'],['baixa','Baixa relevância'],['editorial','Editorial'],['inconclusivo','Inconclusivo']]){
      const option=element('option',label);option.value=value;classification.append(option);
    }
    classification.value=d.classificacao_manual||'automatica';
    classification.addEventListener('change',async()=>{
      try{for(const id of (d.ids_agrupados||[d.id])){await api('/api/relatorio/'+encodeURIComponent(currentId)+'/divergencias/'+encodeURIComponent(id)+'/relevancia',{method:'PUT',body:JSON.stringify({classe:classification.value})});}await openReport(currentId);}
      catch(e){alert('Falha ao reclassificar: '+e.message);}
    });
    head.append(element('span',d.classificacao||'relevante','result-chip'),classification);
    if(d.ids_agrupados?.length>1)head.append(element('span','IDs: '+d.ids_agrupados.join(', '),'result-chip'));
    card.append(element('p',d.motivo_relevancia||''));
    card.title=d.motivo_relevancia||'';
    const copy=element('button','Copiar ID','copy-id-button');copy.type='button';copy.title='Copiar '+d.id;copy.addEventListener('click',()=>copyId(d.id,copy));head.append(copy);
    const trash=element('button','🗑','trash-button');trash.type='button';trash.title='Excluir '+d.id+' deste relatório';
    trash.setAttribute('aria-label','Excluir '+d.id);
    trash.addEventListener('click',()=>deleteDiv(d.id));head.append(trash);
    card.id='div-'+d.id.toLowerCase();
    if(d.ocorrencias_total>1)head.append(element('span',d.ocorrencias_total+' ocorrências agrupadas','result-chip'));
    card.append(head);
    const caminho=d.caminho||d.local||'Local não informado';
    card.append(element('div','COMO LOCALIZAR','detail-heading'),element('div',caminho,'breadcrumb-detail'));
    card.append(element('div','POSIÇÃO VISUAL','detail-heading'),element('div',d.posicao||'Não determinada','breadcrumb-detail'));
    card.append(element('div','DESCRIÇÃO','detail-heading'),element('p',d.descricao));
    if(d.ordem_a && d.ordem_b){
      const compare=element('div',null,'order-comparison');
      const a=element('div',null,'order-column'),b=element('div',null,'order-column');
      a.append(element('strong','Ordem em '+d.presente_em));b.append(element('strong','Ordem em '+d.nao_identificado_em));
      d.ordem_a.forEach((v,i)=>a.append(element('div',(i+1)+'. '+v)));
      d.ordem_b.forEach((v,i)=>b.append(element('div',(i+1)+'. '+v)));
      compare.append(a,b);card.append(compare);
    }
    const meta=element('dl',null,'result-metadata');
    for(const [lab,val,link] of [['Página em '+d.presente_em,d.url_presente,true],['Página em '+d.nao_identificado_em,d.url_comparada,true],
      ...(d.destino_a?[['Destino em '+d.presente_em,d.destino_a,true],['Destino em '+d.nao_identificado_em,d.destino_b,true]]:[]),
      ...(d.texto_a?[['Texto no primeiro ambiente',d.texto_a,false],['Texto no segundo ambiente',d.texto_b,false]]:[]),
      ['Elemento',d.elemento,false]])meta.append(...row(lab,val,link));
    card.append(meta);
    if(d.visivel_texto===false)card.append(element('p','Observação: o nome do elemento pode vir do atributo ALT/ARIA e não aparecer na busca Ctrl + F da página.','subtle-warning'));
    if(currentId && d.evidencias && Object.keys(d.evidencias).length){
      const capture=element('div',null,'evidence-box');
      capture.append(element('div','COMPARAÇÃO VISUAL — AMBIENTE A × AMBIENTE B','detail-heading'));
      const grid=element('div',null,'evidence-pair');
      const nomes=Object.keys(currentReport.ambientes||{});
      for(const nome of nomes){
        const pane=element('div',null,'evidence-pane');
        const title=element('strong',nome,'evidence-env');pane.append(title);
        const path=d.evidencias[nome];
        if(path){
          const a=element('a');a.href='/evidencia/'+encodeURIComponent(currentId)+'/'+encodeURIComponent(path.split('/').pop());
          a.target='_blank';a.rel='noopener noreferrer';
          const img=element('img');img.src=a.href;img.loading='lazy';img.alt='Captura do ambiente '+nome+' para '+d.id;
          a.append(img);pane.append(a);
        }else pane.append(element('p','Captura indisponível neste ambiente.','dim-copy'));
        pane.append(element('small',(d.marcacoes||{})[nome]||'Não foi possível verificar o elemento nesta captura.'));
        grid.append(pane);
      }
      capture.append(grid,element('p','O contorno destaca um elemento localizado pelo seletor. A ausência de contorno não confirma que o conteúdo esteja ausente.','subtle-warning'));
      card.append(capture);
    }else if(d.evidencia&&currentId){
      const capture=element('div',null,'evidence-box');
      capture.append(element('div','CAPTURA LEGADA — AMBIENTE NÃO IDENTIFICADO','detail-heading'));
      const a=element('a');a.href='/evidencia/'+encodeURIComponent(currentId)+'/'+encodeURIComponent(d.id+'.png');a.target='_blank';a.rel='noopener noreferrer';
      const img=element('img');img.src=a.href;img.loading='lazy';img.alt='Captura legada de '+d.elemento;
      a.append(img);capture.append(a,element('p','Esta execução foi feita na versão antiga; refaça a comparação para gerar as duas capturas.','dim-copy'));card.append(capture);
    }

    if(!d.evidencias && !d.evidencia)card.append(element('p','Capturas não disponíveis para esta DIV (falha ou limite preventivo de evidências).','dim-copy'));
    occurrences(card,d);
    $('result-list').append(card);
  }
  renderedCount=end;$('load-more').hidden=renderedCount>=filtered.length;
}
function refilter(){
  if(!currentReport)return;
  const q=$('search-results').value.trim().toLocaleLowerCase('pt-BR'),side=$('filter-side').value,type=$('filter-type').value;
  const searchedId=normalizedDivSearch(q);
  filtered=currentReport.divergencias.filter(d=>
    ($('show-all-differences').checked||!['baixa','editorial'].includes(d.classificacao))&&
    (searchedId?d.id===searchedId:
      (selectedCategory==='todas'||d.categoria===selectedCategory)&&
      (side==='todos'||d.presente_em===side)&&(type==='todos'||d.tipo===type)&&
      (!q||[d.id,d.elemento,d.pagina,d.descricao,d.local,d.caminho,d.posicao,d.destino_a,d.destino_b,d.url_presente,d.url_comparada].some(v=>(v||'').toLocaleLowerCase('pt-BR').includes(q)))));
  $('visible-count').textContent=filtered.length+' divergência(s) agrupada(s)';$('result-list').replaceChildren();renderedCount=0;
  if(filtered.length)renderNext();else $('result-list').append(element('div','Nenhuma divergência nesta categoria ou filtro.','empty-state'));
}
$('show-all-differences').addEventListener('change',refilter);
$('search-results').addEventListener('input',refilter);
$('filter-side').addEventListener('change',refilter);$('filter-type').addEventListener('change',refilter);
$('load-more').addEventListener('click',renderNext);
document.querySelectorAll('[data-export]').forEach(b=>b.addEventListener('click',()=>{if(currentId)window.location.href='/download/'+currentId+'/'+b.dataset.export+($('export-scope').value==='completo'?'?completo=1':'');}));
async function reviewDiv(divId,situacao){
  if(!currentId)return;
  try{
    await api('/api/relatorio/'+encodeURIComponent(currentId)+'/divergencias/'+encodeURIComponent(divId)+'/revisao',
      {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({situacao})});
    await openReport(currentId);
  }catch(e){alert('Falha ao salvar revisão: '+e.message);}
}
function dataVariations(d){
  const box=$('data-variations');box.replaceChildren();
  const variations=d.variacoes_dados||[];
  $('data-count').textContent=(d.itens_editoriais_agrupados??0)+' itens';
  if(!variations.length){box.append(element('div','Nenhuma variação editorial classificada nesta execução.','dim-copy'));return;}
  for(const group of variations){
    const det=element('details',null,'warning-group');
    det.append(element('summary',group.categoria+' · '+group.quantidade_itens+' itens agrupados ('+group.quantidade_ocorrencias+' ocorrências)'));
    det.append(element('p',group.motivo||'Possível variação editorial'));
    const ul=element('ul');
    for(const ex of (group.exemplos||[])){
      const li=element('li');li.append(element('strong',ex.ambiente+' · '+ex.tipo+' · '+ex.elemento),element('div'),safeLink(ex.pagina));ul.append(li);
    }
    if(group.quantidade_itens>(group.exemplos||[]).length)ul.append(element('li','Lista de exemplos limitada. O JSON inclui os totais agrupados.'));
    det.append(ul);box.append(det);
  }
}
function staleSignals(d){
  const box=$('stale-signals');box.replaceChildren();
  const signals=d.sinais_desatualizacao||[];$('signal-count').textContent=signals.length;
  if(!signals.length){box.append(element('div','Nenhum aviso reconhecido no DOM. Isso não garante que as bases sejam equivalentes.','dim-copy'));return;}
  for(const x of signals){const row=element('div',null,'warning-group');row.append(element('strong',x.ambiente+' · '+x.texto),element('p',x.interpretacao),safeLink(x.pagina));box.append(row);}
}
function technical(d){
  const container=$('technical-warnings');container.replaceChildren();
  const avisos=d.avisos_tecnicos||[];
  $('tech-count').textContent=avisos.reduce((a,v)=>a+v.quantidade,0);
  if(!avisos.length){container.append(element('div','Nenhum aviso técnico.','dim-copy'));return;}
  for(const av of avisos){
    const det=element('details',null,'warning-group');
    det.append(element('summary',`${av.ambiente} · ${av.tipo} — ${av.quantidade} ocorrência(s)`));
    const ul=element('ul');for(const url of (av.exemplos||[])){const li=element('li');li.append(/^https?:\/\//.test(url)?safeLink(url):element('span',url));ul.append(li);}
    if(av.quantidade>(av.exemplos||[]).length)ul.append(element('li','Outras ocorrências registradas no JSON exportado.'));
    det.append(ul);container.append(det);
  }
}
function references(d){
  const box=$('reference-warnings');box.replaceChildren();
  const refs=d.referencias_pendentes||[];$('refs-count').textContent=refs.length;
  if(!refs.length){box.append(element('div','Nenhuma diferença de referência anotada.','dim-copy'));return;}
  const det=element('details',null,'warning-group');det.append(element('summary',`Ver ${refs.length} referência(s) para revisão`));
  const ul=element('ul');for(const r of refs.slice(0,80)){
    const li=element('li');li.append(element('strong',r.tipo+' · '+r.elemento),
      element('p','Caminho: '+r.caminho+(r.posicao?' · '+r.posicao:'')),element('p',r.motivo||'Diferença de referência para conferência visual'),element('p',(r.ocorrencias_total||1)+' página(s) afetada(s)'),element('span','Destino '+r.ambiente_a+': '),safeLink(r.destino_a),
      element('br'),element('span','Destino '+r.ambiente_b+': '),safeLink(r.destino_b));ul.append(li);
  }
  if(refs.length>80)ul.append(element('li','Outros registros disponíveis no JSON.'));
  det.append(ul);box.append(det);
}

function externalChecks(d){
  const box=$('external-checks');box.replaceChildren();
  const checks=d.verificacoes_externas||[];$('external-count').textContent=checks.length;
  if(!checks.length){box.append(element('div','Nenhum site externo equivalente foi inspecionado.','dim-copy'));return;}
  for(const check of checks){
    const details=element('details',null,'warning-group');
    details.append(element('summary',check.status+' · '+check.url));
    const content=element('div');content.append(element('p','Origem: '+check.origem),safeLink(check.url));
    const ul=element('ul');for(const option of (check.opcoes||[])){
      const li=element('li');li.append(element('strong',option.opcao+' — '+option.situacao),element('div'),safeLink(option.destino));ul.append(li);
    }
    content.append(ul);details.append(content);box.append(details);
  }
}
function pending(d){
  const box=$('pending-pages');box.replaceChildren();const todos=d.pendencias||[];$('pending-count').textContent=todos.length;
  if(!todos.length){box.append(element('div','Nenhuma página sem correspondência.','dim-copy'));return;}
  const details=element('details',null,'warning-group');details.append(element('summary',`Ver ${todos.length} página(s) pendentes de pareamento`));
  const ul=element('ul');todos.slice(0,100).forEach(p=>{const li=element('li');li.append(element('strong',p.ambiente+' · '),safeLink(p.url),element('span',' — '+p.motivo));ul.append(li);});
  if(todos.length>100)ul.append(element('li','Exibindo 100 itens. Relatório JSON contém todas as pendências.'));
  details.append(ul);box.append(details);
}
function smartResults(d){
  const box=$('smart-results');box.replaceChildren();
  box.append(element('p','Modo: '+(d.modo_varredura||'atual')));
  const o=d.otimizacao||{},m=d.metricas||{};
  if(m.tempo_total_segundos!==undefined)box.append(element('p','Tempo medido: '+m.tempo_total_segundos+' s · '+JSON.stringify(m.contagens||{})));
  box.append(element('p',o.nota||'Relatório anterior sem medições de equivalência.'));
  function lista(titulo,rows){
    const det=element('details');det.append(element('summary',titulo+' ('+rows.length+')'));
    for(const x of rows){const p=element('p',x.elemento||x.categoria||x.classificacao||'Registro');
      p.append(element('span',' · '+(x.classificacao||x.motivo||x.nivel||'')));
      for(const k of ['url_a','url_b','destino_a','destino_b','destino'])if(x[k])p.append(element('br'),safeLink(x[k]));
      if(x.a||x.b)p.append(element('pre',JSON.stringify({a:x.a,b:x.b},null,2)));
      det.append(p);}box.append(det);
  }
  lista('Equivalências estáticas observadas',o.equivalencias_verificadas||[]);
  lista('Equivalências inconclusivas — comparação normal mantida',o.equivalencias_inconclusivas||[]);
  lista('Inspeções profundas omitidas',o.inspecoes_profundas_omitidas||[]);
  lista('Checagem rápida de documentos',d.documentos_verificados||[]);
}
function displayReport(){
  const d=currentReport;if(!d)return;
  $('stat-divergencias').textContent=d.divergencias.filter(r=>!['baixa','editorial'].includes(r.classificacao)).length;
  const vals=Object.values(d.paginas||{});$('stat-a').textContent=vals[0]??0;$('stat-b').textContent=vals[1]??0;
  $('nav-count').textContent=$('stat-divergencias').textContent;
  document.querySelectorAll('[data-export]').forEach(b=>b.disabled=!!(b.dataset.export.startsWith('diagnostico-') && d.versao!=='1.5'));
  const summary=$('report-summary');summary.hidden=false;summary.replaceChildren();
  const inconclusivo=d.situacao_analise==='inconclusivo',parcial=d.situacao_analise==='parcial';
  summary.classList.toggle('important-warning',inconclusivo||parcial);
  const titulo=inconclusivo?'COMPARAÇÃO INCONCLUSIVA':parcial?'VERIFICAÇÃO PARCIAL':'COMPARAÇÃO CONCLUÍDA';
  summary.append(element('strong',titulo+' · '+(d.site_nome||'Portal')));
  summary.append(element('p','Ocorrências originais: '+(d.ocorrencias_brutas??d.divergencias.length)+' · prioritárias: '+$('stat-divergencias').textContent+' · grupos disponíveis: '+d.divergencias.length));
  summary.append(element('p','Baixa relevância e editoriais ficam fora da lista principal. Use Mostrar todas as diferenças para consultar. Inconclusivos continuam visíveis.'));
  if(d.verificacao_cliques_ativa)summary.append(element('p','Testes opcionais de cliques: '+(d.cliques_testados||0)+' link(s) inspecionados. Resultados podem ser inconclusivos.'));
  if(d.ambiente_desatualizado)summary.append(element('p','Base informada como desatualizada: '+d.ambiente_desatualizado+'. Diferenças editoriais separadas de divergências estruturais.'));
  if(d.itens_editoriais_agrupados)summary.append(element('p','Variações editoriais: '+d.itens_editoriais_agrupados+' ocorrências, em '+(d.variacoes_dados||[]).length+' grupo(s) informativo(s).'));
  if(d.divergencias_ocultadas)summary.append(element('p','DIVs excluídas da exibição: '+d.divergencias_ocultadas+' · a coleta original está preservada no disco.'));
  summary.append(element('p',inconclusivo?
    'Um ambiente não teve nenhuma página coletada. As páginas do outro ambiente NÃO são contadas como divergências. Consulte os avisos técnicos.':
    parcial?(d.modo_varredura==='inteligente'?'Cobertura limitada: há conteúdo sem inspeção profunda, documentos sem comparação integral ou pendências. Consulte Equivalência, documentos e cobertura.':'Algumas páginas falharam ou houve interrupção preventiva. As divergências abaixo se referem apenas às páginas pareadas que puderam ser lidas.'):
    'Divergências documentadas apenas nas páginas pareadas. Não determina qual ambiente está correto.'));
  smartResults(d);filters();refilter();dataVariations(d);staleSignals(d);technical(d);references(d);externalChecks(d);pending(d);renderFolders();
}
async function deleteDiv(divId){
  if(!currentId)return;
  if(!window.confirm(`Excluir ${divId} deste relatório? A DIV deixará de aparecer nas exportações futuras. O JSON bruto será preservado.`))return;
  try{
    await api('/api/relatorio/'+encodeURIComponent(currentId)+'/divergencias/'+encodeURIComponent(divId),{method:'DELETE'});
    await openReport(currentId);await loadHistory();
  }catch(e){alert('Não foi possível excluir a divergência: '+e.message);}
}
function updateSelectionBar(){
  $('history-selection').hidden=!selectionMode;
  $('history-select-mode').textContent=selectionMode?'✕ Cancelar seleção':'☑ Selecionar relatórios';
  $('selected-run-count').textContent=selectedRuns.size+' relatório(s) selecionado(s)';
  $('delete-selected-runs').disabled=!selectedRuns.size;
  $('select-all-history').textContent=selectedRuns.size===allHistory.length&&allHistory.length?'Desmarcar todos':'Selecionar todos';
}
function clearReport(){
  currentId=null;currentReport=null;filtered=[];
  $('report-summary').hidden=true;$('result-list').replaceChildren(element('div','Selecione um relatório no histórico ou inicie uma comparação.','empty-state'));
  $('nav-count').textContent='0';$('stat-divergencias').textContent='—';
  document.querySelectorAll('[data-export]').forEach(b=>b.disabled=true);
}
async function deleteRuns(ids){
  if(!ids.length)return;
  if(!window.confirm(`Excluir permanentemente ${ids.length} relatório(s) e suas capturas? Esta ação não pode ser desfeita.`))return;
  try{
    await api('/api/relatorios/excluir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});
    if(currentId&&ids.includes(currentId))clearReport();
    ids.forEach(id=>selectedRuns.delete(id));selectionMode=false;
    await loadHistory();
  }catch(e){alert('Não foi possível excluir os relatórios: '+e.message);}
}
$('history-select-mode').addEventListener('click',()=>{
  selectionMode=!selectionMode;selectedRuns.clear();updateSelectionBar();loadHistory();
});
$('select-all-history').addEventListener('click',()=>{
  if(selectedRuns.size===allHistory.length)selectedRuns.clear();
  else selectedRuns=new Set(allHistory.map(x=>x.id));
  updateSelectionBar();loadHistory();
});
$('delete-selected-runs').addEventListener('click',()=>deleteRuns([...selectedRuns]));
function groupHistory(h){
  const grupos=new Map();for(const x of h){
    const key=x.site_id||('antigo-'+(Object.values(x.ambientes||{})[0]||x.id));
    if(!grupos.has(key))grupos.set(key,[]);
    grupos.get(key).push(x);
  }return [...grupos.values()];
}
function folder(group,forHistory=false){
  const last=group[0],box=element('details',null,'folder-card');
  if(selectionMode)box.open=true;
  else if(currentId&&group.some(x=>x.id===currentId))box.open=!forHistory;
  const name=last.site_nome||'Comparação anterior';
  const header=element('summary');
  const label=element('div');label.append(element('strong','▣ '+name),element('small',group.length+' execução(ões) salva(s)'));
  header.append(label,element('span',last.total+' divergência(s) na última execução','folder-badge'));box.append(header);
  const body=element('div',null,'folder-body');
  for(const h of group){const item=element('div',null,'folder-run');
    if(selectionMode){
      const check=element('input');check.type='checkbox';check.className='run-checkbox';check.checked=selectedRuns.has(h.id);
      check.setAttribute('aria-label','Selecionar relatório de '+h.data);
      check.addEventListener('change',()=>{
        if(check.checked)selectedRuns.add(h.id);else selectedRuns.delete(h.id);
        updateSelectionBar();
      });item.append(check);
    }
    const meta=element('div');meta.append(element('strong',h.data),element('small',h.total+' divergência(s) · '+(h.situacao||'Execução anterior')+' · '+Object.entries(h.paginas||{}).map(([k,v])=>k+': '+v+' pág.').join(' / ')));
    const actions=element('div',null,'run-actions');
    const btn=element('button','Abrir relatório →','outline-button');btn.addEventListener('click',()=>openReport(h.id));
    const trash=element('button','🗑','trash-button');trash.type='button';trash.title='Excluir esta execução';
    trash.setAttribute('aria-label','Excluir relatório de '+h.data);trash.addEventListener('click',()=>deleteRuns([h.id]));
    actions.append(btn,trash);item.append(meta,actions);body.append(item);
  }
  box.append(body);return box;
}
function renderFolders(){
  const box=$('comparison-folders');box.replaceChildren();
  const groups=groupHistory(allHistory);
  if(!groups.length)box.append(element('div','Nenhuma comparação salva.','dim-copy'));
  else groups.forEach(g=>box.append(folder(g)));
}
async function loadHistory(){
  try{
    allHistory=await api('/api/historico');
    selectedRuns=new Set([...selectedRuns].filter(id=>allHistory.some(x=>x.id===id)));updateSelectionBar();
    const list=$('history-list'),activity=$('activity');list.replaceChildren();activity.replaceChildren();
    if(!allHistory.length){list.append(element('div','Nenhuma execução registrada.','empty-state'));activity.append(element('div','Nenhuma comparação realizada.','empty-mini'));renderFolders();return;}
    const latest=allHistory[0];activity.append(element('strong',latest.site_nome||'Comparação anterior'),element('p',latest.data+' · '+latest.total+' divergência(s).'));
    for(const group of groupHistory(allHistory))list.append(folder(group,true));
    renderFolders();
  }catch(e){console.error('Histórico indisponível',e);}
}
async function init(){
  await loadHistory();
  try{const s=await api('/api/status');
    if(s.status==='executando'){nav('comparar');setRunning(true);timer=setInterval(poll,1500);await poll();}
    else if(s.ultimo_id){await openReport(s.ultimo_id);nav('dashboard');}
  }catch(e){console.error(e);}
}
init();
