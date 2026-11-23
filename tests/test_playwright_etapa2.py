"""Cobertura de prontidão e evidências com Chromium e servidores loopback."""
from base64 import b64decode, b64encode
from contextlib import contextmanager, ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import sleep
import unittest
from unittest.mock import patch

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from ambidiff.adaptive import preparar
from ambidiff.evidencias import aguardar_visual
from ambidiff.paired import _salvar_evidencias
from ambidiff.smart import Metricas
from test_smart import navegador


@contextmanager
def portais(html_a, html_b, *, imagem_lenta=False):
    def handler(html):
        class Portal(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                if self.path == '/imagem.gif' and imagem_lenta:
                    sleep(0.25)
                    mime = 'image/gif'
                    corpo = b64decode('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==')
                else:
                    mime = 'text/html; charset=utf-8'
                    pagina = '<!doctype html><meta charset="utf-8"><link rel="icon" href="data:,">' + html
                    corpo = pagina.encode()
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

        return Portal

    with ExitStack() as stack:
        urls = []
        for html in (html_a, html_b):
            servidor = stack.enter_context(ThreadingHTTPServer(('127.0.0.1', 0), handler(html)))
            fio = Thread(target=servidor.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
            fio.start()
            stack.callback(fio.join)
            stack.callback(servidor.shutdown)
            urls.append(f'http://127.0.0.1:{servidor.server_port}/')
        yield urls


def divergencia(bases, numero=1, seletor='#alvo'):
    return dict(id=f'DIV-{numero:04}', presente_em='PRD', nao_identificado_em='DES',
                url_presente=bases[0], url_comparada=bases[1], seletor=seletor)


class PlaywrightEtapa2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.addClassCleanup(cls.pw.stop)
        cls.browser = navegador(cls.pw)
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        td = TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.raiz = Path(td.name)
        self.metricas = Metricas()
        self.parar = Event()
        self.falhas = []

    def capturar(self, linhas):
        _salvar_evidencias(self.browser, linhas, self.raiz / 'evidencias_fixture',
                           self.parar, lambda _: None, metricas=self.metricas, diagnosticos=self.falhas)

    def verificar_png(self, caminho, destacado):
        conteudo = (self.raiz / caminho).read_bytes()
        self.assertTrue(conteudo.startswith(b'\x89PNG\r\n\x1a\n'))
        page = self.browser.new_page()
        try:
            resultado = page.evaluate('''async src => {
                const img = new Image();
                img.src = src;
                await img.decode();
                const canvas = document.createElement('canvas');
                canvas.width = img.width;
                canvas.height = img.height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                const pixels = ctx.getImageData(0, 0, img.width, img.height).data;
                let borda = 0;
                for (let i = 0; i < pixels.length; i += 4)
                    if (pixels[i] === 244 && pixels[i+1] === 166 && pixels[i+2] === 70) borda++;
                return [img.width, img.height, borda];
            }''', 'data:image/png;base64,' + b64encode(conteudo).decode('ascii'))
        finally:
            page.close()
        self.assertEqual(resultado[:2], [1366, 850])
        self.assertEqual(resultado[2] > 0, destacado)

    def test_reuso_respeita_seletor_contexto_e_mutacao_da_pagina(self):
        html = '<style>body{margin:25px}</style><p id="alvo">Primeiro</p><p id="outro">Segundo</p>'
        with portais(html, '<main>Ambiente correspondente</main>') as bases:
            capturas = []
            screenshot = Page.screenshot

            def observar(page, **kwargs):
                capturas.append(page)
                return screenshot(page, **kwargs)

            linhas = [divergencia(bases), divergencia(bases, 2), divergencia(bases, 3, '#outro')]
            with patch.object(Page, 'screenshot', observar):
                self.capturar(linhas)
            self.assertEqual(linhas[0]['evidencias'], linhas[1]['evidencias'])
            self.assertNotEqual(linhas[0]['evidencias']['PRD'], linhas[2]['evidencias']['PRD'])
            self.assertEqual(len({page.context for page in capturas}), 2)
            self.assertEqual(self.metricas.contagens['navegacoes_evidencias'], 2)
            self.assertEqual(self.metricas.contagens['capturas_reutilizadas'], 2)
            self.verificar_png(linhas[0]['evidencias']['PRD'], destacado=True)
            self.verificar_png(linhas[0]['evidencias']['DES'], destacado=False)

            def mudar(page, **kwargs):
                resultado = screenshot(page, **kwargs)
                if page.url == bases[0] and kwargs['path'].endswith('0004_PRD.png'):
                    alvo.append(page)
                if page.url == bases[1] and kwargs['path'].endswith('0004_DES.png'):
                    alvo[0].evaluate("document.body.style.background = 'red'")
                return resultado

            alvo = []
            novas = [divergencia(bases, 4), divergencia(bases, 5)]
            with patch.object(Page, 'screenshot', mudar):
                self.capturar(novas)
            self.assertNotEqual(novas[0]['evidencias']['PRD'], novas[1]['evidencias']['PRD'])
            self.assertEqual(novas[0]['evidencias']['DES'], novas[1]['evidencias']['DES'])
            self.assertFalse(self.falhas)

    def test_captura_aguarda_alvo_tardio_no_ambiente_de_origem(self):
        html = '''<style>body{margin:25px}</style><main>Conteúdo inicial</main>
        <script>setTimeout(() => document.querySelector('main').insertAdjacentHTML(
            'beforeend', '<p id="alvo">ÁUDIOS</p>'), 650)</script>'''
        with portais(html, '<main>Conteúdo correspondente</main>') as bases:
            linha = divergencia(bases)
            self.capturar([linha])
        self.assertIn('Elemento localizado', linha['marcacoes']['PRD'])
        self.assertIn('Área da página', linha['marcacoes']['DES'])
        self.verificar_png(linha['evidencias']['PRD'], destacado=True)
        self.assertFalse(self.falhas)

    def test_captura_aguarda_imagem_lazy_apos_enquadrar_o_alvo(self):
        html = '<div style="height:3500px"></div><img id="alvo" loading="lazy" src="/imagem.gif" width="100" height="100">'
        screenshot = Page.screenshot
        larguras = []

        def observar(page, **kwargs):
            if kwargs['path'].endswith('_PRD.png'):
                larguras.append(page.locator('#alvo').evaluate('img => img.naturalWidth'))
            return screenshot(page, **kwargs)

        with portais(html, '<main>DES</main>', imagem_lenta=True) as bases, patch.object(Page, 'screenshot', observar):
            linha = divergencia(bases)
            self.capturar([linha])
        self.assertEqual(larguras, [1])
        self.assertIn('Elemento localizado', linha['marcacoes']['PRD'])
        self.verificar_png(linha['evidencias']['PRD'], destacado=True)
        self.assertFalse(self.falhas)

    def test_limite_visual_e_preparacao_com_carregamento_tardio(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.set_content('<main aria-busy="true"><p>Carregando</p></main>')
        self.assertFalse(aguardar_visual(page, self.parar, limite_ms=120)['pronto'])
        page.evaluate('''() => setTimeout(() => {
            const main = document.querySelector('main');
            main.removeAttribute('aria-busy');
            main.innerHTML = '<p>Regra divulgada mais tarde</p>';
        }, 450)''')
        resumo = preparar(page, lambda _: None, parar=self.parar)
        self.assertTrue(resumo['estavel'])
        self.assertIn('Regra divulgada mais tarde', page.locator('main').inner_text())

    def test_timeout_da_captura_preserva_o_outro_ambiente_e_continua(self):
        screenshot = Page.screenshot

        def falhar(page, **kwargs):
            if kwargs['path'].endswith('0001_DES.png'):
                raise PlaywrightTimeout('Timeout da captura sintética')
            return screenshot(page, **kwargs)

        with portais('<main>PRD</main>', '<main>DES</main>') as bases, patch.object(Page, 'screenshot', falhar):
            linhas = [divergencia(bases), divergencia(bases, 2)]
            self.capturar(linhas)
        self.assertEqual(set(linhas[0]['evidencias']), {'PRD'})
        self.assertEqual(set(linhas[1]['evidencias']), {'PRD', 'DES'})
        self.assertEqual([(f['tipo_erro'], f['etapa']) for f in self.falhas], [('TIMEOUT', 'evidencias')])

    def test_interrupcao_durante_captura_preserva_imagem_concluida(self):
        screenshot = Page.screenshot

        def interromper(page, **kwargs):
            imagem = screenshot(page, **kwargs)
            self.parar.set()
            return imagem

        with portais('<main>PRD</main>', '<main>DES</main>') as bases, patch.object(Page, 'screenshot', interromper):
            linhas = [divergencia(bases), divergencia(bases, 2)]
            self.capturar(linhas)
        self.assertEqual(set(linhas[0]['evidencias']), {'PRD'})
        self.assertNotIn('evidencias', linhas[1])
        self.assertEqual(self.metricas.contagens['capturas_geradas'], 1)
        self.assertFalse(self.falhas)

    def test_contexto_perdido_e_recriado_sem_descartar_captura(self):
        screenshot = Page.screenshot

        def fechar(page, **kwargs):
            if kwargs['path'].endswith('0001_DES.png'):
                page.context.close()
            return screenshot(page, **kwargs)

        with portais('<main>PRD</main>', '<main>DES</main>') as bases, patch.object(Page, 'screenshot', fechar):
            linhas = [divergencia(bases), divergencia(bases, 2)]
            self.capturar(linhas)
        self.assertEqual(set(linhas[0]['evidencias']), {'PRD'})
        self.assertEqual(set(linhas[1]['evidencias']), {'PRD', 'DES'})
        self.assertEqual(self.metricas.contagens['capturas_reutilizadas'], 1)
        self.assertEqual([f['tipo_erro'] for f in self.falhas], ['RECURSO_ENCERRADO'])
