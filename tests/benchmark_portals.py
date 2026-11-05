"""Portais inteiramente fictícios usados igualmente pelo legado e pelo Next.

Nenhuma rota externa é servida ou consultada pelo harness. Os domínios .invalid
são apenas referências de comparação, bloqueadas pelos motores.
"""
from contextlib import contextmanager
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread, Lock
from urllib.parse import urlsplit

VIEWPORT = {'width': 1366, 'height': 850}
TRUTH = [
    {'id':'audio','nature':'estrutural','element':'ÁUDIOS','description':'opção somente no ambiente A'},
    {'id':'agenda','nature':'estrutural','element':'Agendamento','description':'opção somente no ambiente B'},
    {'id':'redirect','nature':'redirecionamento','element':'Consulta Pública','path':'/consulta','description':'mesma referência termina em rotas diferentes'},
    {'id':'document','nature':'documento','element':'Regulamento','description':'destino documental diferente'},
    {'id':'tab','nature':'funcional','element':'Detalhes do serviço','description':'aba muda o painel somente em A'},
    {'id':'color','nature':'visual','element':'Acessar serviço','description':'cor do botão é azul em A e vermelha em B'},
    {'id':'hidden','nature':'visual','element':'Atendimento oculto','description':'controle invisível por CSS em B'},
    {'id':'overlay','nature':'visual','element':'Painel de atendimento','description':'controle encoberto em B'},
]
NEGATIVES = [
    {'id':'moved','element':'Ouvidoria','reason':'mesmo controle e destino em posições HTML distintas'},
    {'id':'external_equal','element':'Portal externo','reason':'referência externa idêntica; não visitar'},
    {'id':'editorial','element':'Notícia de teste','reason':'datas editoriais diferentes não comprovam defeito'},
]


class PortalPair:
    def __init__(self, news=8):
        self.news=news;self.servers=[];self.threads=[];self.lock=Lock()
        self.counters=Counter();self.requests=[]

    def record(self,side,method,path,kind):
        with self.lock:
            self.counters[method]+=1;self.counters[kind]+=1
            self.requests.append({'side':side,'method':method,'path':path,'kind':kind})

    def reset(self):
        with self.lock:self.counters.clear();self.requests.clear()

    def snapshot(self):
        with self.lock:return {'counts':dict(self.counters),'requests':list(self.requests)}

    def document(self,side,path):
        if path=='/':
            missing='<a href="/audios">ÁUDIOS</a>' if side==0 else '<a href="/agendamento">Agendamento</a>'
            moved='<a href="/ouvidoria">Ouvidoria</a>'
            news=''.join(f'<a href="/noticias/{i}">Notícia de teste {i}</a>' for i in range(self.news))
            regulation='regulamento' if side==0 else 'regulamento-antigo'
            color='#1649b8' if side==0 else '#bc1931'
            hidden='' if side==0 else 'visibility:hidden'
            # Page title/labels stable; only the manifest-listed properties differ.
            return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Portal fictício de serviços</title>
<style>body{{font:16px Arial;margin:20px}}nav a{{display:inline-block;margin:8px}}button,a.cta{{padding:12px;display:inline-block}}
.visual{{height:75px}}.cover{{position:relative;width:280px;height:65px}}.veil{{position:absolute;inset:0;background:#ddd;z-index:5}}
[hidden]{{display:none}}.cta{{color:white;background:{color}}}</style></head><body>
<header><h1>Portal fictício de serviços</h1><nav aria-label="Menu principal"><a href="/">Início</a>
<a href="/consulta">Consulta Pública</a><a href="/servico">Serviço ao cidadão</a>{missing}
<a href="/documents/d/portal/{regulation}">Regulamento</a><a href="/noticias">Notícias</a>
<a href="https://reference.invalid/servico">Portal externo</a>
{moved if side==0 else ''}</nav></header><main><section aria-label="Serviços"><h2>Serviços</h2>
<div role="tablist"><button type="button" role="tab" aria-selected="false" aria-controls="detalhes" id="aba"
>Detalhes do serviço</button></div>
<div role="tabpanel" id="detalhes" hidden>Documentação para atendimento.</div>
<div class="visual"><a class="cta" href="/servico">Acessar serviço</a></div>
<div class="visual"><button type="button" aria-controls="aviso" style="{hidden}">Atendimento oculto</button></div>
<div id="aviso" hidden>Aviso informativo</div>
<div class="cover"><button type="button" aria-controls="painel">Painel de atendimento</button>{'<div class="veil" aria-hidden="true"></div>' if side else ''}</div>
<div id="painel" hidden>Horário de atendimento</div>
</section><section aria-label="Notícias"><h2>Notícias</h2>{news}</section></main>
<footer>{moved if side==1 else ''}<a href="/contato">Contato</a></footer>
{'<script>document.getElementById("aba").addEventListener("click",function(){document.getElementById("detalhes").hidden=false;this.setAttribute("aria-selected","true")});</script>' if side==0 else ''}</body></html>'''
        if path.startswith('/noticias/'):
            i=int(path.rsplit('/',1)[-1])
            day='2026-11-01' if side==0 else '2026-10-01'
            return f'''<!doctype html><html lang="pt-BR"><title>Notícia de teste {i}</title><body><header><nav><a href="/">Início</a><a href="/servico">Serviço ao cidadão</a></nav></header><main><article><h1>Notícia de teste {i}</h1><time datetime="{day}">{day}</time><p>Conteúdo editorial fictício.</p><a href="/noticias/{i+1 if i+1<self.news else 0}">Próximo</a></article></main></body></html>'''
        if path=='/noticias':
            return '<!doctype html><html><title>Notícias</title><body><nav><a href="/">Início</a></nav><main><h1>Notícias</h1><a href="/noticias/0">Notícia de teste 0</a></main></body></html>'
        title={'/resultado':'Resultado da consulta','/outro':'Página diversa','/servico':'Serviço ao cidadão','/audios':'ÁUDIOS','/agendamento':'Agendamento','/ouvidoria':'Ouvidoria','/contato':'Contato'}.get(path,'Página não encontrada')
        return f'<!doctype html><html><title>{title}</title><body><nav><a href="/">Início</a><a href="/servico">Serviço ao cidadão</a></nav><main><h1>{title}</h1><p>Informação institucional fictícia.</p></main></body></html>'

    def start(self):
        owner=self
        def handler(side):
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*_):pass
                def do_HEAD(self):self.respond(True)
                def do_GET(self):self.respond(False)
                def do_POST(self):owner.record(side,self.command,self.path,'unsafe');self.send_error(405)
                do_PUT=do_POST;do_DELETE=do_POST;do_PATCH=do_POST
                def respond(self,head):
                    path=urlsplit(self.path).path
                    if path.startswith('/documents/'):
                        owner.record(side,self.command,path,'document_requests');content=b'%PDF-1.4\n% local fixture\n'
                        self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Disposition','attachment; filename="regulamento.pdf"');self.send_header('Content-Length',str(len(content)));self.end_headers()
                        if not head:self.wfile.write(content)
                        return
                    if path=='/consulta':
                        owner.record(side,self.command,path,'redirect_requests');self.send_response(302);self.send_header('Location','/resultado' if side==0 else '/outro');self.end_headers();return
                    if any(x in path for x in ('delete','logout','admin')):
                        owner.record(side,self.command,path,'unsafe');self.send_error(403);return
                    if path in ('/favicon.ico',):
                        self.send_error(404);return
                    owner.record(side,self.command,path,'html_requests' if not head else 'html_head_requests')
                    content=owner.document(side,path).encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(content)));self.end_headers()
                    if not head:
                        try:self.wfile.write(content)
                        except (ConnectionError,BrokenPipeError):pass
            return Handler
        for side in range(2):
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(side));server.daemon_threads=True
            thread=Thread(target=server.serve_forever,daemon=True);thread.start();self.servers.append(server);self.threads.append(thread)
        self.roots=tuple(f'http://127.0.0.1:{s.server_port}/' for s in self.servers)
        return self

    def close(self):
        for server in self.servers:server.shutdown();server.server_close()
        for thread in self.threads:thread.join(timeout=2)

    def __enter__(self):return self.start()
    def __exit__(self,*_):self.close()
