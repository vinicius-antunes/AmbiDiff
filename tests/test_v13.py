"""Regressões da v1.3 com páginas HTML em memória, sem acessar portais externos."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ambidiff.core import Item, Pagina, JS_EXTRAIR
from ambidiff.paired import (link_equivalente, diferencas_de_ordem,
    _alinhamento_de_componentes, executar_pareado)
from ambidiff.reports import exportar

class V13(unittest.TestCase):
    A='https://prd.test/'
    B='https://des.test/'
    def test_links_literalmente_iguais_em_prd_e_des(self):
        # Caso real que gerou 72 falsos positivos na versão 1.2.
        x='https://www.transparencia.mt.gov.br/glossario'
        self.assertTrue(link_equivalente(x,x,'https://www.transparencia.mt.gov.br/',
             'https://transparencia.des.mt.gov.br/'))
        self.assertTrue(link_equivalente('https://prd.test/x?p=1','https://des.test/x?p=1',self.A,self.B))
        self.assertFalse(link_equivalente('https://prd.test/x?p=1','https://des.test/x?p=2',self.A,self.B))
        self.assertFalse(link_equivalente('https://external.test/um','https://external.test/dois',self.A,self.B))

    def test_ordem_trocada_gera_uma_div(self):
        ma={'nome':'Compras','posicao':'Conteúdo central','seletor':'#compras',
            'opcoes':['Licitações','Plano anual','Pregões encerrados']}
        mb={**ma,'opcoes':['Plano anual','Licitações','Pregões encerrados']}
        a=Pagina(self.A,'','Portal',[],['Página inicial','Compras'],[],[ma])
        b=Pagina(self.B,'','Portal',[],['Página inicial','Compras'],[],[mb])
        ds=diferencas_de_ordem(a,b)
        self.assertEqual(len(ds),1)
        self.assertEqual(ds[0]['categoria'],'Ordem das opções')
        self.assertIn('1ª em PRD, 2ª em DES',ds[0]['descricao'])
        self.assertEqual(len(diferencas_de_ordem(a,a)),0)

    def test_ordem_nao_chama_ausencia_quando_lista_diferente(self):
        m1={'nome':'Compras','posicao':'Conteúdo central','opcoes':['Edital','Plano anual']}
        m2={'nome':'Compras','posicao':'Conteúdo central','opcoes':['Edital','Atas']}
        a=Pagina(self.A,'','Portal',[],[],[],[m1]);b=Pagina(self.B,'','Portal',[],[],[],[m2])
        self.assertEqual(diferencas_de_ordem(a,b),[])

    def test_imagens_mesmo_elemento_nomes_diferentes(self):
        path='#cabecalho > div > a:nth-of-type(1) > img'
        ia=Item('Imagem','ba550d','ba550d','Cabeçalho','https://prd.test/img/radar.png','Cabeçalho',path,False)
        ib=Item('Imagem','Radar da Transparência','Radar da Transparência','Cabeçalho','https://des.test/img/radar.png','Cabeçalho',path,False)
        a=Pagina(self.A,'','Portal',[ia]);b=Pagina(self.B,'','Portal',[ib])
        aa,bb,pend=_alinhamento_de_componentes(a,b,self.A,self.B)
        self.assertEqual((aa,bb,pend),([],[],[]))
        ib.destino='https://des.test/img/outra.png'
        aa,bb,pend=_alinhamento_de_componentes(a,b,self.A,self.B)
        self.assertEqual((aa,bb),([],[]))
        self.assertEqual(len(pend),1)
        self.assertEqual(pend[0]['tipo'],'Imagem')

    def test_nao_contar_imagem_com_link_aria_duas_vezes(self):
        p='#cabecalho > a'
        a=Pagina(self.A,'','P',[Item('Opção','a','Radar','Cabeçalho','https://setasc.test/conselhos','Cabeçalho',p,False,True)])
        b=Pagina(self.B,'','P',[Item('Opção','b','Acessar Radar','Cabeçalho','https://setasc.test/conselhos','Cabeçalho',p,False,True)])
        aa,bb,pend=_alinhamento_de_componentes(a,b,self.A,self.B)
        self.assertEqual((aa,bb,pend),([],[],[]))

    def test_relatorio_exportado_busca_e_copia(self):
        dados={'site_nome':'Portal','divergencias':[{'id':'DIV-0033','categoria':'Ordem das opções',
            'tipo':'Ordem','ocorrencias_total':1,'descricao':'Ordem diferente',
            'ordem_a':['Primeiro','Segundo'],'ordem_b':['Segundo','Primeiro']}],
            'paginas':{'PRD':1,'DES':1},'situacao_analise':'concluido',
            'avisos_tecnicos':[],'falhas':[],'pendencias':[]}
        with tempfile.TemporaryDirectory() as d:
            fname=exportar(dados,Path(d),'test')['html']
            html=Path(fname).read_text(encoding='utf-8')
            self.assertIn('data-div-id="DIV-0033"',html)
            self.assertIn('Copiar ID',html)
            self.assertIn('Pesquisar divergência por ID',html)
            self.assertIn('Ordem A',html)

    def test_extracao_da_ordem_do_dom_e_crawler(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            try:browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            except Exception as e:self.skipTest('Chromium de testes indisponível: '+str(e)[:100])
            try:
                page=browser.new_page()
                page.set_content('<html><body><nav aria-label="Serviços"><ul><li><a href="/um">Um</a></li><li><a href="/dois">Dois</a></li><li><a href="/tres">Três</a></li></ul></nav></body></html>')
                d=page.evaluate(JS_EXTRAIR)
                self.assertTrue(any(x['opcoes']==['Um','Dois','Três'] for x in d['menus']),d['menus'])
            finally:browser.close()

    def test_crawler_registra_ordem_alterada_sem_diferencas_de_destino(self):
        from unittest.mock import patch
        class R:
            status=200
            def __init__(self,url):self.url=url
        def fake(page,url):
            env='prd.test' if 'prd.test' in url else 'des.test'
            labels=['Editais','Pregões','Planos'] if env=='prd.test' else ['Pregões','Editais','Planos']
            links=''.join(f'<li><a href="https://{env}/{x.lower()}">{x}</a></li>' for x in labels)
            page.set_content('<html><body><nav aria-label="Compras"><ul>'+links+'</ul></nav></body></html>' if url.endswith('/')
                             else '<html><body><h1>Documento</h1></body></html>')
            return R(url)
        with patch('ambidiff.paired._abrir',side_effect=fake):
            d=executar_pareado(self.A,self.B,'PRD','DES',threading.Event(),lambda _:None,lambda _:None,site_nome='Portal')
        order=[r for r in d['divergencias'] if r['tipo']=='Ordem']
        self.assertEqual(len(order),1,d['divergencias'])
        self.assertEqual(order[0]['ordem_b'],['Pregões','Editais','Planos'])
        self.assertFalse([r for r in d['divergencias'] if r['tipo']=='Redirecionamento'])

    def test_simulacao_destinos_iguais_nao_gera_falso_positivo(self):
        # Inicia com dois domínios distintos e um link para uma URL PRD exata em ambos.
        v=[]
        class R:
            status=200
            def __init__(self,url):self.url=url
        def fake(page,url):
            v.append(url)
            page.set_content('<html><body><nav><a href="https://prd.test/glossario">Glossário</a></nav></body></html>')
            return R(url)
        with patch('ambidiff.paired._abrir',side_effect=fake):
            d=executar_pareado(self.A,self.B,'PRD','DES',threading.Event(),lambda _:None,lambda _:None,site_nome='Demo')
        self.assertEqual([r for r in d['divergencias'] if r['tipo']=='Redirecionamento'],[])
        self.assertEqual(d['versao'],'1.5')

if __name__=='__main__':unittest.main()
