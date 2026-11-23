"""Instrumentação do motor e do diagnóstico com fixtures locais."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from threading import Event
from time import process_time
from timeit import Timer
import unittest
from unittest.mock import patch

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from ambidiff import checkpoints
from ambidiff.diagnostics import montar_diagnostico
from ambidiff.paired import _extrair_page
from ambidiff.smart import Metricas
from test_filter_stage3 import portal_meta
from test_update18 import A, B, executar, opcao
from test_update19 import RID, run


class Relogio:
    segundos = 0.0

    def __call__(self):
        return self.segundos

    def avancar(self, segundos):
        self.segundos += segundos


@contextmanager
def sem_cronometro(*args, **kwargs):
    yield


class DesempenhoTests(unittest.TestCase):
    def test_unidades_e_etapas_disjuntas(self):
        relogio = Relogio()
        with patch('ambidiff.smart.time.perf_counter', relogio):
            metricas = Metricas()
            with metricas.medir('descoberta', descontar='destinos'):
                relogio.avancar(0.125)
                with metricas.medir('destinos'):
                    relogio.avancar(0.5)
            with metricas.medir('preparacao'):
                relogio.avancar(0.75)
                metricas.tempos['espera_carregamento'] = 0.25
            with metricas.medir('extracao'):
                with metricas.medir('abas'):
                    relogio.avancar(0.125)
            with metricas.medir('comparacao_releitura'):
                relogio.avancar(0.25)
            metricas.tempos['segunda_leitura'] = 0.375
            relogio.avancar(0.25)
            metricas.finalizar()
            resultado = {'metricas': metricas.resultado(), 'andamento': {'pares_comparados': 2},
                         'exportacao_worker_segundos': 0.5}

        diag = montar_diagnostico(resultado)
        d = diag['desempenho']
        t = d['etapas_coleta_segundos']
        self.assertEqual(d['tempo_total_coleta_segundos'], 2.0)
        self.assertEqual(d['tempo_medio_por_par_comparado_segundos'], 1.0)
        self.assertEqual(d['exportacao_relatorios_segundos'], 0.5)
        self.assertEqual(d['espera_explicita_na_preparacao_segundos'], 0.25)
        self.assertEqual(t['preparacao_estabilizacao'], 0.75)
        self.assertEqual(t['extracao_dom'], 0.125)
        self.assertEqual(t['pareamento_comparacao'], 0.25)
        self.assertEqual(t['fila_descoberta'], 0.125)
        self.assertEqual(t['verificacao_destinos'], 0.5)
        self.assertEqual(sum(t.values()), 1.75)
        self.assertEqual(diag['metricas']['tempos_segundos']['descoberta'], 0.625)

    def test_extracao_com_timeout_inclui_as_duas_tentativas(self):
        relogio = Relogio()

        class PaginaComTimeout:
            def evaluate(self, _):
                relogio.avancar(0.25)
                raise PlaywrightTimeout('Timeout da fixture')

            def wait_for_timeout(self, ms):
                relogio.avancar(ms / 1000)

        with patch('ambidiff.smart.time.perf_counter', relogio):
            metricas = Metricas()
            with self.assertRaises(PlaywrightTimeout):
                _extrair_page(PaginaComTimeout(), A, [], lambda _: None, metricas=metricas, profunda=False)
            metricas.finalizar()

        d = montar_diagnostico({'metricas': metricas.resultado()})['desempenho']
        self.assertEqual(d['etapas_coleta_segundos']['extracao_dom'], 0.7)
        self.assertEqual(metricas.contagens['operacoes_extracao'], 1)
        self.assertEqual(metricas.contagens['tentativas_extracao_adicionais'], 1)
        self.assertIsNone(d['tempo_medio_por_par_comparado_segundos'])

    def test_visitas_e_pares_com_timeout_http_e_download(self):
        def navegar(_, url):
            if url == B + '1':
                raise PlaywrightTimeout('Timeout 100 ms excedido na fixture')
            if url == B + '2':
                raise RuntimeError('HTTP 503')
            if url == B + '3':
                raise RuntimeError('Page.goto: Download is starting')

        r, _, visitas = run(n=5, nav=navegar)
        diag = montar_diagnostico(r)
        d = diag['desempenho']
        c = d['contagens']
        self.assertEqual(c['visitas_html_tentadas'], len(visitas))
        self.assertEqual(c['visitas_html_tentadas'], 10)
        self.assertEqual(c['paginas_com_dom_preservado'], 4)
        self.assertEqual(c['pares_comparados'], 2)
        self.assertEqual(c['pares_inconclusivos'], 1)
        self.assertEqual(c['pares_falhos'], 2)
        self.assertEqual(diag['falhas_por_tipo']['TIMEOUT'], 1)
        self.assertEqual(diag['falhas_por_tipo']['HTTP'], 1)
        self.assertGreater(d['etapas_coleta_segundos']['navegacao_html'], 0)

    def test_filtro_diagnostico_reaproveita_contagem_sem_expor_urls(self):
        token = 'segredo-da-fixture'

        def grafo(url):
            base = A if url.startswith(A) else B
            if url != base:
                return []
            return [opcao('Vizinho', base + 'web/outro?token=' + token, 'Menu'),
                    opcao('Fotografias', base + 'fotos?cur=115', 'Acervo')]

        r, visitas, _ = executar(grafo, metadados=portal_meta)
        d = montar_diagnostico(r)['desempenho']
        self.assertEqual(visitas, [A, B])
        self.assertEqual(d['contagens']['urls_excluidas_intencionalmente'], 4)
        self.assertEqual(d['contagens']['urls_excluidas_intencionalmente'], r['filtro_urls']['urls_excluidas'])
        self.assertNotIn(token, json.dumps(d))
        self.assertNotIn(A, json.dumps(d))
        self.assertNotIn(B, json.dumps(d))

    def test_divergencias_pareamento_e_fila_iguais_com_cronometros_neutros(self):
        r, _, abertas = run(n=4)
        with patch.object(Metricas, 'medir', sem_cronometro):
            sem_medicao, _, outras_abertas = run(n=4)

        self.assertEqual(abertas, outras_abertas)
        for campo in ('divergencias', 'estados_pares', 'diagnosticos_pares', 'filtro_urls', 'fila_pendente'):
            self.assertEqual(r[campo], sem_medicao[campo], campo)
        self.assertTrue(any(div['elemento'] == 'ÁUDIOS' for div in r['divergencias']))

    def test_interrupcao_recuperacao_e_retomada_preservam_resultados(self):
        parada = Event()
        snapshots = []

        def interromper(pagina):
            if pagina.url == A + '1':
                parada.set()

        parcial, _, visitas_parciais = run(n=4, extra=interromper, stop=parada, checkpoints=snapshots)
        snapshot = snapshots[-1]
        recuperado = checkpoints.recuperar(snapshot)
        d = montar_diagnostico(recuperado)['desempenho']
        self.assertEqual(d['origem_coleta'], 'checkpoint')
        self.assertEqual(d['contagens']['pares_comparados'], 1)
        self.assertEqual(d['contagens']['visitas_html_tentadas'], len(visitas_parciais))
        self.assertGreater(d['etapas_coleta_segundos']['checkpoints'], 0)
        self.assertEqual(parcial['divergencias'], recuperado['divergencias'])

        retomado, _, visitas_retomadas = run(n=4, retomada=snapshot['retomada'])
        inteiro, _, _ = run(n=4)
        self.assertEqual(retomado['divergencias'], inteiro['divergencias'])
        self.assertCountEqual(retomado['estados_pares'], inteiro['estados_pares'])
        self.assertEqual(visitas_retomadas, [url for par in recuperado['fila_pendente'] for url in par[:2]])
        novo = montar_diagnostico(retomado)['desempenho']
        self.assertFalse(novo['historico_metricas_legado'])
        self.assertGreaterEqual(novo['tempo_total_coleta_segundos'], d['tempo_total_coleta_segundos'])
        self.assertEqual(novo['contagens']['visitas_html_tentadas'], len(visitas_parciais) + len(visitas_retomadas))
        self.assertEqual(novo['contagens']['pares_comparados'], 4)

        estado_legado = deepcopy(snapshot['retomada']['estado'])
        for campo in ('versao_desempenho', 'historico_metricas_legado'):
            del estado_legado['metricas'][campo]
        legado, _, _ = run(n=4, retomada=checkpoints.empacotar(estado_legado))
        self.assertTrue(montar_diagnostico(legado)['desempenho']['historico_metricas_legado'])
        self.assertEqual(legado['divergencias'], inteiro['divergencias'])

    def test_diagnostico_legado_sem_campos_novos(self):
        legado = {'metricas': {'tempos_segundos': {'navegacao': 0.25}, 'contagens': {'paginas_visitadas': 1}},
                  'media_segundos_por_par': 0.8, 'duracao_segundos': 0.8}
        diag = montar_diagnostico(legado)
        self.assertNotIn('desempenho', diag)
        for campo, valor in legado.items():
            self.assertEqual(diag[campo], valor)

    def test_worker_grava_json_com_tempo_de_persistencia(self):
        from web import server

        r, _, _ = run(n=1)
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td)
            with patch.multiple(server, PASTA=pasta, HISTORY_PATH=pasta / 'historico.json',
                                PARAR=Event(), executar=lambda *args, **kwargs: r), patch.dict(server.STATE):
                server.worker({'url_a': A, 'url_b': B, 'nome_a': 'PRD', 'nome_b': 'DES',
                               'site_nome': 'Fixture', 'auditar_externos': False}, RID)
            diag = json.loads((pasta / f'diagnostico_{RID}.json').read_text(encoding='utf-8'))
            comparacao = json.loads((pasta / f'comparacao_{RID}.json').read_text(encoding='utf-8'))
        d = diag['desempenho']
        total_worker = d['tempo_worker_ate_gravacao_diagnostico_segundos']
        self.assertGreater(total_worker, d['exportacao_relatorios_segundos'])
        self.assertGreater(d['exportacao_relatorios_segundos'], 0)
        self.assertNotIn('desempenho', comparacao)

    def test_custo_cpu_dos_cronometros_e_baixo(self):
        metricas = Metricas()

        def cronometros(medir):
            with medir('descoberta', descontar='destinos'):
                with medir('destinos'):
                    pass

        numero = 20_000
        medido = min(Timer(lambda: cronometros(metricas.medir), timer=process_time).repeat(3, numero))
        neutro = min(Timer(lambda: cronometros(sem_cronometro), timer=process_time).repeat(3, numero))
        # Margem para CI compartilhada. Mede dois escopos, inclusive o desconto.
        self.assertLess((medido - neutro) / numero, 20e-6)
