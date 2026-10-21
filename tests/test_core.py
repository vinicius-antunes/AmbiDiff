import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ambidiff.core import (Item,Pagina,comparacao,comparar_sites,permitido,referencia_invalida,
                           referencias_suspeitas,url_limpa,chave_caminho,validacao_inicial,coletar_site)
from ambidiff.reports import exportar

class TestAmbiDiff(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(url_limpa('https://PRD.gov.br/a/?utm_source=x&z=2#x'),'https://prd.gov.br/a?z=2')
        self.assertTrue(permitido('https://prd.gov.br/a/detalhe','https://prd.gov.br/a'))
        self.assertFalse(permitido('https://externo.gov.br/a','https://prd.gov.br/a'))
        self.assertFalse(permitido('https://prd.gov.br/abc','https://prd.gov.br/a'))
        self.assertFalse(permitido('https://prd.gov.br/a/doc.pdf','https://prd.gov.br/a'))
        with self.assertRaises(ValueError):validacao_inicial('https://site.com','https://site.com')
    def test_chave(self):
        self.assertEqual(chave_caminho('https://prd.gov.br/portal/detalhes','https://prd.gov.br/portal'),
                         chave_caminho('https://lab.gov.br/portal/detalhes','https://lab.gov.br/portal'))
    def test_liferay_json_em_href_nao_e_pagina(self):
        self.assertTrue(referencia_invalida('https://lab.gov.br/%7B%22groupId%22:123,%22uuid%22:%22abc%22%7D'))
        self.assertFalse(permitido('https://lab.gov.br/%7B%22groupId%22:123%7D','https://lab.gov.br/'))
    def test_dois_sentidos(self):
        a=Pagina('https://prd.gov.br/','@inicio','Home',[Item('Opção','Serviço 1','Serviço 1'),Item('Imagem','logo','logo')],['Página inicial'])
        b=Pagina('https://lab.gov.br/','@inicio','Home',[Item('Opção','Serviço 2','Serviço 2'),Item('Imagem','logo','logo')],['Página inicial'])
        divergencias,pendencias,referencias=comparar_sites({'@inicio':a},{'@inicio':b})
        self.assertEqual(len(divergencias),2)
        self.assertEqual({i['presente_em'] for i in divergencias},{'PRD','LAB'})
        self.assertTrue(all(i['url_presente'].startswith('https') for i in divergencias))
        self.assertFalse(pendencias)
        self.assertFalse(referencias)
    def test_detalhe_caminho(self):
        a=Pagina('https://prd.gov.br/documentos','documentos','Documentos',
                 [Item('Documento','Manual','Manual','Legislação','https://prd.gov.br/manual.pdf')],
                 ['Página inicial','Serviços','Documentos'])
        b=Pagina('https://lab.gov.br/documentos','documentos','Documentos',[],['Página inicial','Serviços','Documentos'])
        r,_,_=comparar_sites({'documentos':a},{'documentos':b})
        self.assertEqual(len(r),1)
        self.assertIn('Página inicial → Serviços → Documentos → Legislação',r[0]['caminho'])
        self.assertIn('https://prd.gov.br/documentos',r[0]['url_presente'])
        self.assertIn('https://lab.gov.br/documentos',r[0]['url_comparada'])
    def test_imagens_ou_documentos_url_diferente_so_pendencia(self):
        a=Pagina('https://prd.gov.br/','@inicio','Home',[Item('Imagem','Banner','Banner',destino='https://prd.gov.br/a.jpg')])
        b=Pagina('https://lab.gov.br/','@inicio','Home',[Item('Imagem','Banner','Banner',destino='https://lab.gov.br/b.jpg')])
        r,p,refs=comparar_sites({'@inicio':a},{'@inicio':b})
        self.assertEqual(len(r),0)
        self.assertEqual(len(refs),1)
        self.assertEqual(refs[0]['tipo'],'Imagem')
    def test_sem_pareamento_nao_gera_divergencia(self):
        a=Pagina('https://prd.gov.br/a','a','FAQ',[])
        r,p,_=comparar_sites({'a':a},{})
        self.assertFalse(r)
        self.assertFalse(p) # não há coleta no outro ambiente, logo não há alegação de ausência
        b=Pagina('https://lab.gov.br/','@inicio','Inicial',[])
        r,p,_=comparar_sites({'a':a},{'@inicio':b})
        self.assertFalse(r)
        self.assertEqual(len(p),2)
    def test_textos_parecidos_sao_uma_divergencia(self):
        a=Pagina('https://a.test','@inicio','Site',[Item('Texto','Informações sobre serviços públicos','Informações sobre serviços públicos','Serviços')])
        b=Pagina('https://b.test','@inicio','Site',[Item('Texto','Informações sobre serviço público','Informações sobre serviço público','Serviços')])
        r,_,_=comparar_sites({'@inicio':a},{'@inicio':b})
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['situacao'],'Texto diferente')
        self.assertIn('texto_b',r[0])
    def test_export_seguro(self):
        d={'site_nome':'Portal','paginas':{'PRD':1,'LAB':1},'falhas':[],
           'avisos_tecnicos':[],'pendencias':[],'referencias_pendentes':[],
           'situacao_analise':'parcial','gerado_em':'20/10/2026 10:00',
           'divergencias':[{'id':'DIV-0001','tipo':'Texto','presente_em':'PRD',
            'nao_identificado_em':'LAB','pagina':'A','url_presente':'https://prd.gov.br/',
            'url_comparada':'https://lab.gov.br/','local':'Página','caminho':'Início → Serviços',
            'elemento':'=2+2','descricao':'=HYPERLINK("https://malicious.test")','situacao':'Revisão'}]}
        with tempfile.TemporaryDirectory() as td:
            files=exportar(d,Path(td),'test')
            with open(files['csv'],encoding='utf-8-sig') as f:
                item=next(csv.DictReader(f,delimiter=';'))
                self.assertTrue(item['descricao'].startswith("'="))
            self.assertIn('Início → Serviços',Path(files['html']).read_text(encoding='utf-8'))
            self.assertEqual(json.loads(Path(files['json']).read_text(encoding='utf-8'))['site_nome'],'Portal')
    def test_html_escape(self):
        dados={'site_nome':'<script>alert(1)</script>','paginas':{'PRD':0,'LAB':1},'falhas':[],
            'avisos_tecnicos':[],'pendencias':[],'referencias_pendentes':[],
            'situacao_analise':'inconclusivo','gerado_em':'20/10/2026','divergencias':[]}
        with tempfile.TemporaryDirectory() as td:
            files=exportar(dados,Path(td),'test')
            html=Path(files['html']).read_text(encoding='utf-8')
            self.assertIn('&lt;script&gt;',html)
            self.assertNotIn('<script>alert(1)</script>',html)


class FakeServer(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/':
            html='''<!doctype html><html><title>Portal Institucional</title><body>
            <h1>Portal Institucional</h1>
            <a href="/servicos">Serviços</a><a href="/%7B%22groupId%22:5%7D">Doc JSON</a>
            <a href="/servicos">Serviços repetidos</a></body></html>'''
        elif self.path=='/servicos':
            html='''<!doctype html><html><title>Serviços</title><body>
            <h1>Serviços</h1><p>Consulte os documentos disponíveis.</p>
            <a href="/">Início</a></body></html>'''
        else:
            self.send_response(404);self.end_headers();return
        raw=html.encode('utf-8')
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def log_message(self,*args):pass

class TestLocalCrawl(unittest.TestCase):

    def test_extracao_js_com_pagina_em_memoria(self):
        from playwright.sync_api import sync_playwright
        from ambidiff.core import JS_EXTRAIR
        with sync_playwright() as pw:
            try:browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            except Exception as e:self.skipTest('Chromium de testes indisponível: '+str(e)[:120])
            try:
                page=browser.new_page()
                page.set_content('<html><head><title>Exemplo</title></head><body><main><h1>Serviços</h1><p>Manual disponível para consulta.</p><a href="https://prd.gov.br/manual.pdf">Manual PDF</a></main></body></html>')
                dados=page.evaluate(JS_EXTRAIR)
                self.assertEqual(dados['title'],'Exemplo')
                self.assertTrue(any(x['tipo']=='Documento' and x['nome']=='Manual PDF' for x in dados['itens']))
                self.assertTrue(any(x['tipo']=='Texto' for x in dados['itens']))
                self.assertEqual(dados['links'][0]['label'],'Manual PDF')
            finally:browser.close()

    def test_crawler_todas_paginas_e_sem_json_falso(self):
        from playwright.sync_api import sync_playwright
        serv=ThreadingHTTPServer(('127.0.0.1',0),FakeServer)
        th=threading.Thread(target=serv.serve_forever,daemon=True);th.start()
        try:
            base=f'http://127.0.0.1:{serv.server_port}/'
            with sync_playwright() as pw:
                try:browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
                except Exception as e:self.skipTest('Chromium local não disponível: '+str(e)[:100])
                try:
                    pg,fail,full,meta=coletar_site(browser,base,threading.Event(),lambda _:None,lambda _:None,'PRD')
                    if fail and 'ERR_BLOCKED_BY_ADMINISTRATOR' in fail[0].get('erro',''):
                        self.skipTest('Política de rede do navegador neste ambiente bloqueia HTTP local')
                    self.assertEqual(len(pg),2)
                    self.assertFalse(fail)
                    self.assertTrue(full)
                    self.assertGreaterEqual(meta['referencias_excluidas'].get('Referências codificadas não navegáveis',0),1)
                    self.assertIn('Serviços',pg['servicos'].trilha)
                finally:browser.close()
        finally:serv.shutdown();serv.server_close()

if __name__=='__main__':unittest.main()
