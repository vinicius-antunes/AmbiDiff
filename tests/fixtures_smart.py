"""Dois portais sintéticos locais, sem conteúdo ou URLs corporativas."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


@contextmanager
def portais(artigos=8, estrutura_diferente=False):
    servidores=[];threads=[];requisicoes=[]
    for ambiente in ('PRD','DES'):
        def handler(env):
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_HEAD(self):
                    requisicoes.append((env,'HEAD',self.path))
                    self.send_response(200);self.send_header('Content-Type','application/pdf')
                    self.send_header('Content-Disposition','attachment; filename="manual-rede.pdf"')
                    self.send_header('Cache-Control','max-age=60');self.send_header('Content-Length','90000000');self.end_headers()
                def do_GET(self):
                    requisicoes.append((env,'GET',self.path))
                    if self.path=='/manual.pdf':
                        self.send_response(500);self.end_headers();return
                    nav='<nav><a href="/">Início</a><a href="/manual.pdf">Manual rede</a></nav>'
                    if self.path=='/':
                        cards=''.join('<article class="card"><h3>Publicação '+str(n)+'</h3><a href="/w/'+str(n)+'">Ler publicação</a></article>' for n in range(artigos))
                        corpo='<section><h2>Notícias</h2>'+cards+'</section>'
                    else:
                        n=self.path.rsplit('/',1)[-1]
                        extra='<a href="/ajuda">Ajuda</a>' if estrutura_diferente and env=='DES' else ''
                        corpo='<article><h1>Notícia '+env+' '+n+'</h1><time datetime="2026-10-01">'+('01/10/2026' if env=='DES' else '21/10/2026')+'</time><p>Conteúdo editorial '+env+'</p>'+extra+'</article>'
                    html='<html><head><title>Portal sintético</title><link rel="icon" href="data:,"></head><body>'+nav+'<main>'+corpo+'</main></body></html>'
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
                    self.wfile.write(html.encode())
            return Handler
        servidor=ThreadingHTTPServer(('127.0.0.1',0),handler(ambiente))
        thread=threading.Thread(target=servidor.serve_forever,daemon=True);thread.start()
        servidores.append(servidor);threads.append(thread)
    try:
        yield [f'http://127.0.0.1:{s.server_port}/' for s in servidores],requisicoes
    finally:
        for s in servidores:s.shutdown();s.server_close()
        for t in threads:t.join()
