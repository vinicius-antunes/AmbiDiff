"""Testes locais do lote assíncrono e do fluxo de coleta que o consome."""
import asyncio
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock, Thread
from time import sleep
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from playwright.async_api import TimeoutError as PlaywrightTimeout

from ambidiff import checkpoints, core, navigation_async
from ambidiff.diagnostics import montar_diagnostico
from ambidiff.paired import executar_pareado
from ambidiff.smart import Metricas
from fixtures_perf import portais_perf


@contextmanager
def portais(responder):
    """Dois hosts loopback com portas independentes e servidor de teste por lado."""
    def handler(lado):
        class Portal(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                status, headers, html = responder(lado, self.path, self.headers)
                corpo = ('<!doctype html><meta charset="utf-8"><link rel="icon" href="data:,">' + html).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(corpo)))
                for chave, valor in headers.items():
                    self.send_header(chave, valor)
                self.end_headers()
                try:
                    self.wfile.write(corpo)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Timeout e interrupção fecham a conexão da fixture.

        return Portal

    with ExitStack() as stack:
        urls = []
        for lado in (0, 1):
            servidor = stack.enter_context(ThreadingHTTPServer(('127.0.0.1', 0), handler(lado)))
            fio = Thread(target=servidor.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
            fio.start()
            stack.callback(fio.join)
            stack.callback(servidor.shutdown)
            urls.append(f'http://127.0.0.1:{servidor.server_port}/')
        yield urls


def varrer(bases, *, async_=True, parar=None, **kwargs):
    progresso = kwargs.pop('progresso', lambda _: None)
    return executar_pareado(*bases, 'PRD', 'DES', parar or Event(), lambda _: None, progresso,
                            navegacao_assincrona=async_, varredura_inteligente=True, **kwargs)


class MotorAsyncTests(unittest.TestCase):
    def test_duas_navegacoes_simultaneas_contextos_isolados_e_fila_serial(self):
        barreiras = {rota: Barrier(2, timeout=5) for rota in ('/', '/servico', '/arquivo')}
        pedidos = []
        cookies = {}

        def responder(lado, rota, headers):
            cookies[lado] = headers.get('Cookie', '')
            pedidos.append(('iniciou', rota, lado))
            barreiras[rota].wait()
            # Um lado conclui primeiro, mas isso não pode liberar o próximo par.
            sleep(0.18 if lado else 0.04)
            pedidos.append(('respondeu', rota, lado))
            html = '<main><p>Página institucional</p></main>'
            if rota == '/':
                html += '<nav><a href="/servico">Serviço</a><a href="/arquivo">Acervo</a></nav>'
            return 200, {}, html

        with portais(responder) as bases:
            def preparar(a, b):
                a.add_cookies([{'name': 'sessao', 'value': 'fixture', 'url': bases[0]}])
                self.assertFalse(b.cookies())
            r = varrer(bases, _preparar_contextos=preparar)
        self.assertEqual(cookies, {0: 'sessao=fixture', 1: ''})
        self.assertEqual(r['andamento']['pares_comparados'], 3)
        self.assertEqual([p['par'][0] for p in r['estados_pares']],
                         [bases[0], bases[0]+'servico', bases[0]+'arquivo'])
        for i, rota in enumerate(('/', '/servico', '/arquivo')):
            inicio = i*4
            self.assertCountEqual(pedidos[inicio:inicio+2], [('iniciou', rota, 0), ('iniciou', rota, 1)])
            self.assertCountEqual(pedidos[inicio+2:inicio+4], [('respondeu', rota, 0), ('respondeu', rota, 1)])
        d = montar_diagnostico(r)['desempenho']
        self.assertEqual(d['contagens']['visitas_html_tentadas'], 6)
        self.assertGreater(sum(d['navegacao_operacoes_segundos'].values()), d['etapas_coleta_segundos']['navegacao_html'])

    def test_equivalencia_com_conteudo_tardio_audios_e_evidencias(self):
        def responder(lado, rota, _):
            html = '<main><h1>Atendimento</h1><p>Serviços à comunidade</p></main>'
            tardio = '<p>Regra publicada tardiamente.</p>'
            if lado:
                tardio += '<button id="audios">ÁUDIOS</button>'
            html += f"""<script>setTimeout(() => document.querySelector('main').insertAdjacentHTML(
                'beforeend', {tardio!r}), 600)</script>"""
            return 200, {}, html

        with portais(responder) as bases, TemporaryDirectory() as antes, TemporaryDirectory() as depois:
            sync = varrer(bases, async_=False, evidencias_dir=Path(antes)/'evidencias')
            async_ = varrer(bases, evidencias_dir=Path(depois)/'evidencias')
            for campo in ('divergencias', 'estados_pares', 'fila_pendente', 'filtro_urls', 'falhas'):
                self.assertEqual(sync[campo], async_[campo], campo)
            audio = next(d for d in async_['divergencias'] if d['elemento'] == 'ÁUDIOS')
            self.assertEqual(audio['presente_em'], 'DES')
            self.assertEqual(set(audio['evidencias']), {'PRD', 'DES'})
            for caminho in audio['evidencias'].values():
                original = (Path(antes)/caminho).read_bytes()
                self.assertTrue(original.startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertEqual(original, (Path(depois)/caminho).read_bytes())
            self.assertFalse(any('Regra publicada' in d['elemento'] for d in async_['divergencias']))

    def test_timeout_unilateral_e_falha_http_nao_geram_divergencia(self):
        def responder(lado, rota, _):
            if rota == '/lenta' and lado == 1:
                sleep(0.9)
            if rota == '/falha' and lado == 1:
                return 503, {}, '<p>Indisponível</p>'
            html = '<main><p>Atendimento local</p></main>'
            if rota == '/':
                html += '<nav><a href="/lenta">Área lenta</a><a href="/falha">Área com falha</a></nav>'
            return 200, {}, html

        with portais(responder) as bases, patch.object(core, 'TEMPO_PAGINA_MS', 350):
            r = varrer(bases)
        self.assertEqual(r['andamento']['pares_comparados'], 1)
        self.assertEqual(r['andamento']['pares_com_falha'], 2)
        self.assertEqual({(f['ambiente'], f['tipo_erro']) for f in r['falhas']}, {('DES', 'TIMEOUT'), ('DES', 'HTTP')})
        self.assertFalse(r['divergencias'])

    def test_redirecionamentos_conservam_mesmos_destinos_e_estados(self):
        def responder(lado, rota, _):
            html = '<main><p>Atendimento institucional</p></main>'
            if rota == '/':
                return 200, {}, html+'<nav><a href="/atalho">Atalho</a><a href="/igual">Acesso igual</a></nav>'
            if rota == '/atalho':
                return 302, {'Location': '/novo' if lado else '/outra'}, ''
            if rota == '/igual':
                return 302, {'Location': '/mesma'}, ''
            return 200, {}, html

        with portais(responder) as bases:
            sync = varrer(bases, async_=False)
            novo = varrer(bases)
        self.assertEqual(sync['estados_pares'], novo['estados_pares'])
        self.assertEqual(sync['divergencias'], novo['divergencias'])
        self.assertIn('redirecionamento', {p['estado'] for p in novo['estados_pares']})
        self.assertEqual(novo['andamento']['pares_comparados'], 2)

    def test_interrupcao_com_as_duas_navegacoes_pendentes(self):
        parar = Event()
        snapshots = []
        aguardando = []
        lock = Lock()
        liberar = Event()

        def responder(lado, _, __):
            with lock:
                aguardando.append(lado)
                if len(aguardando) == 2:
                    parar.set()
            liberar.wait(timeout=6)
            return 200, {}, '<p>Resposta concluída após a parada</p>'

        with portais(responder) as bases:
            try:
                r = varrer(bases, parar=parar, checkpoint=lambda snap: snapshots.append(deepcopy(snap)))
            finally:
                liberar.set()
        self.assertCountEqual(aguardando, [0, 1])
        self.assertEqual(r['estado_execucao'], 'interrompido')
        self.assertFalse(r['estados_pares'])
        self.assertFalse(r['falhas'])
        snap = checkpoints.validar(snapshots[-1]['retomada'], tuple(bases))
        self.assertEqual([p[:2] for p in snap['fila']], [bases])
        self.assertFalse(snap['visitados'])
        self.assertEqual(r['metricas']['contagens']['operacoes_navegacao'], 2)

    def test_recupera_browser_fechado_com_dois_lados_em_navegacao(self):
        navegar = navigation_async._navegar
        fechou = False

        async def fechar(page, url, base, ambiente, *args):
            nonlocal fechou
            if not fechou and ambiente == 'PRD' and url.endswith('/pagina/1'):
                fechou = True
                await page.context.browser.close()
            return await navegar(page, url, base, ambiente, *args)

        with portais_perf(3) as (bases, _), patch.object(navigation_async, '_navegar', fechar):
            r = varrer(bases)
        self.assertTrue(fechou)
        self.assertEqual(r['andamento']['pares_comparados'], 3)
        self.assertEqual(r['andamento']['pares_pendentes'], 0)
        self.assertEqual(r['metricas']['contagens']['recuperacoes_navegador'], 1)
        self.assertEqual([f['tipo_erro'] for f in r['falhas']], ['RECURSO_ENCERRADO'])
        self.assertEqual(len({tuple(p['par']) for p in r['estados_pares']}), 3)

    def test_reabre_paginas_quando_uma_falha_e_a_irma_e_cancelada(self):
        navegar = navigation_async._navegar
        originais = {}
        recuperadas = {}
        peer_iniciou = None
        fechou = False

        async def fechar(page, url, base, ambiente, *args):
            nonlocal fechou, peer_iniciou
            if url == base and ambiente not in originais:
                originais[ambiente] = page
                if peer_iniciou is None:
                    peer_iniciou = asyncio.Event()
                if ambiente == 'DES':
                    peer_iniciou.set()
                    await asyncio.Future()  # Só termina com o cancelamento.
                await peer_iniciou.wait()
                await page.close()
                fechou = True
            elif url == base:
                recuperadas[ambiente] = page
            return await navegar(page, url, base, ambiente, *args)

        with portais_perf(1) as (bases, _), patch.object(navigation_async, '_navegar', fechar):
            r = varrer(bases)
        self.assertTrue(fechou)
        self.assertEqual(r['andamento']['pares_comparados'], 1)
        for nome in ('PRD', 'DES'):
            self.assertIsNot(recuperadas[nome], originais[nome])
            self.assertTrue(originais[nome].is_closed())

    def test_retomada_de_checkpoint_sincrono_anterior_as_metricas_por_lado(self):
        parar = Event()
        snapshots = []
        with portais_perf(3) as (bases, _):
            parcial = varrer(bases, async_=False, parar=parar, progresso=lambda _: parar.set(),
                             checkpoint=lambda snap: snapshots.append(deepcopy(snap)))
            estado = checkpoints.validar(snapshots[-1]['retomada'], tuple(bases))
            for k in ('navegacao_lado_0_segundos', 'navegacao_lado_1_segundos'):
                estado['metricas']['tempos_segundos'].pop(k, None)
            retomado = varrer(bases, retomada=checkpoints.empacotar(estado))
            inteiro = varrer(bases, async_=False)
        self.assertEqual(parcial['andamento']['pares_comparados'], 1)
        self.assertEqual(retomado['andamento']['pares_comparados'], 3)
        self.assertEqual(retomado['divergencias'], inteiro['divergencias'])
        self.assertEqual(retomado['estados_pares'], inteiro['estados_pares'])
        self.assertFalse(retomado['fila_pendente'])

    def test_regra_somente_leitura_bloqueia_post_no_modo_assincrono(self):
        def responder(_, __, ___):
            return 200, {}, '''<main><p>Página local</p></main><script>
                fetch('/alterar', {method: 'POST', body: 'fixture'}).catch(()=>{});
                </script>'''

        with portais(responder) as bases:
            r = varrer(bases)
        self.assertEqual(r['andamento']['pares_comparados'], 1)
        bloqueios = r['bloqueios_seguranca']
        self.assertEqual([(grupo['metodo'], grupo['quantidade']) for grupo in bloqueios], [('POST', 2)])


class NavegacaoAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_recupera_timeout_por_commit_e_err_aborted_pelo_dom(self):
        base = 'http://127.0.0.1:9000/'
        resposta = object()
        page = SimpleNamespace(url=base, goto=AsyncMock(side_effect=[PlaywrightTimeout('Timeout'), resposta]),
                               evaluate=AsyncMock(return_value={'url': base, 'n': 10}))
        self.assertIs(await navigation_async._abrir(page, base, Event()), resposta)
        self.assertEqual([call.kwargs['wait_until'] for call in page.goto.call_args_list], ['domcontentloaded','commit'])

        async def abortar(*args, **kwargs):
            page.url = base+'destino'
            raise RuntimeError('net::ERR_ABORTED')

        page.goto = AsyncMock(side_effect=abortar)
        page.evaluate = AsyncMock(return_value=True)
        page.wait_for_load_state = AsyncMock()
        page.is_closed = lambda: False
        metricas = Metricas()
        eventos = []
        self.assertIsNone(await navigation_async._navegar(page, base, base, 'PRD', Event(), metricas, eventos))
        self.assertTrue(eventos[0]['recuperada'])
        self.assertEqual(metricas.contagens['navegacoes_recuperadas'], 1)
        page.wait_for_load_state.assert_awaited_once()
