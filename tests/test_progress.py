"""Regressões locais de cursor, interrupção cooperativa e resultados parciais."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from web import server
from ambidiff.core import _abrir
from ambidiff.paired import executar_pareado
from ambidiff.progress import (Acompanhamento, InterrupcaoSolicitada,
                               TempoParExcedido, esperar)


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.state=patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True)
        self.state.start();self.addCleanup(self.state.stop)
        server.STATE.update(status='executando',execucao_id='teste',logs=[],logs_eventos=[],
                            log_seq=0,interrupcao_solicitada=False)
        self.event=patch.object(server,'PARAR',threading.Event())
        self.event.start();self.addCleanup(self.event.stop)
        self.client=server.app.test_client()

    def test_mais_de_200_logs_cursor_e_lacuna_explicita(self):
        for n in range(250):server.log('Mensagem '+str(n+1))
        s=self.client.get('/api/status?execucao=teste&apos=0').json
        self.assertEqual(len(s['logs']),200)
        self.assertEqual([e['id'] for e in s['logs_eventos']],list(range(51,251)))
        self.assertEqual(s['logs_descartados'],50)
        self.assertTrue(s['ultima_atividade'])
        for n in range(10):server.log('Nova '+str(n))
        s=self.client.get('/api/status?execucao=teste&apos=250').json
        self.assertEqual([e['id'] for e in s['logs_eventos']],list(range(251,261)))
        self.assertEqual(s['logs_descartados'],0)
        self.assertEqual(self.client.get('/api/status?execucao=teste&apos=260').json['logs_eventos'],[])

    def test_nova_execucao_reinicia_cursor_e_cursor_invalido_rejeitado(self):
        server.log('Primeira da nova execução')
        s=self.client.get('/api/status?execucao=antiga&apos=999').json
        self.assertTrue(s['reiniciar_logs'])
        self.assertEqual(s['logs_eventos'][0]['id'],1)
        self.assertTrue(self.client.get('/api/status?execucao=teste&apos=999').json['reiniciar_logs'])
        self.assertEqual(self.client.get('/api/status?apos=invalido').status_code,400)

    def test_interrupcao_unico_pedido_idempotente_e_sem_nova_varredura(self):
        r=self.client.post('/api/parar')
        self.assertTrue(r.json['interrupcao_solicitada'])
        self.assertTrue(server.PARAR.is_set())
        self.assertEqual(server.STATE['status'],'executando')
        self.assertEqual(self.client.get('/api/status').json['estado_execucao'],'interrupcao_solicitada')
        self.client.post('/api/parar')
        self.assertEqual(server.STATE['log_seq'],1)
        self.assertEqual(self.client.post('/api/comparar',json={}).status_code,409)

    def test_espera_interrompivel_e_limite_cooperativo_do_par(self):
        event=threading.Event()
        class Page:
            def wait_for_timeout(self,ms):event.set()
        with self.assertRaises(InterrupcaoSolicitada):esperar(Page(),900,event)
        c=Acompanhamento(threading.Event())
        with patch('ambidiff.progress.time.monotonic',return_value=0):c.iniciar_par(1,2)
        with patch('ambidiff.progress.time.monotonic',return_value=91),self.assertRaises(TempoParExcedido):c.verificar()
        self.assertEqual(c.dados['ultimo_par_processado'],0)

    def test_timeout_de_navegacao_nao_tenta_novamente_apos_interrupcao(self):
        event=threading.Event();tentativas=[]
        class Page:
            def goto(self,*args,**kw):
                tentativas.append(kw['timeout']);event.set();raise RuntimeError('Timeout de teste')
        with self.assertRaises(InterrupcaoSolicitada):_abrir(Page(),'https://prd.test/',parar=event)
        self.assertEqual(tentativas,[30000])
        event.clear();tentativas.clear()
        class Recuperacao:
            url='https://prd.test/'
            def goto(self,*args,**kw):tentativas.append(kw['timeout']);raise RuntimeError('Timeout de teste')
            def locator(self,*args):return self
            def inner_text(self,**kw):event.set();raise RuntimeError('Timeout durante recuperação')
        with self.assertRaises(InterrupcaoSolicitada):_abrir(Recuperacao(),'https://prd.test/',parar=event)
        self.assertEqual(tentativas,[30000])

    def resultado_interrompido(self):
        event=threading.Event();snapshots=[];atividades=[]
        def navegar(page,url,**kw):
            host='prd.test' if 'prd.test' in url else 'des.test'
            audios='<a href="https://prd.test/audios">ÁUDIOS</a>' if host=='prd.test' else ''
            page.set_content('<h1>CGE sintética</h1><nav>'+audios+
                             '<a href="https://'+host+'/segundo">Segundo</a></nav>')
            return type('R',(),{'status':200,'url':url})()
        def atividade(**kw):
            atividades.append(copy.deepcopy(kw))
            if kw['par_atual']==2:event.set()
        with patch('ambidiff.paired._abrir',side_effect=navegar), \
             patch('ambidiff.paired._preparar_conteudo',return_value={'estavel':True,'rolagem_limitada':False}):
            r=executar_pareado('https://prd.test/','https://des.test/','PRD','DES',event,
                              lambda _:None,lambda _:None,site_nome='CGE sintética',
                              ambiente_desatualizado='DES',atividade=atividade,
                              checkpoint=lambda d:snapshots.append(copy.deepcopy(d)))
        return r,snapshots,atividades

    def test_interrupcao_preserva_primeiro_par_audios_e_checkpoint_antes_de_20(self):
        r,snapshots,atividades=self.resultado_interrompido()
        self.assertEqual(r['situacao_analise'],'parcial')
        self.assertFalse(r['completo']['PRD'])
        self.assertEqual(r['paginas']['PRD'],1)
        self.assertEqual(r['acompanhamento']['ultimo_par_processado'],1)
        self.assertEqual(r['acompanhamento']['pares_pendentes'],1)
        self.assertTrue(any(a['par_atual']==2 for a in atividades))
        audios=[d for d in r['divergencias'] if d['elemento']=='ÁUDIOS']
        self.assertEqual(len(audios),1)
        self.assertEqual((audios[0]['presente_em'],audios[0]['nao_identificado_em']),('PRD','DES'))
        self.assertEqual(snapshots[-1]['acompanhamento']['ultimo_par_processado'],1)
        self.assertTrue(snapshots[-1]['brutos'])
        self.assertIn('Interrompida',snapshots[-1]['meta_varredura']['PRD']['motivo_parada'])

    def test_worker_grava_parcial_diagnostico_e_mantem_checkpoint(self):
        r,snapshots,_=self.resultado_interrompido()
        rid='20261021_081730_a6242f'
        with tempfile.TemporaryDirectory() as d:
            pasta=Path(d)
            cp=pasta/f'checkpoint_{rid}.json';cp.write_text(json.dumps(snapshots[-1]))
            params={'url_a':'https://prd.test/','url_b':'https://des.test/',
                    'nome_a':'PRD','nome_b':'DES','site_nome':'CGE sintética','auditar_externos':False}
            server.PARAR.set()
            with patch.object(server,'PASTA',pasta),patch.object(server,'HISTORY_PATH',pasta/'historico.json'), \
                 patch('web.server.executar',return_value=r):server.worker(params,rid)
            self.assertEqual(server.STATE['status'],'concluido')
            self.assertTrue(cp.exists())
            bruto=json.loads((pasta/f'comparacao_{rid}.json').read_text())
            self.assertEqual(bruto['situacao_analise'],'parcial')
            diag=json.loads((pasta/f'diagnostico_{rid}.json').read_text())
            self.assertEqual(diag['acompanhamento']['ultimo_par_processado'],1)
            self.assertTrue((pasta/f'log_{rid}.txt').exists())


class BrowserProgressTests(unittest.TestCase):
    def test_interface_cursor_duplicacoes_e_um_clique_confirma_interrupcao(self):
        from playwright.sync_api import sync_playwright
        with patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True), \
             patch.object(server,'PARAR',threading.Event()):
            server.STATE.update(status='executando',execucao_id='browser',logs=[],logs_eventos=[],
                                log_seq=0,interrupcao_solicitada=False,ultimo_id=None,
                                ultimo_par_processado=110,par_atual=111,pares_pendentes=20)
            for n in range(200):server.log('Mensagem '+str(n+1))
            client=server.app.test_client();pedidos=[]
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                try:
                    page=browser.new_page();erros=[]
                    page.on('pageerror',lambda e:erros.append(str(e)))
                    def responder(route):
                        req=route.request;path=req.url.split('http://ambidiff.test',1)[-1]
                        if path=='/api/parar':pedidos.append(path)
                        res=client.open(path,method=req.method)
                        route.fulfill(status=res.status_code,content_type=res.content_type,body=res.data)
                        res.close()
                    page.route('http://ambidiff.test/**',responder)
                    page.goto('http://ambidiff.test/',wait_until='networkidle')
                    page.wait_for_function('lastLogId === 200')
                    for n in range(200,236):server.log('Mensagem '+str(n+1))
                    page.evaluate('poll()')
                    self.assertIn('Mensagem 236',page.locator('#terminal').inner_text())
                    self.assertEqual(page.locator('[data-log-id="236"]').count(),1)
                    page.evaluate('poll()')
                    self.assertEqual(page.locator('[data-log-id="236"]').count(),1)
                    for n in range(250):server.log('Após reconexão '+str(n))
                    page.evaluate('poll()')
                    self.assertIn('50 mensagem(ns)',page.locator('#terminal .subtle-warning').inner_text())
                    self.assertEqual(page.locator('[data-log-id="486"]').count(),1)
                    page.locator('#stop-button').click()
                    page.wait_for_function('document.querySelector("#running-label").textContent.includes("Interrupção solicitada")')
                    self.assertEqual(len(pedidos),1)
                    self.assertTrue(server.PARAR.is_set())
                    self.assertTrue(page.locator('#stop-button').is_disabled())
                    page.evaluate('poll()')
                    self.assertEqual(page.locator('#running-label').inner_text(),'Interrupção solicitada — aguardando operação atual')
                    self.assertEqual(page.locator('#last-pair').inner_text(),'110')
                    self.assertIn('111',page.locator('#current-stage').inner_text())
                    self.assertFalse(erros)
                finally:browser.close()

    def test_operacao_lenta_respeita_timeout_real_de_navegacao(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from playwright.sync_api import sync_playwright, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
        liberar=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                liberar.wait(2)
                try:self.send_response(200);self.end_headers();self.wfile.write(b'<h1>Pagina</h1>')
                except (BrokenPipeError,ConnectionResetError):pass
        serv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=serv.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                try:
                    page=browser.new_page();inicio=time.monotonic();erros=[]
                    class PaginaObservada:
                        def __getattr__(self,nome):return getattr(page,nome)
                        def goto(self,*args,**kw):
                            try:return page.goto(*args,**kw)
                            except PlaywrightError as ex:erros.append(ex);raise
                    # A tentativa alternativa pode terminar por timeout ou
                    # ERR_ABORTED ao substituir a navegação ainda pendente.
                    # A primeira tentativa precisa ter atingido seu timeout real.
                    with patch('ambidiff.core.TEMPO_PAGINA_MS',100),self.assertRaises(PlaywrightError):
                        _abrir(PaginaObservada(),f'http://127.0.0.1:{serv.server_port}/')
                    self.assertIsInstance(erros[0],PlaywrightTimeoutError)
                    self.assertLess(time.monotonic()-inicio,1.5)
                finally:browser.close()
        finally:
            liberar.set();serv.shutdown();serv.server_close();thread.join()


if __name__=='__main__':unittest.main()
