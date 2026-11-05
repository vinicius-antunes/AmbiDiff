"""Navegação isolada, extração semântica e interações de inspeção permitidas.

Não depende do crawler legado. Limites de operação não são prazos da varredura.
"""
from pathlib import Path
import os
import re
import time
import uuid
from urllib.parse import urlsplit

from .models import Element, Page, stable_id, normalized
from .policy import normalize_url, allowed_url, safe_url, redact_url, classify_resource

_EXTRACT=Path(__file__).with_name('extract.js').read_text(encoding='utf-8')
_ERROR_CODES=(('certificate','CERTIFICATE'),('err_cert','CERTIFICATE'),('timeout','TIMEOUT'),
              ('download','DOCUMENT_DOWNLOAD'),('err_name_not_resolved','DNS'),('err_aborted','NAVIGATION_INTERRUPTED'))


def _error_code(error):
    text=str(error).lower()
    if any(t in text for t in ('target closed','browser has been closed','target page, context or browser')):return 'BROWSER_CLOSED'
    return next((code for term,code in _ERROR_CODES if term in text),'AUTOMATION_ERROR')


class BrowserSession:
    def __init__(self,roots,evidence_dir,stop,config=None):
        self.roots=tuple(normalize_url(x) for x in roots)
        if len(self.roots)!=2:raise ValueError('Configure exatamente dois ambientes')
        self.evidence_dir=Path(evidence_dir);self.evidence_dir.mkdir(parents=True,exist_ok=True)
        self.stop=stop;self.config=config or {};self.contexts=[];self.pages=[];self.pw=None;self.browser=None
        self.blocks=[[],[]];self.interacting=[False,False];self.current=[None,None];self.token=uuid.uuid4().hex[:10];self.sequence=0
        self.metrics={'navigations':0,'functional_navigations':0,'functional_tests':0,'screenshots':0,'recoveries':0,'blocked_requests':0,'navigation_seconds':0.,'extraction_seconds':0.,'capture_seconds':0.,'evidence_seconds':0.,'functional_seconds':0.,'discovery_seconds':0.,'preparation_seconds':0.,'document_requests':0}

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.pw=sync_playwright().start()
        try:self._launch()
        except Exception:
            self.pw.stop();raise
        return self

    def _launch(self):
        options={'headless':True}
        executable=self.config.get('executable_path') or os.environ.get('AMBIDIFF_NEXT_CHROMIUM')
        if executable:options['executable_path']=executable
        self.browser=self.pw.chromium.launch(**options)
        self.contexts=[];self.pages=[]
        viewport=self.config.get('viewport',{'width':1366,'height':850})
        for side in (0,1):
            context=self.browser.new_context(viewport=viewport,device_scale_factor=1,accept_downloads=False,
                service_workers='block',locale='pt-BR',reduced_motion='reduce')
            context.set_default_timeout(int(self.config.get('operation_timeout_ms',5000)))
            context.set_default_navigation_timeout(int(self.config.get('navigation_timeout_ms',20000)))
            context.route('**/*',lambda route,request,side=side:self._route(route,side))
            if hasattr(context,'route_web_socket'):context.route_web_socket('**/*',lambda socket:socket.close())
            self.contexts.append(context);self.pages.append(context.new_page())

    def _route(self,route,side):
        request=route.request;method=request.method.upper();url=request.url
        reason=''
        if self.stop.is_set():reason='interrupção solicitada'
        elif method not in ('GET','HEAD'):reason='método modificador ou não autorizado'
        elif self.interacting[side]:reason='requisição disparada por interação sem autorização específica'
        elif not safe_url(url):reason='URL potencialmente modificadora ou inválida'
        elif not allowed_url(url,self.roots[side]):reason='fora do escopo autorizado'
        if reason:
            self.metrics['blocked_requests']+=1
            # Não guarda cookies, cabeçalhos, corpos ou valores da query.
            entry={'method':method,'url':redact_url(url),'resource':classify_resource(url),'reason':reason,
                   'navigation':request.is_navigation_request()}
            if len(self.blocks[side])<200:self.blocks[side].append(entry)
            route.abort('blockedbyclient')
        else:route.continue_()

    def __exit__(self,*args):
        for context in self.contexts:
            try:context.close()
            except Exception:pass
        if self.browser:
            try:self.browser.close()
            except Exception:pass
        if self.pw:
            try:self.pw.stop()
            except Exception:pass

    def _recover(self):
        for context in self.contexts:
            try:context.close()
            except Exception:pass
        try:self.browser.close()
        except Exception:pass
        self._launch();self.metrics['recoveries']+=1

    def _capture(self,target,side,identifier,**options):
        self.sequence+=1
        filename=f'{self.token}_{self.sequence}_{side}_{identifier}.png'
        started=time.perf_counter()
        try:
            target.screenshot(path=str(self.evidence_dir/filename),animations='disabled',caret='hide',timeout=int(self.config.get('capture_timeout_ms',3000)),**options)
            self.metrics['screenshots']+=1
            return filename
        finally:
            elapsed=time.perf_counter()-started
            self.metrics['capture_seconds']+=elapsed;self.metrics['evidence_seconds']+=elapsed

    def collect(self,url,side,trail=()):
        """Uma navegação, uma extração; falhas locais retornam diagnóstico explícito."""
        if side not in (0,1):raise ValueError('Ambiente inválido')
        try:url=normalize_url(url,self.roots[side])
        except ValueError:
            return Page(str(url),str(url),'',status=0,diagnostics=[{'code':'INVALID_URL','message':'URL malformada; não navegada'}])
        if not allowed_url(url,self.roots[side]):return Page(url,url,'',status=0,diagnostics=[{'code':'OUT_OF_SCOPE','message':'URL fora do escopo ou operação não autorizada'}])
        if self.stop.is_set():return Page(url,url,'',status=0,diagnostics=[{'code':'STOPPED','message':'Interrupção solicitada antes da navegação'}])
        diagnostics=[]
        for attempt in range(2):
            start=time.perf_counter();page=self.pages[side];response=None
            try:
                self.blocks[side].clear();self.metrics['navigations']+=1
                response=page.goto(url,wait_until='domcontentloaded')
                self.metrics['navigation_seconds']+=time.perf_counter()-start
                status=response.status if response else 0
                redirects=[]
                if response:
                    req=response.request
                    while req:
                        # URLs são dados de comparação; nunca registrar headers/token.
                        redirects.append(req.url);req=req.redirected_from
                    redirects.reverse()
                    headers=response.all_headers();mime=headers.get('content-type','').split(';')[0].lower()
                    disposition=headers.get('content-disposition','').lower()
                    if 'attachment' in disposition or (mime and mime not in ('text/html','application/xhtml+xml')):
                        return Page(url,page.url,'Recurso não HTML',status=status,redirects=redirects,
                            diagnostics=diagnostics+[{'code':'DOCUMENT_DOWNLOAD' if 'attachment' in disposition else 'NON_HTML','message':'Apenas metadados; corpo documental não analisado','mime':mime,'resource':classify_resource(page.url,{'mime':mime})}])
                if status>=400:
                    return Page(url,page.url,'Falha HTTP',status=status,redirects=redirects,diagnostics=diagnostics+[{'code':'HTTP_ERROR','message':f'HTTP {status}; não comprova ausência'}])
                if not allowed_url(page.url,self.roots[side]):
                    return Page(url,page.url,'Destino restrito',status=status,redirects=redirects,diagnostics=diagnostics+[{'code':'OUT_OF_SCOPE','message':'Navegação encerrou fora do escopo'}])
                self.current[side]=url
                # Não aguarda networkidle: analytics ou polling não definem prontidão.
                started=time.perf_counter();raw=page.evaluate(_EXTRACT)
                self.metrics['extraction_seconds']+=time.perf_counter()-started
                if not isinstance(raw,dict) or not isinstance(raw.get('items'),list):raise RuntimeError('DOM não retornou modelo válido')
                if raw.get('ready')!='complete':diagnostics.append({'code':'INCOMPLETE_LOADING','message':'DOM disponível antes de carregamento completo; conteúdo tardio pode não ter sido observado'})
                if raw.get('auth'):diagnostics.append({'code':'AUTHENTICATION','message':'Página de autenticação detectada; nenhuma autenticação foi executada'})
                components=[]
                for index,item in enumerate(raw['items']):
                    resource=classify_resource(item.get('url',''),item.get('attrs'))
                    if item.get('kind')=='link' and resource in ('document','document_reference'):item['kind']='document'
                    item['attrs']['resource']=resource;item['attrs']['source_url']=url
                    item['attrs']['extraction']='accessible-dom';item['attrs']['index']=index
                    item['path']=[*trail,item['section'],item['name']][-16:]
                    item['id']=stable_id('el',side,url,item['kind'],item['name'],item['section'],item['selector'])
                    components.append(Element(**item))
                result=Page(url,page.url,raw.get('title',''),components,status,redirects,diagnostics=diagnostics)
                if not raw.get('auth'):self._evidence(result,side)
                self._block_diagnostics(result,side)
                if not components:result.diagnostics.append({'code':'EMPTY_DOM','message':'Nenhum componente analisável encontrado; comparação estrutural limitada'})
                return result
            except Exception as exc:
                self.metrics['navigation_seconds']+=max(0,time.perf_counter()-start) if response is None else 0
                code=_error_code(exc)
                if code=='BROWSER_CLOSED' and attempt==0 and not self.stop.is_set():
                    diagnostics.append({'code':code,'message':'Recurso encerrado; uma recuperação controlada foi tentada'})
                    try:self._recover();continue
                    except Exception:pass
                # Mensagem reduzida por código evita URLs/segredos inseridos pelo driver.
                result=Page(url,getattr(page,'url',url),'',status=0,diagnostics=diagnostics+[{'code':code,'message':'Operação não concluída; verifique acesso, certificado, documento ou disponibilidade do navegador'}])
                self._block_diagnostics(result,side);return result

    def _block_diagnostics(self,result,side):
        if self.blocks[side]:
            helpers=sum(x['resource']=='auxiliary' for x in self.blocks[side])
            result.diagnostics.append({'code':'POLICY_BLOCKS','message':'Restrições de inspeção podem afetar widgets; bloqueio isolado não é defeito do site',
                'count':len(self.blocks[side]),'auxiliary':helpers,'examples':self.blocks[side][:12]})

    def _evidence(self,result,side):
        page=self.pages[side]
        try:result.screenshot=self._capture(page,side,'viewport')
        except Exception:result.diagnostics.append({'code':'CAPTURE_FAILED','message':'Captura de viewport indisponível; não houve validação visual integral'})
        limit=max(0,min(200,int(self.config.get('max_component_captures',40))))
        visible=[e for e in result.elements if e.visible and e.kind not in ('form','field','heading','section')]
        hidden=[e for e in result.elements if not e.visible and e.kind not in ('form','field','heading','section')
                and e.attrs.get('style',{}).get('visibility')=='hidden' and e.bbox.get('width',0)>0 and e.bbox.get('height',0)>0]
        # Regiões ocultas são capturadas primeiro, antes que screenshots de
        # locators rolem a página. A imagem é do viewport real, não do controle
        # invisível; display:none não possui região e continua sem evidência.
        candidates=hidden+visible
        viewport=page.evaluate('({width:innerWidth,height:innerHeight,x:scrollX,y:scrollY})')
        for element in candidates[:limit]:
            if self.stop.is_set():break
            try:
                if not element.visible:
                    box=element.bbox;x=max(0,box['x']);y=max(0,box['y'])
                    width=min(viewport['width'],box['x']+box['width'])-x
                    height=min(viewport['height'],box['y']+box['height'])-y
                    if width<=0 or height<=0:
                        element.attrs['capture_error']='Região oculta fora do viewport observado';continue
                    clip={'x':x+viewport['x'],'y':y+viewport['y'],'width':width,'height':height}
                    element.attrs['screenshot']=self._capture(page,side,element.id,clip=clip)
                    element.attrs['evidence_nature']='region_not_visible_control'
                    element.attrs['capture_region']=clip
                    result.diagnostics.append({'code':'HIDDEN_REGION_EVIDENCE','message':'Captura real da região visual; o controle CSS continua invisível','element_id':element.id})
                else:element.attrs['screenshot']=self._capture(page.locator(element.selector),side,element.id)
            except Exception:element.attrs['capture_error']='Captura do componente indisponível'
        if len(candidates)>limit:result.diagnostics.append({'code':'CAPTURE_LIMIT','message':'Alguns componentes não receberam captura individual','captured':limit,'eligible':len(candidates)})

    def inspect_document(self,url,side):
        """Cabeçalhos HEAD locais ao escopo; nenhum corpo documental é baixado."""
        from urllib.parse import urljoin
        if side not in (0,1):raise ValueError('Ambiente inválido')
        result={'url':url,'final_url':url,'redirects':[],'status':0,'content_type':'','kind':'unknown','error':''}
        try:
            current=normalize_url(url,self.roots[side])
            for _ in range(6):
                if self.stop.is_set():result['error']='STOPPED';return result
                if not allowed_url(current,self.roots[side]):result['error']='OUT_OF_SCOPE';return result
                result['redirects'].append(current);result['final_url']=current
                self.metrics['document_requests']+=1
                response=self.contexts[side].request.head(current,max_redirects=0,timeout=int(self.config.get('navigation_timeout_ms',20000)))
                try:
                    status=response.status;headers=response.headers;result['status']=status
                    result['content_type']=headers.get('content-type','').split(';')[0].lower()
                    if 300<=status<400 and headers.get('location'):
                        current=normalize_url(urljoin(current,headers['location']));continue
                    result['kind']=classify_resource(current,{'mime':result['content_type']})
                    if status>=400:result['error']='HTTP_'+str(status)
                    return result
                finally:response.dispose()
            result['error']='REDIRECT_LIMIT'
        except Exception as exc:result['error']=_error_code(exc)
        return result

    def perform(self,element,side):
        """Testa somente links HTTP internos e controles ARIA/details reconhecidos.

        Cada teste usa página temporária em contexto isolado do ambiente; não há
        continuidade de estado entre controles nem submissão de formulários.
        """
        started=time.perf_counter();page=None
        def outcome(status,message,**extra):return {'status':status,'changed':False,'observation':message,**extra}
        if side not in (0,1):return outcome('untested','Ambiente inválido')
        if self.stop.is_set():return outcome('untested','Interrupção solicitada')
        if not element.enabled or not element.visible:return outcome('untested','Elemento desabilitado ou não visível')
        name=normalized(element.name)
        if re.search(r'\b(excluir|deletar|remover|salvar|enviar|entrar|login|sair|logout|pagar|comprar|cadastrar|criar|alterar)\b',name):return outcome('untested','Interação não consta na lista de ações de leitura permitidas')
        source=element.attrs.get('source_url')
        if not source or not allowed_url(source,self.roots[side]):return outcome('untested','Página de origem não autorizada ou desconhecida')
        is_link=element.kind in ('link','document') and bool(element.url)
        safe_control=element.kind in ('button','tab') and (element.attrs.get('aria_controls') or element.attrs.get('tag')=='summary')
        if not is_link and not safe_control:return outcome('untested','Sem contrato ARIA/details ou destino HTTP seguro; existência não comprova funcionamento')
        if is_link and not allowed_url(element.url,self.roots[side]):return outcome('untested','Destino externo, inválido ou potencialmente modificador; referência não explorada')
        if element.kind=='document':return outcome('untested','Documento é avaliado por metadados, não por clique/download')
        if not is_link and element.attrs.get('inline_handler'):return outcome('untested','Handler inline sem contrato seguro verificável; ação não executada')
        try:
            page=self.contexts[side].new_page();self.metrics['functional_tests']+=1
            self.metrics['functional_navigations']+=1;self.metrics['navigations']+=1
            page.goto(source,wait_until='domcontentloaded')
            target=page.locator(element.selector)
            if not target.count():return outcome('inconclusive','Elemento não reencontrado na página temporária')
            if is_link:
                # Navegação direta de leitura é observável; não executa JS arbitrário.
                self.metrics['functional_navigations']+=1;self.metrics['navigations']+=1
                response=page.goto(element.url,wait_until='domcontentloaded')
                status=response.status if response else 0
                return {'status':'executed' if status and status<400 else 'inconclusive','changed':status>0 and status<400,
                        'observation':'Navegação HTTP segura observada; handler de clique JavaScript não executado',
                        'final_url':page.url,'http_status':status,'action':'direct_navigation'}
            script="""e=>{const p=e.getAttribute('aria-controls');const t=p?document.getElementById(p):e.closest('details');return {expanded:e.getAttribute('aria-expanded'),selected:e.getAttribute('aria-selected'),open:t?.open,visible:t?!!(t.getBoundingClientRect().height && getComputedStyle(t).display!=='none'):null,text:t?.textContent?.slice(0,1000)}}"""
            before=target.evaluate(script)
            # Um submit sem type=button jamais é tratado como controle seguro.
            if target.evaluate("e=>!!e.closest('form') && e.tagName==='BUTTON' && (e.getAttribute('type')||'submit')!=='button'"):return outcome('untested','Botão de formulário não é interação permitida')
            evidence={}
            try:evidence['before']=self._capture(target,side,element.id+'_before')
            except Exception:pass
            self.blocks[side].clear();self.interacting[side]=True
            target.click(timeout=int(self.config.get('operation_timeout_ms',5000)))
            page.wait_for_timeout(min(300,int(self.config.get('interaction_wait_ms',150))))
            after=target.evaluate(script)
            try:evidence['after']=self._capture(target,side,element.id+'_after')
            except Exception:pass
            if self.blocks[side]:return outcome('inconclusive','A política bloqueou requisições durante a interação; não atribuir falha ao site',evidence=evidence)
            changed=before!=after
            return {'status':'executed','changed':changed,'observation':'Estado ARIA/painel alterado' if changed else 'Nenhuma alteração observável de estado ARIA/painel',
                    'before':before,'after':after,'evidence':evidence,'action':'safe_ui_control'}
        except Exception as exc:return outcome('inconclusive','Interação não concluída: '+_error_code(exc))
        finally:
            self.interacting[side]=False
            self.metrics['functional_seconds']+=time.perf_counter()-started
            if page:
                try:page.close()
                except Exception:pass
