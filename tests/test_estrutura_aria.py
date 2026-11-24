"""Regressões estruturais com Chromium e HTML local."""
from dataclasses import asdict
import threading
import unittest

from playwright.sync_api import sync_playwright

from ambidiff.checkpoints import restaurar_pagina
from ambidiff.paired import _extrair_page, _link_pairs, executar_pareado
from ambidiff.relevance import classificar
from ambidiff.smart import Inteligencia, Metricas
from fixtures_aria import DIFERENCAS, EQUIVALENTES, pagina_aria, portais_aria


BASES = ('https://prd.test/', 'https://des.test/')


def palavras(itens):
    return {i.nome for i in itens}


class EstruturaARIATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.addClassCleanup(cls.pw.stop)
        cls.browser = cls.pw.chromium.launch()
        cls.addClassCleanup(cls.browser.close)

    def coletar(self, html, base, profunda=False):
        with self.browser.new_page() as page:
            page.set_content(f'<base href="{base}">'+html)
            pg = _extrair_page(page, base, ['Início'], lambda _: None, profunda=profunda)
            return pg, page.evaluate('!!window.escrita')

    def test_menu_rotulos_e_listagem_sem_criar_destino_para_role_link(self):
        a, _ = self.coletar(pagina_aria('PRD'), BASES[0])
        b, _ = self.coletar(pagina_aria('DES'), BASES[1])
        link = next(i for i in b.itens if i.nome == 'Atendimento')
        self.assertEqual(link.semantica['papel'], 'menuitem')
        self.assertEqual(link.semantica['grupo_nome'], 'Serviços públicos')
        self.assertEqual(link.destino, BASES[1]+'servicos')
        self.assertEqual(a.menus[0]['opcoes'][:3], b.menus[0]['opcoes'][:3])
        self.assertNotEqual(a.menus[0]['posicao'], b.menus[0]['posicao'])
        self.assertTrue(DIFERENCAS <= palavras(a.itens))
        self.assertNotIn('ÁUDIOS', palavras(b.itens))
        html = '<nav><span role="link" tabindex="0" aria-label="Serviço sem href"></span></nav>'
        pg, _ = self.coletar(html, BASES[0])
        item = pg.itens[0]
        self.assertFalse(item.destino)
        self.assertIn('destino', item.semantica['invalidos'])
        self.assertFalse(pg.links)

    def test_nome_associado_invalido_hidden_e_inerte(self):
        pg, _ = self.coletar(pagina_aria('DES'), BASES[1])
        itens = {i.nome: i for i in pg.itens}
        prefer = itens['Preferências do portal']
        self.assertFalse(prefer.visivel_texto)
        self.assertEqual(prefer.semantica['origem'], 'aria-labelledby')
        self.assertIn('labelledby', itens['Rótulo inválido'].semantica['invalidos'])
        self.assertIn('foco', itens['Acesso sem foco'].semantica['invalidos'])
        self.assertFalse({'Somente no DOM','Controle inerte','Controle transparente',
                          'Ação do diálogo fechado','Versão responsiva inativa'} & itens.keys())
        original = '<section aria-label="Ferramentas"><label for="x">Preferência acessível</label><input id="x" type="button"></section>'
        pg, _ = self.coletar(original, BASES[0])
        self.assertEqual(pg.itens[0].semantica['origem'], 'label')
        legado = asdict(pg)
        legado['itens'][0].pop('semantica')
        self.assertEqual(restaurar_pagina(legado).itens[0].semantica, {})
        self.assertEqual(restaurar_pagina(asdict(pg)).itens[0].semantica, pg.itens[0].semantica)

    def test_equivalencias_mutuas_e_estados_sem_assumir_funcionamento(self):
        a, _ = self.coletar(pagina_aria('PRD'), BASES[0])
        b, _ = self.coletar(pagina_aria('DES'), BASES[1])
        for pa, pb in ((a,b), (b,a)):
            motor = Inteligencia(Metricas())
            registros = motor.comparar(pa.itens,pb.itens,pa,pb,'A','B',pa.url,pb.url)
            encontrados = {e['elemento'] for e in motor.equivalencias}
            self.assertTrue(EQUIVALENTES <= encontrados, motor.inconclusivos)
            for e in motor.equivalencias:
                self.assertEqual(e['funcionamento'], 'Não comprovado por esta equivalência')
            ambiguos = {e['elemento'] for e in motor.inconclusivos}
            self.assertTrue({'Consultar','Rótulo inválido','Acesso sem foco'} <= ambiguos)
            estados = {r['elemento']:r for r in registros if r['tipo']=='Estado'}
            self.assertIn('expanded', estados['Alternar opções']['descricao'])
            self.assertIn('disabled', estados['Bloqueio parcial']['descricao'])
            self.assertEqual(classificar(estados['Bloqueio parcial'])[0], 'relevante')
            self.assertTrue(any(r['elemento']=='ÁUDIOS' for r in registros))
            pares = {x.nome:(x.destino,y.destino) for x,y in _link_pairs(pa,pb,aceitar_rotulos=True)}
            self.assertIn('Portaria 12', pares)
            self.assertNotEqual(*(x.rsplit('/',1)[1] for x in pares['Rota divergente']))

    def test_inspecao_qualifica_falha_local_e_nao_aciona_controles_proibidos(self):
        a, escrita_a = self.coletar(pagina_aria('PRD'), BASES[0], profunda=True)
        b, escrita_b = self.coletar(pagina_aria('DES'), BASES[1], profunda=True)
        self.assertFalse(escrita_a or escrita_b)
        self.assertIn('Aba "Detalhes tardios"', b.coleta['componentes_nao_inspecionados'])
        motor = Inteligencia(Metricas())
        rows = motor.comparar(a.itens,b.itens,a,b,'PRD','DES',*BASES)
        tardio = next(r for r in rows if r['elemento']=='Conteúdo tardio da aba')
        self.assertEqual(classificar(tardio)[0], 'inconclusivo')
        audio = next(r for r in rows if r['elemento']=='ÁUDIOS')
        self.assertEqual(classificar(audio)[0], 'relevante')

    def test_papel_sem_alvo_conhecido_permanece_inconclusivo(self):
        html = '<div role="tablist" aria-label="Painéis"><button role="tab" aria-controls="duplicado">Preferências</button></div>'
        html += '<div id="duplicado" role="tabpanel"></div><div id="duplicado" role="tabpanel"></div>'
        a, _ = self.coletar(html, BASES[0])
        b, _ = self.coletar(html, BASES[1])
        self.assertIn('controls', a.itens[0].semantica['invalidos'])
        motor = Inteligencia(Metricas())
        motor.comparar(a.itens,b.itens,a,b,'A','B',*BASES)
        self.assertFalse(motor.equivalencias)
        self.assertTrue(motor.inconclusivos)

    def test_menu_responsivo_expoe_apenas_a_variante_visivel(self):
        html = '''<style>@media (max-width:600px){.desktop{display:none}}
          @media (min-width:601px){.mobile{display:none}}</style>
          <nav class="desktop" aria-label="Serviços"><a href="/info">Atendimento</a></nav>
          <div role="navigation" class="mobile" aria-label="Serviços">
            <a role="menuitem" href="/info">Atendimento</a></div>'''
        tipos = []
        for largura, base in zip((1024,375), BASES):
            with self.browser.new_page(viewport={'width':largura,'height':700}) as page:
                page.set_content(f'<base href="{base}">'+html)
                pg = _extrair_page(page, base, [], lambda _: None, profunda=False)
                self.assertEqual([i.nome for i in pg.itens], ['Atendimento'])
                tipos.append(pg.itens[0].semantica['papel'])
        self.assertEqual(tipos, ['link','menuitem'])

    def test_current_e_selected_distintos_com_destinos_consistentes(self):
        html = '''<nav aria-label="Serviços"><a href="/info" {current}>Atendimento</a></nav>
          <div role="tablist" aria-label="Seções"><button role="tab" aria-controls="painel"
          aria-selected="{selected}">Dados do portal</button></div>
          <div role="tabpanel" id="painel" {hidden}><p>Conteúdo do painel</p></div>'''
        a, _ = self.coletar(html.format(current='aria-current="page"',selected='true',hidden=''), BASES[0])
        b, _ = self.coletar(html.format(current='',selected='false',hidden='hidden'), BASES[1])
        motor = Inteligencia(Metricas())
        registros = motor.comparar(a.itens,b.itens,a,b,'A','B',*BASES)
        estados = {r['elemento']:r['descricao'] for r in registros if r['tipo']=='Estado'}
        self.assertIn('current (page / false)', estados['Atendimento'])
        self.assertIn('selected (true / false)', estados['Dados do portal'])


class EstruturaARIAIntegracaoTests(unittest.TestCase):
    def test_sincrono_e_assincrono_preservam_ids_e_classificacoes(self):
        resultados = []
        with portais_aria() as (bases, requisicoes):
            for assincrono in (False, True):
                r = executar_pareado(*bases, 'PRD','DES', threading.Event(), lambda _:None, lambda _:None,
                                     varredura_inteligente=True, navegacao_assincrona=assincrono)
                self.assertEqual(r['andamento']['pares_pendentes'],0)
                self.assertEqual(r['andamento']['pares_com_falha'],0)
                self.assertFalse(any(m=='POST' for _,m,_ in requisicoes))
                divergencias = [(d['id'],d['elemento'],d['tipo'],classificar(d)[0]) for d in r['divergencias']]
                self.assertTrue(any(e=='ÁUDIOS' and c=='relevante' for _,e,_,c in divergencias),divergencias)
                self.assertTrue(any(e=='Rota divergente' and t=='Redirecionamento' for _,e,t,_ in divergencias),divergencias)
                self.assertFalse(any(e=='Rota divergente' and t=='Função' for _,e,t,_ in divergencias),divergencias)
                resultados.append((divergencias, r['estados_pares']))
        self.assertEqual(*resultados)
