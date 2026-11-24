"""Estruturas equivalentes e diferenças rotuladas, servidas somente em loopback."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


EQUIVALENTES = {'Atendimento', 'Legislação', 'Portaria 12', 'Preferências do portal', 'Resumo'}
INCONCLUSIVOS = {'Consultar', 'Rótulo inválido', 'Acesso sem foco', 'Conteúdo tardio da aba'}
DIFERENCAS = {'ÁUDIOS', 'Rota divergente', 'Alternar opções', 'Bloqueio parcial'}


def pagina_aria(lado, *, escala=0, escala_nativa=False):
    if lado == 'PRD':
        menu = '''<nav aria-label="Serviços públicos">
        <a href="/servicos">Atendimento</a><a href="/legislacao">Legislação</a>
        <a href="/portaria.pdf">Portaria 12</a><a href="/rota-a">Rota divergente</a>
        <a href="/audio.mp3">ÁUDIOS</a></nav>'''
        botoes = '''<button type="button" id="preferencias">Preferências do portal</button>
        <button type="button" aria-disabled="true">Bloqueio parcial</button>
        <button type="button">Consultar</button><button type="button">Consultar</button>
        <button type="button">Acesso sem foco</button><button type="button">Rótulo inválido</button>
        <details><summary>Alternar opções</summary><p>Orientações de uso</p></details>'''
        resumo = '<button id="tab-resumo" role="tab" aria-controls="resumo-a" aria-selected="true">Resumo</button>'
        falha = "document.getElementById('tardio').hidden=false;this.setAttribute('aria-selected','true');setTimeout(()=>document.getElementById('texto-tardio').textContent='Conteúdo tardio da aba',60);"
    else:
        menu = '''<footer><div role="navigation" aria-labelledby="rot-menu" id="nav-alternativo">
        <span id="rot-menu" hidden>Serviços públicos</span><div role="menu">
        <a role="menuitem" href="/servicos">Atendimento</a><a role="menuitem" href="/legislacao">Legislação</a>
        <a role="menuitem" href="/portaria.pdf">Portaria 12</a><a role="menuitem" href="/rota-b">Rota divergente</a>
        </div></div></footer>'''
        botoes = '''<span hidden id="preferir">Preferências</span><span hidden id="portal">do portal</span>
        <div role="button" tabindex="0" id="preferencias" aria-labelledby="preferir portal">⚙</div>
        <button>Bloqueio parcial</button><button>Consultar</button>
        <div role="button">Acesso sem foco</div>
        <div role="button" tabindex="0" aria-labelledby="nao-existe">Rótulo inválido</div>
        <div role="button" tabindex="0" aria-expanded="true" aria-controls="ajuda-b">Alternar opções</div>
        <div role="region" id="ajuda-b"><p>Orientações de uso</p></div>'''
        resumo = '<div id="tab-resumo" role="tab" tabindex="0" aria-controls="resumo-b" aria-selected="true">Resumo</div>'
        falha = ''
    adicionais = ''.join(f'<button type="button">Preferência local {i:04d}</button>' if lado == 'PRD' or escala_nativa
                         else f'<div role="button" tabindex="0" aria-label="Preferência local {i:04d}"></div>'
                         for i in range(escala))
    return f'''<!doctype html><html lang="pt-BR"><head><title>Portal de teste ARIA</title>
    <style>[role=button] {{ min-height: 18px }}</style></head><body>
    {menu}<main><section aria-label="Ferramentas"><h2>Ferramentas</h2>
    {botoes}{adicionais}
    <button aria-hidden="true">Somente no DOM</button><div inert><button>Controle inerte</button></div>
    <button style="opacity:0">Controle transparente</button>
    <dialog><button>Ação do diálogo fechado</button></dialog>
    <button hidden aria-label="Versão responsiva inativa">Atendimento</button>
    <div aria-disabled="true"><button aria-expanded="false" aria-controls="nunca"
        onclick="window.escrita=true">Abertura desabilitada</button></div><div hidden id="nunca">Reservado</div>
    <button aria-labelledby="perigo" aria-expanded="false" aria-controls="nunca"
        onclick="window.escrita=true">⚙</button><span hidden id="perigo">Excluir cadastro</span>
    <form><button role="tab" type="submit" onclick="window.escrita=true">Enviar</button></form>
    </section><div role="tablist" aria-label="Informações">
    {resumo}
    <button role="tab" aria-controls="tardio" aria-selected="false" onclick="{falha}">Detalhes tardios</button>
    </div><div role="tabpanel" id="resumo-{'a' if lado == 'PRD' else 'b'}"><p>Resumo do portal</p></div>
    <div hidden role="tabpanel" id="tardio"><p id="texto-tardio">Texto pendente</p></div>
    </main></body></html>'''


@contextmanager
def portais_aria():
    servidores, processos = [], []
    requisicoes = []

    def handler(lado):
        class Portal(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                requisicoes.append((lado, self.command, self.path))
                if self.path == '/':
                    data = pagina_aria(lado).encode()
                    tipo = 'text/html; charset=utf-8'
                elif self.path.endswith('.pdf'):
                    data = b'%PDF-1.4\n%%EOF\n'
                    tipo = 'application/pdf'
                else:
                    data = '<title>Página interna</title><p>Informações públicas do portal.</p>'.encode()
                    tipo = 'text/html; charset=utf-8'
                self.send_response(200)
                self.send_header('Content-Type', tipo)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                if self.command != 'HEAD':
                    try:
                        self.wfile.write(data)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

            def do_POST(self):
                requisicoes.append((lado, self.command, self.path))
                self.send_error(405)

        return Portal

    try:
        for lado in ('PRD', 'DES'):
            servidor = ThreadingHTTPServer(('127.0.0.1', 0), handler(lado))
            processo = threading.Thread(target=servidor.serve_forever, daemon=True)
            servidores.append(servidor)
            processos.append(processo)
            processo.start()
        yield [f'http://127.0.0.1:{s.server_port}/' for s in servidores], requisicoes
    finally:
        for servidor in servidores:
            servidor.shutdown()
            servidor.server_close()
        for processo in processos:
            processo.join()
