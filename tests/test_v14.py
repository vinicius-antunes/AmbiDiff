"""Regressões da v1.4: exclusões persistentes, exports filtrados e duas capturas."""
from __future__ import annotations
import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
import sys
import unittest
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ambidiff.storage import (atomic_json,ler_original,preparar_relatorio,
    excluir_div,excluir_execucoes)
from ambidiff.paired import _preparar_conteudo,_salvar_evidencias
from ambidiff.reports import exportar

ID1='20261020_131357_ac942d'
ID2='20261020_130933_730bd6'


def fixture(tmp):
    raw={'versao':'1.4','site_nome':'Marketplace','ambientes':{'PRD':'https://prd.test/','DES':'https://des.test/'},
        'divergencias':[{'id':'DIV-0001','tipo':'Texto','categoria':'Textos','descricao':'A',
                        'ocorrencias_total':1,'elemento':'Teste A'},
                       {'id':'DIV-0002','tipo':'Imagem','categoria':'Imagens e banners','descricao':'B',
                        'ocorrencias_total':1,'elemento':'Teste B'}],
        'situacao_analise':'concluido','paginas':{'PRD':2,'DES':2},'avisos_tecnicos':[],
        'pendencias':[],'referencias_pendentes':[],'falhas':[]}
    exportar(raw,tmp,ID1)
    exportar({**raw,'divergencias':[raw['divergencias'][0]]},tmp,ID2)
    hist=[{'id':ID1,'site_nome':'Marketplace','total':2},
          {'id':ID2,'site_nome':'Transparência','total':1}]
    atomic_json(tmp.parent/'historico.json',hist)
    return raw

class StorageTests(unittest.TestCase):
    def test_div_persiste_sem_modificar_bruto(self):
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)/'relatorios';tmp.mkdir();raw=fixture(tmp)
            assert excluir_div(tmp,ID1,'DIV-0001')['divergencias_ocultadas']==1
            self.assertEqual([x['id'] for x in ler_original(tmp,ID1)['divergencias']],['DIV-0001','DIV-0002'])
            self.assertEqual([x['id'] for x in preparar_relatorio(tmp,ID1)['divergencias']],['DIV-0002'])
            self.assertEqual(len(preparar_relatorio(tmp,ID2)['divergencias']),1)
            # Retirar a mesma DIV duas vezes não remove outros registros.
            excluir_div(tmp,ID1,'DIV-0001')
            self.assertEqual(len(preparar_relatorio(tmp,ID1)['divergencias']),1)
            with self.assertRaises(KeyError):excluir_div(tmp,ID1,'DIV-0099')

    def test_delete_execucao_remove_so_arqs_proprios(self):
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)/'relatorios';tmp.mkdir();fixture(tmp)
            (tmp/f'evidencias_{ID1}').mkdir()
            (tmp/f'evidencias_{ID1}'/'DIV-0001_PRD.png').write_bytes(b'a')
            excluir_div(tmp,ID1,'DIV-0001')
            total=excluir_execucoes(tmp,Path(d)/'historico.json',[ID1])
            self.assertEqual(total,1)
            self.assertFalse((tmp/f'evidencias_{ID1}').exists())
            self.assertFalse((tmp/f'comparacao_{ID1}.json').exists())
            self.assertTrue((tmp/f'comparacao_{ID2}.json').exists())
            self.assertEqual(json.loads((Path(d)/'historico.json').read_text())[0]['id'],ID2)

    def test_validacao_impede_travessia_e_lote_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)/'relatorios';tmp.mkdir();fixture(tmp)
            with self.assertRaises(ValueError):excluir_div(tmp,ID1,'../../a')
            with self.assertRaises(ValueError):excluir_execucoes(tmp,Path(d)/'historico.json',['../../a'])
            self.assertTrue((tmp/f'comparacao_{ID1}.json').exists())

    @unittest.skipUnless(__import__("importlib").util.find_spec("flask"),"Flask não está disponível no ambiente de testes")
    def test_api_delete_div_e_export_filtered(self):
        from web import server
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)/'relatorios';tmp.mkdir();fixture(tmp)
            with patch.object(server,'PASTA',tmp),patch.object(server,'HISTORY_PATH',Path(d)/'historico.json'):
                with server.LOCK:server.STATE['status']='pronto'
                client=server.app.test_client()
                res=client.delete(f'/api/relatorio/{ID1}/divergencias/DIV-0001')
                self.assertEqual(res.status_code,200,res.json)
                self.assertEqual(res.json['total'],1)
                self.assertEqual(len(client.get(f'/api/relatorio/{ID1}').json['divergencias']),1)
                history=client.get('/api/historico').json
                self.assertEqual(history[0]['total'],1)
                csv=client.get(f'/download/{ID1}/csv')
                self.assertEqual(csv.status_code,200)
                self.assertNotIn('DIV-0001',csv.get_data(as_text=True))
                self.assertIn('DIV-0002',csv.get_data(as_text=True))
                html=client.get(f'/download/{ID1}/html')
                self.assertNotIn('DIV-0001',html.get_data(as_text=True))
                self.assertEqual(len(ler_original(tmp,ID1)['divergencias']),2)

    @unittest.skipUnless(__import__("importlib").util.find_spec("flask"),"Flask não está disponível no ambiente de testes")
    def test_api_bulk_delete_confirma_especificos(self):
        from web import server
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)/'relatorios';tmp.mkdir();fixture(tmp)
            with patch.object(server,'PASTA',tmp),patch.object(server,'HISTORY_PATH',Path(d)/'historico.json'):
                with server.LOCK:server.STATE['status']='pronto'
                client=server.app.test_client()
                self.assertEqual(client.post('/api/relatorios/excluir',json={'ids':[ID1]}).status_code,200)
                self.assertEqual(client.get(f'/api/relatorio/{ID1}').status_code,404)
                self.assertEqual(client.get(f'/api/relatorio/{ID2}').status_code,200)

class BrowserTests(unittest.TestCase):
    def browser(self,pw):
        try:return pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        except Exception as e:self.skipTest('Chromium indisponível: '+str(e)[:100])

    def test_rolagem_ativa_elemento_lazy(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser=self.browser(pw)
            try:
                page=browser.new_page(viewport={'width':1100,'height':700})
                page.set_content('''<body style="height:2700px"><div id="lazy"></div><script>
                window.addEventListener('scroll',()=>{if(window.scrollY>1100)
                document.getElementById('lazy').innerHTML='<p>Texto carregado ao rolar</p>';});
                </script></body>''')
                stats=_preparar_conteudo(page,lambda _:None,delay=80)
                self.assertGreater(stats['passos_rolagem'],0)
                self.assertIn('Texto carregado ao rolar',page.locator('body').inner_text())
            finally:browser.close()

    def test_par_de_capturas_identifica_ambiente(self):
        # As políticas locais bloqueiam navegação até para URLs simuladas;
        # validamos os dois arquivos e os metadados sem requisições de rede.
        class Loc:
            def count(self):return 1
            def is_visible(self,timeout):return True
            def scroll_into_view_if_needed(self,timeout):pass
            def evaluate(self,script):pass
        class Page:
            def goto(self,url,wait_until,timeout):return None
            def wait_for_timeout(self,t):pass
            def locator(self,selector):return self
            @property
            def first(self):return Loc()
            def evaluate(self,code):return 40
            def screenshot(self,path,timeout,animations,full_page):Path(path).write_bytes(b'fake-image')
        class Context:
            def route(self,pattern,handler):self.navigation_policy=handler
            def new_page(self):return Page()
            def close(self):pass
        class FakeBrowser:
            def new_context(self,**kw):return Context()
        with tempfile.TemporaryDirectory() as d:
            rows=[{'id':'DIV-0001','tipo':'Texto','presente_em':'PRD','nao_identificado_em':'DES',
                   'url_presente':'https://prd.test/','url_comparada':'https://des.test/',
                   'seletor':'#target'}]
            _salvar_evidencias(FakeBrowser(),rows,Path(d)/('evidencias_'+ID1),
                              threading.Event(),lambda _:None,'PRD','DES')
            self.assertEqual(set(rows[0]['evidencias']),{'PRD','DES'})
            for env in ('PRD','DES'):
                self.assertTrue((Path(d)/rows[0]['evidencias'][env]).is_file())

    def test_export_html_contendo_duas_capturas(self):
        import base64
        image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg==')
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);(folder/f'evidencias_{ID1}').mkdir()
            for env in ('PRD','DES'):
                (folder/f'evidencias_{ID1}'/f'DIV-0001_{env}.png').write_bytes(image)
            row={'id':'DIV-0001','tipo':'Texto','descricao':'Teste','evidencias':{
                 env:f'evidencias_{ID1}/DIV-0001_{env}.png' for env in ('PRD','DES')}}
            dados={'site_nome':'Demo','ambientes':{'PRD':'a','DES':'b'},'paginas':{'PRD':1,'DES':1},
                   'divergencias':[row],'avisos_tecnicos':[],'pendencias':[]}
            filename=exportar(dados,folder,ID1)['html']
            html=Path(filename).read_text()
            self.assertIn('capture-grid',html)
            self.assertIn('alt="Captura de PRD',html)
            self.assertIn('alt="Captura de DES',html)

if __name__=='__main__':unittest.main()
