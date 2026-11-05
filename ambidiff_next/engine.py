"""Orquestra componentes e verificações; não depende do crawler legado."""
from collections import Counter
from pathlib import Path
import os
import time
from .models import finding,Page,normalized
from .planner import Planner,priority
from .policy import normalize_url,allowed_url,safe_url,classify_resource,equivalent_url
from .browser import BrowserSession
from .comparison import compare_pages,compare_functions
from .visual import compare_components


def validate_config(config):
    cfg=dict(config)
    roots=cfg.get('roots',[])
    if not isinstance(roots,(list,tuple)) or len(roots)!=2:raise ValueError('Informe os dois ambientes')
    cfg['roots']=[normalize_url(u) for u in roots]
    if not all(safe_url(u) for u in cfg['roots']):raise ValueError('Rota inicial não autorizada para inspeção')
    labels=cfg.get('labels',['PRD','HOMOL'])
    if not isinstance(labels,list) or len(labels)!=2 or any(x not in ('PRD','HOMOL','DES','LAB') for x in labels) or labels[0]==labels[1]:raise ValueError('Identificações de ambiente inválidas')
    cfg['labels']=labels
    cfg['max_pages']=int(cfg.get('max_pages',cfg.get('capacity',1000)))
    if not 1<=cfg['max_pages']<=1000:raise ValueError('Capacidade: 1 a 1.000 pares planejados')
    cfg['editorials_per_template']=int(cfg.get('editorials_per_template',2))
    if not 1<=cfg['editorials_per_template']<=10:raise ValueError('Amostras editoriais: 1 a 10')
    viewport=cfg.get('viewport',{'width':1366,'height':850})
    if not isinstance(viewport,dict) or set(viewport)!={'width','height'} or any(type(v) is not int or not 320<=v<=3840 for v in viewport.values()):raise ValueError('Viewport inválido')
    cfg['viewport']=viewport
    # Caminho de executável é configuração local; não é preenchido por URLs.
    if os.getenv('AMBIDIFF_NEXT_CHROMIUM') and not cfg.get('executable_path'):cfg['executable_path']=os.environ['AMBIDIFF_NEXT_CHROMIUM']
    return cfg


class Engine:
    def __init__(self,store,evidence_dir,session_factory=BrowserSession):
        self.store=store;self.evidence_dir=Path(evidence_dir);self.session_factory=session_factory
    def run(self,rid,stop):
        cfg=validate_config(self.store.get_run(rid)['config']);roots=cfg['roots'];planner=Planner(self.store,rid,cfg)
        self.store.recover(rid)
        if not self.store.tasks(rid):planner.propose(*roots,['Página inicial'])
        metrics=Counter(self.store.get_run(rid)['metrics']);started=time.perf_counter();task=None;browser=None
        self.store.update_run(rid,status='running',current='Mapeamento inicial',error=None)
        self.store.log(rid,'Execução iniciada; análise limitada às referências e componentes planejados')
        def diagnose(item):self.store.diagnose(rid,item)
        def record(item):self.store.add_finding(rid,item)
        def update():
            tasks=self.store.tasks(rid);states=Counter(t['state'] for t in tasks)
            metrics['tasks_planned']=len(tasks);metrics['tasks_done']=sum(states[k] for k in ('done','failed','inconclusive','sampled','blocked'))
            metrics['tasks_pending']=states['pending'];metrics['technical_failures']=states['failed']
            metrics['sampled_pages']=states['sampled']
            metrics['pages_discovered']=len({(side,u) for t in tasks for side,u in enumerate(t['payload'].get('urls',[])) if u})
            metrics['elapsed_seconds']=metrics.get('previous_elapsed_seconds',0)+time.perf_counter()-started
            categories={}
            for rank,label in enumerate(('estrutura','servicos','documentos','institucional','editorial')):
                subset=[t for t in tasks if t['payload'].get('category')==rank]
                categories[label]={'planned':len(subset),'done':sum(t['state']=='done' for t in subset),'inconclusive':sum(t['state'] in ('inconclusive','failed') for t in subset),'not_examined':sum(t['state'] in ('sampled','blocked','pending') for t in subset)}
            values=dict(metrics);values['coverage']=categories
            if browser:
                for key,value in browser.metrics.items():
                    if isinstance(value,(int,float)):values[key]=initial_browser_metrics.get(key,0)+value
            values['seconds']={k.removesuffix('_seconds'):v for k,v in values.items() if k.endswith('_seconds') and isinstance(v,(int,float))}
            self.store.update_run(rid,metrics=values)
        initial_browser_metrics=dict(metrics)
        try:
            with self.session_factory(roots,self.evidence_dir,stop,cfg) as browser:
                while not stop.is_set() and self.store.get_run(rid)['status']!='stop_requested':
                    task=self.store.claim(rid)
                    if task is None:break
                    payload=task['payload'];urls=payload['urls'];trail=payload['trail']
                    self.store.update_run(rid,current={'task':task['id'],'kind':task['kind'],'urls':urls,'trail':trail})
                    self.store.log(rid,'Analisando '+payload['element'])
                    try:
                        if task['kind']=='document':
                            results=[]
                            for side,url in enumerate(urls):
                                if not url:results.append({'status':'not_tested','reason':'Referência sem contraparte'});continue
                                if hasattr(browser,'inspect_document'):results.append(browser.inspect_document(url,side))
                                else:results.append({'status':'not_tested','reason':'Somente referência: cabeçalhos não inspecionados'})
                            metrics['documents_checked']+=sum(isinstance(x.get('status'),int) and x['status']>0 for x in results)
                            diagnose({'task':task['id'],'kind':'document','urls':urls,'results':results})
                            for side,result in enumerate(results):
                                status=result.get('http_status',result.get('status',0))
                                if isinstance(status,int) and status>=400:
                                    record(finding('documento_inacessivel','documento',payload['element'],*urls,confidence='confirmado',observed_a=str(status) if side==0 else '',observed_b=str(status) if side==1 else ''))
                            self.store.finish(rid,task['id'],'done' if all(not x.get('error') and isinstance(x.get('status'),int) and x['status']>0 for x in results) else 'inconclusive','Cabeçalhos apenas; conteúdo documental não comparado',result=results)
                        else:
                            pages=[]
                            for side,url in enumerate(urls):
                                if not url:pages.append(None);continue
                                page=self.store.get_page(rid,side,url)
                                if page is None:
                                    page=browser.collect(url,side,trail)
                                    if stop.is_set():break
                                    self.store.save_page(rid,side,page)
                                    metrics['pages_visited']+=1;metrics['components_mapped']+=len(page.elements)
                                else:metrics['page_models_reused']+=1
                                pages.append(page)
                                for d in page.diagnostics:diagnose({'task':task['id'],'side':side,**d})
                            if stop.is_set():
                                self.store.finish(rid,task['id'],'pending','Interrupção recebida; coleta atual não foi declarada concluída');break
                            if not all(pages):
                                metrics['pages_without_counterpart']+=1
                                diagnose({'task':task['id'],'urls':urls,'status':'inconclusive','reason':'Referência unilateral inspecionada; ausência da página não comprovada. Árvore unilateral não expandida.'})
                                self.store.finish(rid,task['id'],'inconclusive','Sem contraparte comprovada; árvore não expandida')
                            else:
                                a,b=pages
                                if task['reason'].startswith('Hipótese intermediária'):
                                    from .matching import match_elements,similarity
                                    checks=match_elements(a,b,roots)
                                    source_titles={normalized(p.title) for side,root in enumerate(roots) if (p:=self.store.get_page(rid,side,root))}
                                    confirmed=(bool(a.title and b.title) and similarity(a.title,b.title)>=.75
                                        and normalized(a.title) not in source_titles
                                        and sum(m['confidence']=='alta' for m in checks['matches'])>=2
                                        and not any(p.status==0 or p.status>=400 or any(d.get('code') in ('AUTHENTICATION','INCOMPLETE_LOADING','EMPTY_DOM') for d in p.diagnostics) for p in pages))
                                    diagnose({'task':task['id'],'kind':'corroboration','accepted':confirmed,'titles':[a.title,b.title],
                                        'reason':'Título específico e estrutura compatível observados; aparência sozinha não comprova equivalência'})
                                    if not confirmed:
                                        self.store.finish(rid,task['id'],'inconclusive','Hipótese de correspondência sem corroboração suficiente')
                                        task=None;update();continue
                                    metrics['correspondences_corroborated']+=1
                                before=time.perf_counter();result=compare_pages(a,b,roots,cfg)
                                metrics['comparison_seconds']+=time.perf_counter()-before
                                metrics['elements_checked']+=len(a.elements)+len(b.elements)
                                metrics['components_compared']+=len(result['matches'])
                                metrics['equivalent_elements']+=sum(m['confidence']=='alta' for m in result['matches'])
                                metrics['candidate_elements']+=sum(m['confidence']!='alta' for m in result['matches'])
                                metrics['links_evaluated']+=sum(bool(e.url) for e in a.elements+b.elements)
                                metrics['redirects_checked']+=len(a.redirects)+len(b.redirects)
                                for row in result['findings']:record(row)
                                for row in result['diagnostics']:diagnose({'task':task['id'],**row})
                                aa={e.id:e for e in a.elements};bb={e.id:e for e in b.elements}
                                matched=set();actions=0
                                for match in result['matches']:
                                    x,y=aa[match['a']],bb[match['b']];matched.update((x.id,y.id))
                                    if match['confidence']!='alta':
                                        diagnose({'task':task['id'],'elements':[x.id,y.id],'status':'inconclusive','reason':'Correspondência intermediária: exige observação adicional da finalidade e estrutura'})
                                        if x.url and y.url and classify_resource(x.url,x.attrs)=='navigation' and classify_resource(y.url,y.attrs)=='navigation':
                                            planner.propose(x.url,y.url,trail+[x.name],x,'Hipótese intermediária: '+match['criteria'])
                                        continue
                                    before=time.perf_counter();visual=compare_components(x,y,self.evidence_dir,a.url,b.url)
                                    metrics['visual_seconds']+=time.perf_counter()-before
                                    metrics['visual_compared']+=int(visual.get('metrics',{}).get('completed',False))
                                    for row in visual['findings']:record(row)
                                    for row in visual['diagnostics']:diagnose({'task':task['id'],**row})
                                    if x.kind in ('tab','button','summary') or x.role in ('tab','button'):
                                        if actions<cfg.get('max_functional_per_page',8):
                                            obs=[browser.perform(e,side) for side,e in enumerate((x,y))];actions+=1
                                            executed=sum(o.get('status')=='executed' for o in obs)
                                            metrics['functional_executed']+=executed
                                            metrics['functional_inconclusive']+=2-executed
                                            functional=compare_functions(*obs,element=x.name,page_a=a.url,page_b=b.url,section=x.section)
                                            for row in functional['findings']:record(row)
                                            if executed==2 and functional['diagnostics']:metrics['functional_inconclusive']+=2
                                            for row in functional['diagnostics']:diagnose({'task':task['id'],**row})
                                            diagnose({'task':task['id'],'element':x.name,'kind':'functional','observations':obs})
                                        else:
                                            metrics['functional_inconclusive']+=2
                                            diagnose({'task':task['id'],'element':x.name,'status':'not_tested','reason':'Orçamento explícito de interações por página; não validado'})
                                    if x.url and y.url:
                                        resource=classify_resource(x.url,x.attrs)
                                        if resource not in ('media','auxiliary'):
                                            planner.propose(x.url,y.url,trail+[x.name],x,'Correspondência alta: '+match['criteria'])
                                # Referências unilaterais estruturais têm uma inspeção;
                                # editoriais sem par ficam registradas, não viram árvore.
                                for side,page in enumerate((a,b)):
                                    for e in page.elements:
                                        if e.id not in matched and e.url and allowed_url(e.url,roots[side]):
                                            if priority(e)<=3 and classify_resource(e.url,e.attrs) not in ('media','auxiliary'):
                                                planner.propose(e.url if side==0 else '',e.url if side==1 else '',trail+[e.name],e,'Referência sem correspondência inequívoca')
                                            elif e.editorial:diagnose({'element':e.id,'url':e.url,'status':'not_planned','reason':'Editorial unilateral sem contraparte; referência preservada sem expansão'})
                                has_failure=any(p.status==0 or p.status>=400 for p in pages)
                                metrics['page_pairs_attempted']+=1
                                if not has_failure:metrics['page_pairs_compared']+=1
                                self.store.finish(rid,task['id'],'failed' if has_failure else 'done','Coleta limitada' if has_failure else 'Comparação realizada; consultar verificações não executadas',{'matches':result['matches']})
                        task=None;update()
                    except Exception as exc:
                        from .browser import _error_code
                        self.store.finish(rid,task['id'],'failed',type(exc).__name__+': '+str(exc)[:400])
                        diagnose({'task':task['id'],'status':'failed','code':_error_code(exc),'reason':type(exc).__name__+': '+str(exc)[:400]})
                        record(finding('falha_automacao','automacao',payload['element'],*urls,confidence='inconclusivo',observed_a=type(exc).__name__,recommendation='Consultar diagnóstico; não comprova defeito do site'))
                        task=None;update()
                interrupted=stop.is_set() or self.store.get_run(rid)['status']=='stop_requested'
                if interrupted and task:self.store.finish(rid,task['id'],'pending','Interrupção solicitada')
                update()
                states=Counter(t['state'] for t in self.store.tasks(rid))
                status='interrupted' if interrupted else 'partial' if any(states[k] for k in ('failed','inconclusive','sampled','blocked','pending')) else 'completed'
                self.store.update_run(rid,status=status,current='Fila planejada encerrada; cobertura não equivale à totalidade do portal')
        except Exception as exc:
            if task:self.store.finish(rid,task['id'],'pending' if task['attempts']<2 else 'failed','Falha global; recuperação limitada')
            update();self.store.update_run(rid,status='failed',error=type(exc).__name__+': '+str(exc)[:400],current='Falha; resultados parciais preservados')
            diagnose({'status':'failed','reason':type(exc).__name__+': '+str(exc)[:400]})
        finally:
            metrics_now=self.store.get_run(rid)['metrics'];metrics_now['previous_elapsed_seconds']=metrics_now.get('elapsed_seconds',0)
            self.store.update_run(rid,metrics=metrics_now)
            self.store.log(rid,'Encerramento: '+self.store.get_run(rid)['status']+'; dados preservados localmente')
