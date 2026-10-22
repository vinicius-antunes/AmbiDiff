"""Portais somente loopback: diferenças institucionais, widget, lazy e abas."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading

@contextmanager
def portais_perf(paginas=3,dinamico=False,redirecionar_lab=False):
    servers=[];threads=[];requests=[]
    for env in ('PRD','LAB'):
        def handler(ambiente):
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    requests.append((ambiente,self.path))
                    if redirecionar_lab and ambiente=='LAB' and self.path=='/':
                        self.send_response(302);self.send_header('Location','/login');self.end_headers();return
                    if self.path=='/falha':self.send_response(503);self.end_headers();return
                    nav='<nav>'+''.join(f'<a href="/pagina/{n}">Área {n}</a>' for n in range(1,paginas))+'</nav>'
                    textos=(['Atendimento fiscal suspenso nesta unidade','Prazos para declaração tributária prorrogados','Orientação obrigatória aos contribuintes','Alíquota aplicada conforme resolução vigente','Regras para inscrição de prestadores','Requerimentos devem conter assinatura','Serviços disponíveis mediante agendamento'] if ambiente=='PRD' else
                            ['Cadastro geral em manutenção programada','Balancetes encerrados na competência atual','Utilize o canal de ouvidoria permanente','A entrega de formulários ocorrerá no anexo','Autorizações emitidas após conferência','Responsáveis informados no protocolo','Resultados publicados na sede administrativa'])
                    main='<section id="institucional"><h1>Atendimento</h1>'+''.join('<p>'+t+'</p>' for t in textos)+'</section>'
                    if ambiente=='PRD':main+='<aside class="widget" id="auxiliar"><img src="data:image/svg+xml,%3Csvg xmlns=\"http://www.w3.org/2000/svg\"/%3E" alt="Contato ilustrado"><button type="button">Canal auxiliar</button></aside>'
                    if dinamico:
                        main+='''<section id="painel"><button role="tab" onclick="document.getElementById('dados').textContent='Informação da aba'">Painel</button><p id="dados">Resumo</p></section>
                        <div style="height:1400px"></div><div id="tardio"></div><script>
                        setTimeout(()=>document.getElementById('tardio').innerHTML='<p>Publicação carregada depois</p>',600);
                        addEventListener('scroll',()=>{if(scrollY>500&&!document.getElementById('rolagem')){
                          const p=document.createElement('p');p.id='rolagem';p.textContent='Informação ativada por rolagem';document.body.append(p);}});
                        </script>'''
                    html='<html><head><title>Portal local de teste</title><link rel="icon" href="data:,"></head><body>'+nav+'<main>'+main+'</main></body></html>'
                    body=html.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            return Handler
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(env));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();servers.append(server);threads.append(thread)
    try:yield [f'http://127.0.0.1:{s.server_port}/' for s in servers],requests
    finally:
        for s in servers:s.shutdown();s.server_close()
        for t in threads:t.join()
