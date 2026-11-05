"""Chromium real com servidor loopback fictício; nenhum portal institucional."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import shutil
import threading
import pytest
from ambidiff_next.browser import BrowserSession

HTML='''<!doctype html><title>Portal fictício</title><style>#hidden{display:none}.cover{position:absolute;left:0;top:0;background:red}</style>
<nav aria-label="Serviços"><a href="./consulta?c=1&e=2">Consultar processo</a><a id="hidden" href="./audios">ÁUDIOS</a></nav>
<button type="button" aria-controls="panel" aria-expanded="false" id="toggle">Abrir detalhes</button><section id="panel" hidden>Atendimento ao consumidor</section>
<script>document.getElementById('toggle').addEventListener('click',()=>{let p=document.getElementById('panel');p.hidden=!p.hidden;document.getElementById('toggle').setAttribute('aria-expanded',!p.hidden)})</script>
<form action="./submit" method="POST"><input name="q"><button>Enviar</button></form>
<a href="./documents/d/org/boletim">Boletim</a><a href="./logout">Sair</a><img src="https://external.invalid/tracker.png" alt="Recurso auxiliar">
'''


@contextmanager
def portal():
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):received.append(('POST',self.path));self.send_error(405)
        def do_HEAD(self):
            received.append(('HEAD',self.path))
            self.send_response(200);self.send_header('content-type','application/pdf' if '/documents/' in self.path else 'text/html');self.end_headers()
        def do_GET(self):
            received.append(('GET',self.path))
            if self.path.endswith('/redirect'):
                self.send_response(302);self.send_header('location','./home');self.end_headers();return
            if self.path.endswith('/error'):self.send_error(503);return
            if self.path.endswith('/download'):
                self.send_response(200);self.send_header('content-type','application/pdf');self.send_header('content-disposition','attachment; filename=a.pdf');self.end_headers();return
            self.send_response(200);self.send_header('content-type','text/html; charset=utf-8');self.end_headers();self.wfile.write(HTML.encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',received
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def config():
    # Ambiente de CI oficial usa o navegador Playwright; fallback local é explícito.
    path=shutil.which('chromium')
    return {'executable_path':path,'max_component_captures':8,'navigation_timeout_ms':3000,'operation_timeout_ms':1500} if path else {'max_component_captures':8}


def test_structural_map_hidden_audios_and_real_evidence(tmp_path):
    with portal() as (base,received),BrowserSession((base+'/a/',base+'/b/'),tmp_path,threading.Event(),config()) as browser:
        a=browser.collect(base+'/a/home',0)
        assert a.title=='Portal fictício'
        audio=next(x for x in a.elements if x.name=='ÁUDIOS')
        assert not audio.visible and audio.kind=='link'
        assert any(x.kind=='form' for x in a.elements)
        assert any(x.kind=='document' and x.name=='Boletim' for x in a.elements)
        assert a.screenshot and (tmp_path/a.screenshot).read_bytes().startswith(b'\x89PNG')
        assert any(x.attrs.get('screenshot') for x in a.elements)
        assert any(x['code']=='POLICY_BLOCKS' for x in a.diagnostics)
        assert all(method=='GET' for method,_ in received)


def test_safe_ui_control_actual_change_and_destructive_get_blocked(tmp_path):
    with portal() as (base,received),BrowserSession((base+'/a/',base+'/b/'),tmp_path,threading.Event(),config()) as browser:
        p=browser.collect(base+'/a/home',0)
        control=next(x for x in p.elements if x.name=='Abrir detalhes')
        result=browser.perform(control,0)
        assert result['status']=='executed' and result['changed']
        assert result['evidence'].get('before') and result['evidence'].get('after')
        sair=next(x for x in p.elements if x.name=='Sair')
        assert browser.perform(sair,0)['status']=='untested'
        bad=browser.collect(base+'/a/logout',0)
        assert bad.diagnostics[0]['code']=='OUT_OF_SCOPE'
        assert not any('/logout' in u or method=='POST' for method,u in received)


def test_request_policy_blocks_post_and_sessions_are_isolated(tmp_path):
    with portal() as (base,received),BrowserSession((base+'/a/',base+'/b/'),tmp_path,threading.Event(),config()) as browser:
        browser.collect(base+'/a/home',0);browser.collect(base+'/b/home',1)
        browser.contexts[0].add_cookies([{'name':'only_a','value':'fixture','url':base}])
        assert not browser.contexts[1].cookies()
        browser.pages[0].evaluate("fetch('./submit',{method:'POST',body:'x'}).catch(()=>null)")
        assert not any(method=='POST' for method,_ in received)


def test_redirect_http_error_document_head_and_download(tmp_path):
    with portal() as (base,received),BrowserSession((base+'/a/',base+'/b/'),tmp_path,threading.Event(),config()) as browser:
        p=browser.collect(base+'/a/redirect',0)
        assert len(p.redirects)==2 and p.final_url.endswith('/home')
        bad=browser.collect(base+'/a/error',0)
        assert bad.status==503 and bad.diagnostics[0]['code']=='HTTP_ERROR'
        meta=browser.inspect_document(base+'/a/documents/d/org/boletim',0)
        assert meta['kind']=='document' and meta['content_type']=='application/pdf'
        assert ('HEAD','/a/documents/d/org/boletim') in received
        assert ('GET','/a/documents/d/org/boletim') not in received
        download=browser.collect(base+'/a/download',0)
        assert any(x['code'] in ('DOCUMENT_DOWNLOAD','NON_HTML') for x in download.diagnostics)


def test_browser_closed_recovers_once_and_stop_preserves_control(tmp_path):
    stop=threading.Event()
    with portal() as (base,_),BrowserSession((base+'/a/',base+'/b/'),tmp_path,stop,config()) as browser:
        browser.browser.close();p=browser.collect(base+'/a/home',0)
        assert p.elements and browser.metrics['recoveries']==1
        stop.set();p=browser.collect(base+'/b/home',1)
        assert p.status==0 and p.diagnostics[0]['code']=='STOPPED'


def test_interaction_does_not_assume_unclassified_get_is_safe(tmp_path,monkeypatch):
    import sys
    monkeypatch.setattr(sys.modules[__name__],'HTML',HTML.replace("p.hidden=!p.hidden;", "fetch('./change-state').catch(()=>null);p.hidden=!p.hidden;"))
    with portal() as (base,received),BrowserSession((base+'/a/',base+'/b/'),tmp_path,threading.Event(),config()) as browser:
        p=browser.collect(base+'/a/home',0)
        control=next(x for x in p.elements if x.name=='Abrir detalhes')
        result=browser.perform(control,0)
        assert result['status']=='inconclusive'
        assert not any('/change-state' in path for _,path in received)


def test_hidden_css_region_has_real_evidence_but_display_none_has_not(tmp_path,monkeypatch):
    import sys
    from PIL import Image
    html=HTML+'<button style="visibility:hidden;width:120px;height:35px">Controle oculto CSS</button>'
    monkeypatch.setattr(sys.modules[__name__],'HTML',html)
    with portal() as (base,_),BrowserSession((base+'/a/',base+'/b/'),tmp_path,threading.Event(),config()) as browser:
        p=browser.collect(base+'/a/home',0)
        hidden=next(x for x in p.elements if x.name=='Controle oculto CSS')
        assert not hidden.visible and hidden.bbox['width']==120
        assert hidden.attrs['evidence_nature']=='region_not_visible_control'
        with Image.open(tmp_path/hidden.attrs['screenshot']) as image:
            assert image.format=='PNG' and image.width==120 and image.height==35
        none=next(x for x in p.elements if x.name=='ÁUDIOS')
        assert not none.attrs.get('screenshot')
        assert any(x['code']=='HIDDEN_REGION_EVIDENCE' for x in p.diagnostics)
