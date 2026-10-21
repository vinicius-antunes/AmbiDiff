"""Regressões USEIA com HTML sintético; nenhum portal corporativo é acessado."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ambidiff.core import Item, Pagina
from ambidiff.navigation import validar_rotas, equivalente_declarado
from ambidiff.paired import executar_pareado
from ambidiff.functional import escolher_candidatos, _um_clique, verificar_par
from ambidiff.reports import exportar
from ambidiff.diagnostics import montar_diagnostico


A = 'https://prd.test/'
B = 'https://des.test/web/useia'


class NavigationTests(unittest.TestCase):
    def executar(self, navegar, **kwargs):
        def abrir(page, url):
            final, html = navegar(url)
            page.set_content(html)
            return type('Resposta', (), {'status':200, 'url':final})()
        with patch('ambidiff.paired._abrir', side_effect=abrir), \
             patch('ambidiff.paired._preparar_conteudo', return_value={
                 'estavel':True, 'rolagem_limitada':False, 'passos_rolagem':0}):
            return executar_pareado(A, B, 'PRD', 'DES', threading.Event(),
                                    lambda _:None, lambda _:None, **kwargs)

    def test_useia_login_nao_e_conteudo_nem_comparacao_completa(self):
        def navegar(url):
            if url == A:
                return A+'c/portal/login?p_p_id=com_liferay_login_web_portlet_LoginPortlet', '<form><input type="password"></form>'
            return url, '<main><h1>USEIA</h1><a href="https://des.test/">Início</a></main>'
        r = self.executar(navegar)
        self.assertEqual(r['paginas'], {'PRD':0, 'DES':0})
        self.assertEqual(r['situacao_analise'], 'inconclusivo')
        self.assertFalse(any(r['completo'].values()))
        self.assertFalse(r['falhas'])
        self.assertEqual(r['acessos'][0]['tipo'], 'AUTENTICACAO')
        self.assertIn('Autenticação', r['pendencias'][0]['motivo'])
        self.assertFalse(r['divergencias'])  # login não é ausência de conteúdo
        self.assertTrue(r['meta_varredura']['PRD']['motivo_parada'])
        self.assertEqual(r['paginas_acessiveis_sem_par'][0]['ambiente'],'DES')
        self.assertEqual(r['links_observados'][0]['elemento'],'Início')
        self.assertEqual(r['links_observados'][0]['destino'],'https://des.test/')

    def test_rotas_distintas_sem_declaracao_nao_sao_comparadas(self):
        r = self.executar(lambda url:(url, '<h1>USEIA</h1>'))
        self.assertEqual(r['situacao_analise'], 'inconclusivo')
        self.assertEqual(r['divergencias'][0]['tipo'], 'Redirecionamento')
        self.assertFalse(r['completo']['PRD'])
        self.assertIn('sem equivalência', r['pendencias'][0]['motivo'])

    def test_declaracao_explicita_compara_raizes_diferentes_e_preserva_audios(self):
        def navegar(url):
            nav = '<nav><a href="https://prd.test/w/audios">ÁUDIOS</a></nav>' if url == A else ''
            return url, '<main><h1>USEIA</h1></main>'+nav
        r = self.executar(navegar, rotas_equivalentes=[{'a':A,'b':B}], ambiente_desatualizado='DES')
        self.assertEqual(r['paginas'], {'PRD':1, 'DES':1})
        self.assertTrue(r['completo']['PRD'])
        audios = [d for d in r['divergencias'] if d['elemento']=='ÁUDIOS']
        self.assertEqual(len(audios), 1)
        self.assertEqual(audios[0]['presente_em'], 'PRD')
        self.assertEqual(audios[0]['nao_identificado_em'], 'DES')
        self.assertEqual(r['itens_editoriais_agrupados'], 0)
        self.assertEqual(r['links_observados'][0]['destino'], A+'w/audios')

    def test_login_na_raiz_nao_impede_outro_par_publico_declarado(self):
        def navegar(url):
            if url == A:return A+'login', '<input type="password">'
            return url, '<main><h1>Conteúdo público</h1></main>'
        r = self.executar(navegar, rotas_equivalentes=[{'a':A+'publico','b':B}])
        self.assertEqual(r['paginas'], {'PRD':1, 'DES':1})
        self.assertEqual(r['situacao_analise'], 'parcial')
        self.assertFalse(r['completo']['DES'])
        self.assertTrue(r['pendencias'])

    def test_redirecionamento_equivalente_legitimo_continua(self):
        # A equivalência aqui é declarada, não inferida do texto da página.
        r = self.executar(lambda url:(A+'publico' if url==A else B, '<h1>Página pública</h1>'),
                          rotas_equivalentes=[{'a':A+'publico','b':B}])
        self.assertGreaterEqual(r['paginas']['PRD'], 1)
        self.assertFalse(r['falhas'])
        self.assertTrue(any(a['tipo']=='REDIRECIONAMENTO' for a in r['acessos']))

    def test_falha_automacao_distinta_de_autenticacao(self):
        with patch('ambidiff.paired._abrir', side_effect=RuntimeError('Timeout de teste')):
            r = executar_pareado(A,B,'PRD','DES',threading.Event(),lambda _:None,lambda _:None)
        self.assertEqual(r['situacao_analise'], 'inconclusivo')
        self.assertTrue(r['falhas'])
        self.assertEqual(r['acessos'][0]['tipo'], 'FALHA_DE_ACESSO')
        self.assertEqual(r['falhas'][0]['tipo_erro'], 'TIMEOUT')

    def test_http_401_e_limitacao_de_autenticacao(self):
        resposta=type('Resposta',(),{'status':401,'url':A})()
        with patch('ambidiff.paired._abrir',return_value=resposta):
            r=executar_pareado(A,B,'PRD','DES',threading.Event(),lambda _:None,lambda _:None)
        self.assertEqual(r['situacao_analise'],'inconclusivo')
        self.assertFalse(r['falhas'])
        self.assertTrue(all(a['tipo']=='AUTENTICACAO' for a in r['acessos']))

    def test_redirecionamento_legitimo_existente_sem_configuracao(self):
        from ambidiff.core import executar
        def navegar(page,url):
            page.set_content('<h1>Página pública</h1>')
            return type('Resposta',(),{'status':200,'url':url+'inicio'})()
        with patch('ambidiff.paired._abrir',side_effect=navegar), \
             patch('ambidiff.paired._preparar_conteudo',return_value={'estavel':True,'rolagem_limitada':False}):
            r=executar(A,'https://des.test/','PRD','DES',threading.Event(),lambda _:None,lambda _:None)
        self.assertEqual(r['situacao_analise'],'concluido')
        self.assertEqual(r['paginas'],{'PRD':1,'DES':1})
        self.assertFalse(r['divergencias'])

    def test_configuracao_rejeita_login_origem_externa_e_par_incompleto(self):
        for rotas in ([{'a':A+'login','b':B}], [{'a':'https://outro.test/','b':B}],
                      [{'a':A}], 'inválido'):
            with self.subTest(rotas=rotas), self.assertRaises(ValueError):
                validar_rotas(rotas,A,B)
        rotas=validar_rotas([{'a':A,'b':B}],A,B)
        self.assertTrue(equivalente_declarado(A,B,rotas))
        self.assertTrue(equivalente_declarado(A+'ajuda',B+'/ajuda',rotas))
        self.assertFalse(equivalente_declarado(A+'ajuda',B+'/outro',rotas))
        self.assertFalse(equivalente_declarado(A+'ajuda','https://des.test/web/useia-extra/ajuda',rotas))

    def test_inicio_e_menu_elegiveis_mas_acoes_e_destinos_divergentes_nao(self):
        def item(nome,url,posicao=''):
            return Item('Opção',nome,nome,destino=url,seletor='#link',posicao=posicao)
        pares=[(item('Início',A),item('Início','https://des.test/')),
               (item('Equipe',A+'equipe','Menu lateral'),item('Equipe','https://des.test/equipe','Menu lateral')),
               (item('Salvar',A+'save','Menu lateral'),item('Salvar','https://des.test/save','Menu lateral')),
               (item('Início',A),item('Início','https://outro.test/'))]
        self.assertEqual(len(escolher_candidatos(pares,A,'https://des.test/',limite=12)),2)

    def test_resultados_iguais_sem_navegacao_tambem_ficam_registrados(self):
        item=Item('Opção','Início','Início',destino=A,seletor='#inicio')
        obs={'status':'sem_navegacao_observada','url_final':A,'motivo':'Janela limitada.'}
        registros=[]
        with patch('ambidiff.functional._um_clique',return_value=obs):
            div=verificar_par(None,Pagina(A,'','P',[]),Pagina(B,'','P',[]),item,item,
                              'PRD','DES',A,B,lambda _:None,resultados=registros)
        self.assertIsNone(div)
        self.assertEqual(len(registros),1)
        self.assertEqual(registros[0]['PRD']['status'],'sem_navegacao_observada')

    def test_api_valida_e_encaminha_rotas_sem_iniciar_worker_real(self):
        from web import server
        with patch.dict(server.STATE, status='pronto'), patch('web.server.threading.Thread') as worker:
            client=server.app.test_client()
            payload={'url_a':A,'url_b':B,'rotas_equivalentes':[{'a':A,'b':B}]}
            self.assertEqual(client.post('/api/comparar',json=payload).status_code,200)
            self.assertEqual(worker.call_args.kwargs['args'][0]['rotas_equivalentes'],payload['rotas_equivalentes'])
        with patch.dict(server.STATE, status='pronto'), patch('web.server.threading.Thread') as worker:
            payload['rotas_equivalentes']=[{'a':'https://outro.test/','b':B}]
            self.assertEqual(client.post('/api/comparar',json=payload).status_code,400)
            worker.assert_not_called()

    def test_exportacoes_preservam_limitacoes_e_destinos(self):
        r=self.executar(lambda url:(A+'login' if url==A else url,'<h1>Página</h1>'))
        diag=montar_diagnostico(r)
        self.assertEqual(diag['acessos'],r['acessos'])
        with tempfile.TemporaryDirectory() as d:
            arquivos=exportar(r,Path(d),'teste')
            self.assertEqual(json.loads(Path(arquivos['json']).read_text())['pendencias'],r['pendencias'])
            html=Path(arquivos['html']).read_text()
            self.assertIn('Autenticação',html)
            self.assertIn(A+'login',html)


class FunctionalBrowserTests(unittest.TestCase):
    def test_formulario_envia_par_explicito_e_exibe_limitacao(self):
        from playwright.sync_api import sync_playwright
        from web import server
        enviados=[]
        with patch.dict(server.STATE,status='pronto'):
            client=server.app.test_client()
            with sync_playwright() as p:
                try:browser=p.chromium.launch(headless=True)
                except Exception:browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                try:
                    page=browser.new_page()
                    erros=[];page.on('pageerror',lambda e:erros.append(str(e)))
                    def responder(route):
                        req=route.request
                        path=req.url.split('http://ambidiff.test',1)[-1]
                        if path=='/api/comparar':
                            enviados.append(req.post_data_json)
                            route.fulfill(status=200,content_type='application/json',body='{"ok":true}')
                        else:
                            res=client.get(path)
                            route.fulfill(status=res.status_code,content_type=res.content_type,body=res.data)
                    page.route('http://ambidiff.test/**',responder)
                    page.goto('http://ambidiff.test/',wait_until='networkidle')
                    page.locator('[data-section="comparar"]').click()
                    page.locator('#url-a').fill(A);page.locator('#url-b').fill(B)
                    page.locator('#rota-a').fill(A+'publico');page.locator('#rota-b').fill(B)
                    page.locator('#run-button').click()
                    page.wait_for_function('document.querySelector("#run-button").disabled === false')
                    self.assertEqual(enviados[0]['rotas_equivalentes'],[{'a':A+'publico','b':B}])
                    page.evaluate('''() => {currentReport={ambientes:{PRD:'https://prd.test/',DES:'https://des.test/'},
                      acessos:[{ambiente:'PRD',tipo:'AUTENTICACAO',motivo:'Login não tentado',url_solicitada:'https://prd.test/',url_final:'https://prd.test/login'}]};
                      navigationObservations(currentReport);}''')
                    self.assertIn('Login não tentado',page.locator('#navigation-observations').inner_text())
                    self.assertFalse(erros)
                finally:browser.close()

    def test_inicio_destino_atual_clique_inerte_e_post_bloqueado(self):
        from playwright.sync_api import sync_playwright
        recebidos=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                recebidos.append(('GET',self.path))
                html='''<a id="atual" href="/">Início</a>
                <a id="inerte" href="/destino" onclick="event.preventDefault()">Início</a>
                <a id="post" href="/destino" onclick="event.preventDefault();fetch('/gravar',{method:'POST'})">Consultar</a>
                <a id="externo" href="/destino" onclick="event.preventDefault();location.href='http://externo.test/'">Consultar</a>'''
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
                self.wfile.write(html.encode())
            def do_POST(self):
                recebidos.append(('POST',self.path));self.send_response(500);self.end_headers()
        serv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=serv.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{serv.server_port}/'
        try:
            with sync_playwright() as p:
                try:browser=p.chromium.launch(headless=True)
                except Exception:browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                try:
                    pagina=Pagina(base,'','P',[])
                    def clicar(id,destino):
                        item=Item('Opção','Início','Início',destino=destino,seletor='#'+id)
                        return _um_clique(browser,pagina,item,base)
                    self.assertEqual(clicar('atual',base)['status'],'destino_atual')
                    self.assertEqual(clicar('inerte',base+'destino')['status'],'sem_navegacao_observada')
                    post=clicar('post',base+'destino')
                    self.assertEqual(post['status'],'inconclusivo')
                    self.assertEqual(post['bloqueios'][0]['metodo'],'POST')
                    externo=clicar('externo',base+'destino')
                    self.assertEqual(externo['status'],'inconclusivo')
                    self.assertTrue(externo['bloqueios'])
                    self.assertFalse(any(m=='POST' for m,_ in recebidos))
                finally:browser.close()
        finally:
            serv.shutdown();serv.server_close();thread.join()


if __name__=='__main__':unittest.main()
