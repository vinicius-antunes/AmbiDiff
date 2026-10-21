"""Regressões da instrumentação de progresso; não acessam portais externos."""
import unittest
from unittest.mock import patch
from web import server


class ProgressTests(unittest.TestCase):
    def setUp(self):
        with server.LOCK:
            self.original=dict(server.STATE)

    def tearDown(self):
        with server.LOCK:
            server.STATE.clear()
            server.STATE.update(self.original)

    def test_eta_apenas_quando_ha_amostras_recentes(self):
        f=server.estimar_tempo_restante
        samples=[(0,10),(40,25)]
        self.assertEqual(f(samples,40,25,40,'executando'),200)
        self.assertIsNone(f(samples,40,25,40,'concluido'))
        self.assertIsNone(f(samples,40,90,40,'executando'))
        self.assertIsNone(f(samples,40,25,10,'executando'))
        self.assertIsNone(f(samples,180,25,180,'executando'))
        self.assertIsNone(f([(0,10),(40,11)],40,11,40,'executando'))

    def test_callback_nao_regride_e_nao_antecipa_100_porcento(self):
        with server.LOCK:
            server.STATE.update(status='executando',progresso=0,amostras_progresso=[])
        with patch.object(server.time,'monotonic',return_value=15):
            server.atualizar_progresso(.12)
        with patch.object(server.time,'monotonic',return_value=16):
            server.atualizar_progresso(.05)
            server.atualizar_progresso(1.0)
        with server.LOCK:
            self.assertEqual(server.STATE['progresso'],99)
            self.assertEqual(len(server.STATE['amostras_progresso']),2)
        with patch.object(server.time,'monotonic',return_value=20):
            server.atualizar(status='concluido',progresso=100)
        server.atualizar_progresso(.40)
        with server.LOCK:
            self.assertEqual(server.STATE['progresso'],100)
            self.assertEqual(server.STATE['fim_monotonic'],20)

    def test_status_publico_com_duracao_e_sem_controles_internos(self):
        with server.LOCK:
            server.STATE.update(status='executando',progresso=25,logs=['Teste local'],
                inicio_monotonic=10,fim_monotonic=None,
                amostras_progresso=[(10,10),(50,25)])
        with patch.object(server.time,'monotonic',return_value=50):
            response=server.app.test_client().get('/api/status')
        self.assertEqual(response.status_code,200)
        payload=response.get_json()
        self.assertEqual(payload['progresso'],25)
        self.assertEqual(payload['tempo_decorrido_segundos'],40)
        self.assertEqual(payload['tempo_restante_segundos'],200)
        for key in ('inicio_monotonic','fim_monotonic','amostras_progresso'):
            self.assertNotIn(key,payload)

    def test_status_pronto_e_fim_da_execucao(self):
        with server.LOCK:
            server.STATE.update(status='pronto',progresso=0,inicio_monotonic=None,
                fim_monotonic=None,amostras_progresso=[])
        self.assertIsNone(server.estado_publico()['tempo_restante_segundos'])
        with server.LOCK:
            server.STATE.update(status='concluido',progresso=100,inicio_monotonic=10,
                fim_monotonic=55,amostras_progresso=[(10,0),(50,98)])
        payload=server.estado_publico(agora=200)
        self.assertEqual(payload['tempo_decorrido_segundos'],45)
        self.assertIsNone(payload['tempo_restante_segundos'])

    def test_interface_exibe_resumo_acessivel(self):
        response=server.app.test_client().get('/')
        self.assertEqual(response.status_code,200)
        markup=response.get_data(as_text=True)
        for token in ('progress-track','progress-percent','progress-elapsed','progress-eta','aria-valuenow'):
            self.assertIn(token,markup)


if __name__=='__main__':
    unittest.main()
