"""PRD × PRD com navegação simulada e Chromium interceptado; sem portais reais."""
import copy
import csv
import json
from contextlib import ExitStack
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from ambidiff import checkpoints as cp
from ambidiff.core import Item
from ambidiff.environments import identificar,identidades
from ambidiff.storage import atomic_json
from test_update19 import run
from test_intermat import A,B,RID
import test_update17 as fixtures17


class PRDEngineTests(unittest.TestCase):
    def test_portais_http_locais_equivalentes_com_chromium_e_cookies_isolados(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from ambidiff.core import executar
        recebidos=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):
                recebidos.append((self.path,self.headers.get('Cookie','')))
                lado='a' if self.path.startswith('/a') else 'b'
                html=('<html lang="pt-BR"><head><meta charset="utf-8"><title>Portal fictício PRD</title></head>'
                    '<body><nav><a href="/'+lado+'">Início</a><a href="/'+lado+'/servicos">Serviços</a></nav>'
                    '<main><h1>Portal institucional fictício</h1><p>Informações públicas para testar a comparação local de estrutura e navegação, sem modificar dados.</p></main></body></html>').encode()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
                if lado=='a':self.send_header('Set-Cookie','somente_a=1; Path=/')
                self.send_header('Content-Length',str(len(html)));self.end_headers();self.wfile.write(html)
        srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:'+str(srv.server_port)
            for inteligente in (False,True):
                with self.subTest(varredura_inteligente=inteligente):
                    r=executar(base+'/a',base+'/b','PRD','PRD',threading.Event(),lambda _:None,lambda _:None,varredura_inteligente=inteligente)
                    self.assertEqual(r['divergencias'],[])
                    self.assertEqual(r['andamento']['pares_comparados'],2)
            self.assertTrue(any(p.startswith('/b') for p,c in recebidos))
            self.assertTrue(all('somente_a' not in c for p,c in recebidos if p.startswith('/b')))
        finally:srv.shutdown();thread.join(timeout=5);srv.server_close()

    def test_equivalentes_ids_contextos_e_contadores_independentes(self):
        def extra(p):p.itens=[i for i in p.itens if i.nome!='ÁUDIOS']
        def nav(p,u):
            if u==A:p.ctx.cookies['lado']='A'
            if u==B:self.assertNotIn('lado',p.ctx.cookies)
        r,pw,opened=run(n=2,nomes=('PRD','PRD'),extra=extra,nav=nav)
        self.assertEqual(r['divergencias'],[])
        self.assertEqual(r['ambientes'],{'PRD_A':A,'PRD_B':B})
        self.assertEqual(r['paginas'],{'PRD_A':2,'PRD_B':2})
        self.assertEqual(r['andamento']['pares_comparados'],2)
        self.assertEqual(r['ambiente_a']['tipo'],'PRD');self.assertEqual(r['ambiente_b']['funcao'],'comparado')
        self.assertEqual(len(pw.browsers[0].contexts),2)
        self.assertTrue(all(x['headless'] for x in pw.launches))

    def test_audios_bidirecional_sem_fixar_id_numerico(self):
        for lado in ('A','B'):
            def extra(p):
                if lado=='B':
                    p.itens=[i for i in p.itens if i.nome!='ÁUDIOS']
                    if p.url==B:p.itens.append(Item('Opção','ÁUDIOS','ÁUDIOS',local='Menu',destino=B+'audio.pdf'))
            r,_,_=run(n=1,nomes=('PRD','PRD'),extra=extra)
            d=next(d for d in r['divergencias'] if d.get('elemento')=='ÁUDIOS')
            self.assertEqual(d['presente_em'],'PRD_'+lado)
            self.assertEqual(d['nao_identificado_em'],'PRD_'+('B' if lado=='A' else 'A'))

    def test_falha_apenas_no_servidor_b(self):
        def nav(p,u):
            if u==B:raise RuntimeError('HTTP 503 simulado')
        r,_,_=run(n=1,nomes=('PRD','PRD'),nav=nav)
        self.assertTrue(r['falhas']);self.assertEqual({f['ambiente'] for f in r['falhas']},{'PRD_B'})
        self.assertEqual(r['andamento']['pares_comparados'],0)

    def test_bases_desatualizadas_sem_ocultar_menu(self):
        from ambidiff.paired import executar_pareado
        import test_update19 as fixture
        original=executar_pareado
        for lado,esperado in (('',''),('A','PRD_A'),('B','PRD_B')):
            def configured(*a,**kw):return original(*a,ambiente_desatualizado=lado,**kw)
            with patch('ambidiff.paired.executar_pareado',side_effect=configured):
                r,_,_=fixture.run(n=1,nomes=('PRD','PRD'))
            self.assertEqual(r['ambiente_desatualizado'],esperado)
            self.assertTrue(any(d.get('elemento')=='ÁUDIOS' for d in r['divergencias']))

    def test_interrupcao_recuperacao_retomada_e_rejeicao_de_troca(self):
        stop=threading.Event();snaps=[]
        def extra(p):
            if p.url==B+'1':stop.set()
        r,_,_=run(n=3,nomes=('PRD','PRD'),extra=extra,stop=stop,checkpoints=snaps)
        self.assertEqual(r['estado_execucao'],'interrompido')
        parcial=cp.recuperar(snaps[-1]);self.assertEqual(parcial['ambiente_b']['url'],B)
        estado=cp.validar(snaps[-1]['retomada'])
        self.assertEqual((estado['configuracao']['nome_a'],estado['configuracao']['nome_b']),('PRD_A','PRD_B'))
        resumed,_,opened=run(n=3,nomes=('PRD','PRD'),retomada=snaps[-1]['retomada'])
        self.assertEqual(resumed['andamento']['pares_comparados'],3)
        self.assertNotIn(A,opened);self.assertNotIn(B,opened)
        self.assertEqual(resumed['ambientes'],r['ambientes'])
        self.assertTrue(any(d.get('elemento')=='ÁUDIOS' for d in resumed['divergencias']))
        estado['configuracao'].update(nome_a='PRD_B',nome_b='PRD_A')
        with self.assertRaises(ValueError):cp.validar(cp.empacotar(estado))

    def test_comparacoes_tradicionais_e_identificadores_inalterados(self):
        for outro in ('DES','LAB','HOMOL'):
            r,_,_=run(n=1,nomes=('PRD',outro))
            self.assertEqual(r['ambientes'],{'PRD':A,outro:B})
            self.assertNotIn('ambiente_a',r)
        for nome in ('DES','LAB','HOMOL'):
            with self.assertRaises(ValueError):identificar(nome,nome)
        with self.assertRaises(ValueError):identificar('PRD_B','PRD_A')


class PRDAPITests(unittest.TestCase):
    def setUp(self):
        from web import server
        from ambidiff.live import Logs
        self.server=server;self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for name,value in (('PASTA',self.root),('HISTORY_PATH',self.root/'historico.json'),('PARAR',threading.Event()),('FEED',Logs())):
            self.stack.enter_context(patch.object(server,name,value))
        self.stack.enter_context(patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True))
        server.STATE.update(status='pronto',logs=[]);self.client=server.app.test_client()

    def test_api_aceita_e_separa_tipos_lados_urls_e_base_desatualizada(self):
        for lado,esperado in (('',''),('A','PRD_A'),('B','PRD_B'),('PRD_A','PRD_A'),('PRD_B','PRD_B')):
            self.server.STATE['status']='pronto'
            with patch('web.server.threading.Thread') as worker:
                resp=self.client.post('/api/comparar',json={'url_a':A,'url_b':B,'nome_a':'PRD','nome_b':'PRD','ambiente_desatualizado':lado})
                self.assertEqual(resp.status_code,200,resp.get_json())
                p=worker.call_args.kwargs['args'][0]
                self.assertEqual((p['nome_a'],p['nome_b'],p['url_a'],p['url_b']),('PRD_A','PRD_B',A,B))
                self.assertEqual(p['ambiente_desatualizado'],esperado)
                self.assertTrue(any('PRD_A' in l and 'PRD_B' in l for l in self.server.STATE['logs']))

    def test_validacoes_nao_liberam_outros_tipos_iguais_ou_urls_inseguras(self):
        invalidos=[{'nome_a':n,'nome_b':n} for n in ('DES','LAB','HOMOL')]+[
            {'nome_b':'PRD_X'},{'nome_a':'PRD_A','nome_b':'PRD'},
            {'nome_b':'PRD','ambiente_desatualizado':'PRD'},
            {'nome_b':'PRD','url_a':'file:///tmp/segredo'},
            {'nome_b':'PRD','url_b':'https://user:password@b.test/'},
            {'nome_b':'PRD','url_b':A}]
        for args in invalidos:
            with self.subTest(args=args),patch('web.server.threading.Thread') as worker:
                self.server.STATE['status']='pronto'
                self.assertEqual(self.client.post('/api/comparar',json={'url_a':A,'url_b':B,**args}).status_code,400)
                worker.assert_not_called()

    def test_worker_historico_e_json_diagnostico_preservam_metadados(self):
        r,_,_=run(n=1,nomes=('PRD','PRD'))
        params=dict(url_a=A,url_b=B,nome_a='PRD_A',nome_b='PRD_B',site_nome='Portal fictício',auditar_externos=False)
        with patch.object(self.server,'executar',return_value=r):self.server.worker(params,RID)
        h=json.loads((self.root/'historico.json').read_text())[0]
        self.assertEqual(h['ambiente_a']['url'],A);self.assertEqual(h['ambiente_b']['url'],B)
        diag=json.loads((self.root/f'diagnostico_{RID}.json').read_text())
        self.assertEqual(diag['ambiente_b']['identificador'],'PRD_B')
        txt=(self.root/f'log_{RID}.txt').read_text()
        self.assertIn('PRD (A) — Base',txt);self.assertIn('PRD (B) — Comparado',txt)
        report=self.client.get('/api/relatorio/'+RID).get_json()
        self.assertEqual(report['ambiente_a'],h['ambiente_a'])

    def test_api_retomada_preserva_configuracao_e_legados(self):
        stop=threading.Event();snaps=[]
        def extra(p):
            if p.url==B+'1':stop.set()
        run(n=3,nomes=('PRD','PRD'),stop=stop,extra=extra,checkpoints=snaps)
        atomic_json(self.root/f'checkpoint_{RID}.json',snaps[-1])
        with patch('web.server.threading.Thread') as worker:
            self.assertEqual(self.client.post('/api/retomar/'+RID).status_code,200)
            p=worker.call_args.kwargs['args'][0];self.assertEqual((p['nome_a'],p['nome_b']),('PRD_A','PRD_B'))
            self.assertEqual((p['url_a'],p['url_b']),(A,B))
        legacy={'id':RID,'ambientes':{'PRD':A,'HOMOL':B},'divergencias':[],'paginas':{'PRD':1,'HOMOL':1}}
        atomic_json(self.root/f'comparacao_{RID}.json',legacy)
        self.assertEqual(self.client.get('/api/relatorio/'+RID).get_json()['ambientes'],legacy['ambientes'])

    def test_evidencias_novos_nomes_legados_e_path_traversal(self):
        d=self.root/f'evidencias_{RID}';d.mkdir()
        for suffix in ('','_PRD','_DES','_LAB','_HOMOL','_PRD_A','_PRD_B'):
            path=d/('DIV-0001'+suffix+'.png');path.write_bytes(b'imagem ficticia'+suffix.encode())
            resp=self.client.get(f'/evidencia/{RID}/{path.name}')
            self.assertEqual(resp.status_code,200);self.assertEqual(resp.data,path.read_bytes());resp.close()
        for nome in ('DIV-0001_PRD_C.png','DIV-0001_PRD_A.png.tmp','../segredo','DIV-0001_PRD_A.svg'):
            self.assertIn(self.client.get(f'/evidencia/{RID}/{nome}').status_code,(400,404))


class PRDBrowserTests(unittest.TestCase):
    setUp=fixtures17.BrowserUI17Tests.setUp

    def test_seletores_e_payload_sem_mudanca_visual_da_base(self):
        self.assertEqual(self.p.locator('#nome-b option').evaluate_all('els=>els.map(e=>e.value)'),['DES','LAB','HOMOL','PRD'])
        self.assertEqual(self.p.locator('#nome-b').input_value(),'DES')
        self.assertEqual(self.p.locator('#nome-a option').evaluate_all('els=>els.map(e=>e.value)'),['PRD','LAB','DES'])
        self.p.locator('#go-compare').click()
        self.p.locator('#nome-b').select_option('PRD')
        self.p.locator('#url-a').fill(A);self.p.locator('#url-b').fill(B)
        from web import server
        for lado,esperado in (('',''),('A','PRD_A'),('B','PRD_B')):
            server.STATE['status']='pronto';self.p.locator('#ambiente-desatualizado').select_option(lado)
            with patch('web.server.threading.Thread') as worker:
                with self.p.expect_response('**/api/comparar'):
                    self.p.locator('#compare-form').evaluate('f=>f.requestSubmit()')
                p=worker.call_args.kwargs['args'][0]
                self.assertEqual(p['ambiente_desatualizado'],esperado)
            self.assertEqual(self.p.locator('#nome-b').input_value(),'PRD')
            self.assertNotIn('PRD_A',self.p.locator('#nome-b').text_content())

    def test_relatorio_usa_rotulos_e_mantem_filtro_por_id(self):
        r,_,_=run(n=1,nomes=('PRD','PRD'));r['id']=RID
        atomic_json(self.root/f'comparacao_{RID}.json',r)
        self.p.evaluate('(id)=>openReport(id)',RID)
        self.p.wait_for_function("document.querySelector('#filter-side').textContent.includes('PRD (A)')")
        self.assertIn('PRD (B) — Comparado',self.p.locator('#section-resultados').text_content())
        self.assertEqual(self.p.locator('#filter-side option[value="PRD_A"]').count(),1)


class PRDExportTests(unittest.TestCase):
    def test_capturas_separadas_e_exportacoes_offline_inclusive_pdf(self):
        from playwright.sync_api import sync_playwright
        from test_smart import navegador
        from ambidiff.paired import _salvar_evidencias
        from ambidiff.reports import exportar
        from ambidiff.exports import gerar_pdf
        from ambidiff.storage import selecionar,somente_selecionadas,preparar_relatorio,ler_selecao
        r,_,_=run(n=1,nomes=('PRD','PRD'));r['id']=RID
        with tempfile.TemporaryDirectory() as td,sync_playwright() as pw:
            root=Path(td);browser=navegador(pw)
            class CaptureContext:
                def __init__(self,c):self.c=c
                def __getattr__(self,n):return getattr(self.c,n)
                def new_page(self):
                    p=self.c.new_page()
                    p.route('**/*',lambda route:route.fulfill(content_type='text/html',body='<html><body style="background:'+('red' if route.request.url==A else 'blue')+'"><nav>Portal fictício</nav></body></html>'))
                    return p
            wrapper=NS(new_context=lambda **kw:CaptureContext(browser.new_context(**kw)))
            try:_salvar_evidencias(wrapper,r['divergencias'],root/f'evidencias_{RID}',threading.Event(),lambda _:None,'PRD_A','PRD_B')
            finally:browser.close()
            d=r['divergencias'][0]
            d.update(texto_a='PRD_A',texto_b='PRD_B')  # texto real do portal não é um rótulo de ambiente
            self.assertEqual(set(d['evidencias']),{'PRD_A','PRD_B'})
            self.assertNotEqual((root/d['evidencias']['PRD_A']).read_bytes(),(root/d['evidencias']['PRD_B']).read_bytes())
            paths=exportar(r,root,RID)
            raw=json.loads(Path(paths['json']).read_text());self.assertEqual(raw['ambiente_a']['url'],A)
            self.assertEqual(raw['divergencias'][0]['evidencias'],d['evidencias'])
            with Path(paths['csv']).open(encoding='utf-8-sig') as csv_file:rows=list(csv.DictReader(csv_file,delimiter=';'))
            self.assertEqual(rows[0]['presente_em'],'PRD (A) — Base')
            self.assertEqual(rows[0]['ambiente_b_url'],B)
            self.assertEqual(rows[0]['texto_a'],'PRD_A')
            html=Path(paths['html']).read_text()
            self.assertIn('PRD (A) — Base',html);self.assertIn('PRD (B) — Comparado',html)
            self.assertIn('<b>Texto A:</b> PRD_A',html)
            self.assertIn('<b>Texto B:</b> PRD_B',html)
            self.assertEqual(html.count('data:image/png;base64,'),2)
            gerar_pdf(Path(paths['html']),root/'resultado.pdf')
            self.assertTrue((root/'resultado.pdf').read_bytes().startswith(b'%PDF'))
            selecionar(root,RID,d['id'],True)
            selecionado=somente_selecionadas(preparar_relatorio(root,RID),ler_selecao(root,RID))
            self.assertEqual(selecionado['ambiente_a']['identificador'],'PRD_A')
            self.assertEqual(selecionado['ambiente_b']['url'],B)
