"""v1.5: regressões reais de defasagem editorial, navegação e diagnóstico."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ambidiff.core import Item,Pagina,JS_EXTRAIR
from ambidiff.intelligence import separar_editoriais,agrupar_variacoes
from ambidiff.diagnostics import classificar_erro,montar_diagnostico,exportar_diagnostico
from ambidiff.paired import executar_pareado,e_arquivo,imagem_equivalente
from ambidiff.reports import exportar
from ambidiff.storage import registrar_revisao,preparar_relatorio
from ambidiff.visual import comparar_visuais
from ambidiff.functional import escolher_candidatos

class IntelligenceTests(unittest.TestCase):
    def test_des_antigo_separa_noticia_mas_preserva_menu(self):
        pa=Pagina('https://prd.test/','@inicio','Portal',[],['Página inicial'])
        pb=Pagina('https://des.test/','@inicio','Portal',[],['Página inicial'])
        menu=Item('Opção','ÁUDIOS','ÁUDIOS','Menu',destino='https://prd.test/audios',natureza='estrutura')
        news=Item('Opção','Notícia de hoje','Notícia de hoje','Notícias',destino='https://prd.test/w/hoje',natureza='editorial',entidade='/w/hoje')
        news_des=Item('Opção','Notícia antiga','Notícia antiga','Notícias',destino='https://des.test/w/antiga',natureza='editorial',entidade='/w/antiga')
        comps=[{'tipo':'Opção','presente_em':'PRD','elemento':'ÁUDIOS'},
          {'tipo':'Opção','presente_em':'PRD','elemento':'Notícia de hoje'},
          {'tipo':'Opção','presente_em':'DES','elemento':'Notícia antiga'}]
        principal,data=separar_editoriais(comps,pa,pb,[menu,news],[news_des],('PRD','DES'),'DES')
        self.assertEqual([x['elemento'] for x in principal],['ÁUDIOS'])
        self.assertEqual(len(data),2)
        self.assertEqual(agrupar_variacoes(data,'DES')[0]['quantidade_itens'],2)
        raw,_=separar_editoriais(comps,pa,pb,[menu,news],[news_des],('PRD','DES'),'')
        self.assertEqual(len(raw),3)

    def test_documentos_sem_extensao_e_logo_liferay(self):
        self.assertTrue(e_arquivo('https://prd.test/documents/d/cge/portaria-76'))
        self.assertFalse(e_arquivo('https://prd.test/legislacao-e-jurisprudencia'))
        self.assertTrue(imagem_equivalente('https://prd.test/image/layout_set_logo?img_id=44&t=123',
              'https://des.test/image/layout_set_logo?img_id=44&t=456','https://prd.test/','https://des.test/'))
        self.assertFalse(imagem_equivalente('https://prd.test/image/layout_set_logo?img_id=44&t=123',
              'https://des.test/image/layout_set_logo?img_id=45&t=456','https://prd.test/','https://des.test/'))

    def test_catalogo_erro(self):
        a=classificar_erro('Page.goto: net::ERR_NAME_NOT_RESOLVED')
        self.assertEqual(a['tipo_erro'],'DNS');self.assertFalse(a['causa_confirmada'])
        self.assertEqual(classificar_erro('Page.goto: net::ERR_CERT_AUTHORITY_INVALID')['tipo_erro'],'CERTIFICADO_TLS')
        self.assertEqual(classificar_erro('Download is starting')['tipo_erro'],'DOWNLOAD_DE_DOCUMENTO')
        self.assertEqual(classificar_erro('Timeout 12000ms exceeded')['tipo_erro'],'TIMEOUT')

    def test_salva_arquivos_e_confirmacoes(self):
        with tempfile.TemporaryDirectory() as t:
            td=Path(t);rid='20261021_081730_a6242f'
            r={'site_nome':'Portal CGE','id':rid,'versao':'1.5','ambientes':{'PRD':'https://p.test','DES':'https://d.test'},
               'divergencias':[{'id':'DIV-0004','tipo':'Opção','elemento':'ÁUDIOS','descricao':'Opção encontrada PRD não encontrada DES'}],
               'falhas':[{'ambiente':'PRD','url':'https://p.test/intranet','erro':'ERR_NAME_NOT_RESOLVED'}],
               'meta_varredura':{'PRD':{'visitadas':113,'pendentes':738,'motivo_parada':'Muitas falhas consecutivas'}},
               'situacao_analise':'parcial','paginas':{'PRD':86,'DES':85},
               'avisos_tecnicos':[],'pendencias':[],'referencias_pendentes':[],
               'variacoes_dados':[{'categoria':'Notícias e publicações','quantidade_itens':4}],
               'itens_editoriais_agrupados':14}
            exportar(r,td,rid)
            diag=montar_diagnostico(r,['[PARES] 113'])
            exportar_diagnostico(diag,td,rid)
            self.assertIn('ERR_NAME_NOT_RESOLVED',(td/f'log_{rid}.txt').read_text())
            self.assertEqual(json.loads((td/f'diagnostico_{rid}.json').read_text())['divergencias_preservadas'],1)
            confirmar=registrar_revisao(td,rid,'DIV-0004','confirmada')
            self.assertEqual(confirmar['divergencias'][0]['revisao_manual'],'confirmada')
            self.assertEqual(json.loads((td/f'comparacao_{rid}.json').read_text())['divergencias'][0].get('revisao_manual'),None)
            registrar_revisao(td,rid,'DIV-0004','pendente')
            self.assertNotIn('revisao_manual',preparar_relatorio(td,rid)['divergencias'][0])

    def test_dom_mais_de_uma_estrutura_mas_mesmo_conteudo(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            try:browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            except Exception as ex:self.skipTest('Chromium indisponível: '+str(ex)[:100])
            try:
                page=browser.new_page()
                page.goto('about:blank')
                page.set_content('''<html><body><div class="alert">Aviso: ambiente de desenvolvimento com dados desatualizados</div>
                <nav><a href="https://prd.test/audios">ÁUDIOS</a></nav>
                <section><article class="card"><h3>Notícia recente</h3><p>19/10/2026</p>
                <a href="https://prd.test/w/recente">Notícia recente</a></article></section></body></html>''')
                d=page.evaluate(JS_EXTRAIR)
                self.assertTrue(d['avisos_ambiente'])
                self.assertTrue(any(i['natureza']=='editorial' and i['nome']=='Notícia recente' for i in d['itens']),d['itens'])
                self.assertTrue(any(i['nome']=='ÁUDIOS' and i['natureza']=='estrutura' for i in d['itens']),d['itens'])
            finally:browser.close()

    def test_verificacao_opcional_filtra_links_inseguros(self):
        from ambidiff.core import Item
        pairs=[(Item('Opção','Consultar processo','Consultar processo',destino='https://prd.test/consultar',seletor='a'),
                Item('Opção','Consultar processo','Consultar processo',destino='https://des.test/consultar',seletor='a')),
               (Item('Opção','Excluir processo','Excluir processo',destino='https://prd.test/delete',seletor='b'),
                Item('Opção','Excluir processo','Excluir processo',destino='https://des.test/delete',seletor='b')),
               (Item('Opção','Acessar site externo','Acessar site externo',destino='https://third.test/',seletor='c'),
                Item('Opção','Acessar site externo','Acessar site externo',destino='https://third.test/',seletor='c'))]
        chosen=escolher_candidatos(pairs,'https://prd.test/','https://des.test/')
        self.assertEqual(len(chosen),1)
        self.assertEqual(chosen[0][0].nome,'Consultar processo')

    def test_contempla_icones_svg_distintos(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            try:browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            except Exception as ex:self.skipTest('Chromium indisponível: '+str(ex)[:100])
            try:
                pages=[browser.new_page(),browser.new_page()]
                for p,n in zip(pages,['M1 1','M3 3']):
                    p.set_content('<html><body><main><a href="https://example.org/consulta">Consultar'
                                  '<svg><path d="'+n+'"/></svg></a></main></body></html>')
                pa=Pagina('https://prd.test/','@inicio','Portal',[],['Página inicial'])
                pb=Pagina('https://des.test/','@inicio','Portal',[],['Página inicial'])
                icones,layouts=comparar_visuais(*pages,pa,pb,'PRD','DES',False)
                self.assertEqual(len(icones),1)
                self.assertIn('revisão visual',icones[0]['situacao'])
                self.assertEqual(len(layouts),0)
            finally:browser.close()

    def test_crawler_nao_incrementa_falhas_pelo_documento(self):
        class R:
            status=200
            def __init__(self,url):self.url=url
        def navegar(page,url):
            if '/doc/' in url:raise RuntimeError('Page.goto: Download is starting')
            env='prd.test' if 'prd.test' in url else 'des.test'
            page.set_content('<html><body><nav><a href="https://'+env+'/doc/portaria">Portaria</a><a href="https://'+env+'/pagina">Outra página</a></nav></body></html>')
            return R(url)
        with patch('ambidiff.paired._abrir',side_effect=navegar),patch('ambidiff.paired._MAX_EVIDENCIAS',0):
            r=executar_pareado('https://prd.test/','https://des.test/','PRD','DES',
                 threading.Event(),lambda _:None,lambda _:None,site_nome='Teste CGE')
        self.assertIn(r['situacao_analise'],('concluido','parcial'))
        self.assertFalse(r['meta_varredura']['PRD']['motivo_parada'])
        self.assertGreaterEqual(r['paginas']['PRD'],2)

if __name__=='__main__':unittest.main()
