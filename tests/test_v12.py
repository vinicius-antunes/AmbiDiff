"""Testes de regressão da v1.2: destinos diferentes nunca são percorridos."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import threading
import tempfile
import unittest
from ambidiff.core import Item, Pagina
from ambidiff.paired import (link_equivalente, e_arquivo, _link_pairs,
                             _diff_destino, agrupar_registros, executar_pareado)


class TestsV12(unittest.TestCase):
    def test_urls_equivalentes_ambientes_distintos(self):
        self.assertTrue(link_equivalente('https://prd.gov.br/inicio?id=1',
                       'https://des.gov.br/inicio?id=1','https://prd.gov.br/','https://des.gov.br/'))
        self.assertFalse(link_equivalente('https://prd.gov.br/inicio?id=1',
                       'https://des.gov.br/inicio?id=2','https://prd.gov.br/','https://des.gov.br/'))
        self.assertFalse(link_equivalente('https://setasc.mt.gov.br/a',
                       'https://setasc.mt.gov.br/b','https://prd.mt.gov.br','https://des.mt.gov.br'))
        self.assertTrue(link_equivalente('https://setasc.mt.gov.br/a',
                       'https://setasc.mt.gov.br/a','https://prd.mt.gov.br','https://des.mt.gov.br'))

    def test_pdfs_liferay_nao_sao_paginas_html(self):
        self.assertTrue(e_arquivo('https://site.gov.br/documents/1/3/arquivo.pdf/uuid'))
        self.assertTrue(e_arquivo('https://site.gov.br/planilha.xlsx'))
        self.assertFalse(e_arquivo('https://site.gov.br/servicos'))

    def test_destinos_e_descricao(self):
        a=Pagina('https://prd.gov.br/','@inicio','Portal',[Item('Opção','Consultar','Consultar','Conselhos',
           'https://setasc.mt.gov.br/conselhos1','Menu lateral')],['Página inicial'])
        b=Pagina('https://des.gov.br/','@inicio','Portal',[Item('Opção','Consultar','Consultar','Conselhos',
           'https://setasc.mt.gov.br/conselhos2','Menu lateral')],['Página inicial'])
        pares=_link_pairs(a,b)
        self.assertEqual(len(pares),1)
        reg=_diff_destino(a,b,*pares[0],'PRD','DES')
        self.assertEqual(reg['categoria'],'Links e redirecionamentos')
        self.assertIn('NÃO foram percorridos',reg['descricao'])
        self.assertIn('conselhos1',reg['destino_a'])

    def test_agrupamento_mesma_imagem(self):
        item={'tipo':'Imagem','elemento':'Radar','presente_em':'PRD','local':'Rodapé','posicao':'Rodapé',
             'url_presente':'https://prd.gov.br/','url_comparada':'https://des.gov.br/','caminho':'Início',
             'descricao':'Imagem não identificada'}
        outro={**item,'url_presente':'https://prd.gov.br/outro','url_comparada':'https://des.gov.br/outro',
               'caminho':'Início → Outro'}
        agrupados=agrupar_registros([item,outro,item])
        self.assertEqual(len(agrupados),1)
        self.assertEqual(agrupados[0]['ocorrencias_total'],2)

    def test_nao_agrupar_destinos_distintos(self):
        base={'tipo':'Redirecionamento','elemento':'Consultar','presente_em':'PRD',
             'local':'Conselhos','posicao':'Menu lateral','destino_a':'https://a.test/1',
             'destino_b':'https://b.test/2','descricao':'x'}
        self.assertEqual(len(agrupar_registros([base,{**base,'destino_a':'https://a.test/3'}])),2)

    def test_fluxo_nao_entra_no_link_diferente(self):
        # Substitui só a navegação por HTML em memória; valida o motor real.
        from unittest.mock import patch
        visitados=[]
        class Resposta:
            status=200
            def __init__(self,url):self.url=url
        def abrir(page,url):
            visitados.append(url)
            suf='um' if 'prd.test' in url else 'dois'
            base='<base href="'+url+'">'
            if url.endswith('/igual'):
                html='<html><head>'+base+'<title>Igual</title></head><body><h1>Igual</h1><p>Texto igual</p></body></html>'
            else:
                html='<html><head>'+base+'<title>Órgão Demo</title></head><body><main><h1>Órgão Demo</h1><nav><a href="/igual">Página igual</a><a href="https://externo.test/'+suf+'">Consultar conselho</a></nav></main></body></html>'
            page.set_content(html)
            return Resposta(url)
        with patch('ambidiff.paired._abrir',side_effect=abrir):
            d=executar_pareado('https://prd.test/','https://des.test/','PRD','DES',threading.Event(),
                               lambda x:None,lambda x:None,site_nome='Órgão Demo')
        regs=[x for x in d['divergencias'] if x['tipo']=='Redirecionamento']
        self.assertEqual(len(regs),1,d['divergencias'])
        self.assertEqual(d['paginas']['PRD'],2)
        self.assertEqual(d['paginas']['DES'],2)
        self.assertFalse(any('externo.test' in x for x in visitados))
        self.assertIn('externo.test/um',regs[0]['destino_a'])
        self.assertIn('https://des.test/igual',visitados)


if __name__=='__main__':unittest.main()
