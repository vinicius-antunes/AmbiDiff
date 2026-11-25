"""Regressões CGE fictícia: admissão real, sem ocultação de DIVs."""
import copy
import threading
import unittest
from unittest.mock import patch
from ambidiff.urlfilter import PoliticaURLs
from ambidiff.pagination import paginacao,primeira_equivalente
from ambidiff import checkpoints as cp
from test_update18 import A,B,executar,opcao

class Stage2Tests(unittest.TestCase):
    def pair(self,path,name='Próximo'):return A+path,B+path,['Início',name]
    def test_liferay_prefixos_offset_e_delta(self):
        for key in ('cur','page','start','offset','_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_x3_cur','_outro_portlet_INSTANCE_Y_offset'):
            with self.subTest(key=key):self.assertTrue(paginacao(A+'noticias?'+key+'=20')['posterior'])
        for q in ('delta=10','_abc_delta=10','cur=1','start=0','offset=0'):
            self.assertFalse(paginacao(A+'noticias?'+q)['posterior'])
            self.assertFalse(PoliticaURLs().avaliar(self.pair('noticias?'+q),'Paginação'))
    def test_menu_e_mapa_nao_autorizam_pagina_posterior(self):
        for path in ('noticias?cur=12','videos?cur=4','audios?offset=20','galerias?_random_INSTANCE_Z_cur=2'):
            for context in ('Menu de navegação estrutura','Mapa do site','Conteúdo institucional',''):
                self.assertTrue(PoliticaURLs().avaliar(self.pair(path),context))
    def test_documentos_servicos_campanha_preservados_com_motivo(self):
        for path,name,ctx in [('legislacao?cur=2','Portarias','Menu'),('documents/d/portal/lista?offset=20','Documentos','Conteúdo'),('servicos?cur=2','Serviço público','Menu'),('web/cge/w/integridade-mt-2','Campanha de integridade','Conteúdo')]:
            f=PoliticaURLs();self.assertFalse(f.avaliar(self.pair(path,name),ctx))
            self.assertTrue(f.resumo()['excecoes_estruturais']);self.assertNotIn('ambígua',f.resumo(True)['referencias'][0]['motivo'])
            if path.startswith('servicos'):self.assertEqual(f.resumo()['paginacoes_documentais_preservadas'],0)
            elif 'cur=2' in path or 'offset=20' in path:self.assertEqual(f.resumo()['paginacoes_documentais_preservadas'],1)
    def test_rotulo_importante_nao_muda_assunto_de_noticia(self):
        f=PoliticaURLs()
        for label in ('Institucional','Serviço ao cidadão','Documentos'):
            self.assertTrue(f.avaliar(self.pair('noticias?cur=3',label),'Menu Serviços institucional estrutura'))
        self.assertFalse(f.avaliar(self.pair('w/assunto-nao-classificado','Outro'),'Mapa do site'))
        self.assertEqual(f.resumo()['excecoes_estruturais'],0)
    def test_doze_paginas_nao_entram_em_candidatos_ou_fila(self):
        snaps=[]
        def grafo(u):
            base=A if u.startswith(A) else B
            if u==base:return [opcao('Notícias',base+'noticias','Menu')]+([opcao('ÁUDIOS',A+'audios','Menu',recurso='navegacao')] if u==A else [])
            if u==base+'noticias':return [opcao(str(n),base+'noticias?_asset_INSTANCE_AbC_cur='+str(n),'Notícias',posicao='Menu de navegação',natureza='estrutura') for n in range(1,13)]
            return []
        r,opened,_=executar(grafo,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        state=cp.validar(snaps[-1]['retomada'])
        self.assertEqual(r['andamento']['pares_comparados'],2)
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))
        self.assertEqual(r['filtro_urls']['excluidas_por_categoria']['paginacao_editorial'],11)
        self.assertFalse(any('_cur=' in u for u in opened))
        self.assertFalse(any('_cur=' in u for p in state['pares_enfileirados'] for u in p))
        self.assertEqual(len(state['pares_enfileirados']),len(state['estados_pares']))
    def test_primeira_pagina_preserva_delta_e_conteudo(self):
        self.assertEqual(primeira_equivalente(A+'noticias?cur=1'),A+'noticias')
        self.assertEqual(primeira_equivalente(A+'noticias?_abc_cur=1&delta=10&c=2&e=3'),A+'noticias?delta=10&c=2&e=3')
        self.assertEqual(primeira_equivalente(A+'servicos?cur=1'),A+'servicos?cur=1')
    def test_exclusiva_editorial_nao_abre_arvore_servico_abre(self):
        def grafo(u):
            if u==A:return [opcao('Vídeo de teste',A+'videos/episodio','Vídeos',recurso='navegacao'),opcao('Serviço público',A+'servicos/exclusivo','Menu',recurso='navegacao')]
            if u==A+'servicos/exclusivo':return [opcao('Outro vídeo',A+'videos/filho','Menu',recurso='navegacao')]
            return []
        r,opened,_=executar(grafo)
        self.assertIn(A+'servicos/exclusivo',opened)
        self.assertFalse(any('/videos/' in u for u in opened))
        self.assertEqual(r['andamento']['pares_exclusivamente_inspecionados'],1)
        self.assertEqual(r['filtro_urls']['exclusivas_descartadas'],2)
    def test_candidatos_checkpoint_reavaliados_antes_admissao(self):
        stop=threading.Event();snaps=[]
        def log(msg):
            if msg.startswith('[PRD/DES]'):stop.set()
        def grafo(u):
            base=A if u.startswith(A) else B
            return [opcao('Notícias',base+'noticias','Menu')] if u==base else []
        executar(grafo,parar=stop,checkpoint=lambda d:snaps.append(copy.deepcopy(d)),ao_log=log)
        estado=cp.validar(snaps[-1]['retomada'])
        candidate=[A+'videos?_portlet_cur=4',B+'videos?_portlet_cur=4',['Início','Vídeos']]
        estado['candidatos_html'].append(candidate);estado['candidatos_vistos'].append(candidate[:2])
        r,opened,_=executar(lambda _:[],retomada=cp.empacotar(estado))
        self.assertFalse(any('_cur=4' in u for u in opened));self.assertEqual(r['andamento']['pares_pendentes'],0)
        self.assertEqual(r['filtro_urls']['excluidas_por_categoria']['paginacao_editorial'],1)
    def test_eventos_unicos_amostras_sanitizadas_limitadas(self):
        f=PoliticaURLs()
        for i in range(140):f.avaliar(self.pair('videos?cur='+str(i+2)+'&token=SEGREDO'),'Menu')
        for i in range(2):f.avaliar(self.pair('videos?cur=2&token=SEGREDO'),'Mapa')
        d=f.resumo(True)
        self.assertEqual(d['pares_excluidos'],140);self.assertEqual(d['eventos']['tentativas_admissao'],142)
        self.assertEqual(len(d['referencias']),100);self.assertNotIn('SEGREDO',str(d))
        self.assertEqual(d['referencias'][0]['paginacao'][0],[{'parametro':'cur','valor':2}])
        self.assertEqual(PoliticaURLs(f.estado()).resumo()['eventos'],d['eventos'])

    def test_pagina_posterior_inicial_explicita_preservada(self):
        import test_update18 as fixture
        with patch.multiple(fixture,A=A+'noticias?cur=12',B=B+'noticias?cur=12'):
            r,opened,_=fixture.executar(lambda _:[])
        self.assertEqual(r['andamento']['pares_comparados'],1)
        self.assertIn(A+'noticias?cur=12',opened)
        self.assertEqual(r['filtro_urls']['pares_excluidos'],0)

    def test_cliques_opcionais_nao_abrem_paginacao_excluida(self):
        import test_update18 as fixture
        original=fixture.executar_pareado
        def configured(*a,**kw):return original(*a,verificar_cliques=True,**kw)
        def graph(u):
            base=A if u.startswith(A) else B
            return [opcao('Próximo',base+'noticias?cur=2','Notícias')] if u==base else []
        with patch.object(fixture,'executar_pareado',side_effect=configured), patch('ambidiff.paired.verificar_par') as probe:
            r,opened,_=fixture.executar(graph)
        probe.assert_not_called()
        self.assertEqual(len(opened),2)
        self.assertFalse(r['resultados_funcionais'][0]['teste_executado'])

    def test_cache_de_menu_legado_nao_vira_excecao_atual(self):
        pair=self.pair('videos?cur=4','Vídeos')
        legacy={'preservadas':list(pair[:2]),'registros':[{'par':list(pair[:2]),'excluido':False,'categoria':'','excecao_estrutural':True,'motivo':'Menu institucional'}]}
        f=PoliticaURLs(legacy)
        self.assertEqual(f.resumo()['excecoes_legadas_sem_revalidacao'],1)
        self.assertEqual(f.resumo()['excecoes_estruturais'],0)
        self.assertTrue(f.avaliar(pair,'Menu'))
        self.assertEqual(f.resumo()['urls_excluidas'],2)

    def test_candidato_rejeitado_na_retomada_pode_ser_redescoberto_com_prova(self):
        stop=threading.Event();snaps=[]
        def log(msg):
            if msg.startswith('[PRD/DES]'):stop.set()
        def rootgraph(u):
            base=A if u.startswith(A) else B
            return [opcao('Serviço',base+'servicos','Menu')] if u==base else []
        executar(rootgraph,parar=stop,checkpoint=lambda d:snaps.append(copy.deepcopy(d)),ao_log=log)
        estado=cp.validar(snaps[-1]['retomada'])
        candidate=[A+'web/cge/w/integridade-mt-2',B+'web/cge/w/integridade-mt-2',['Início','Notícia']]
        estado['candidatos_html'].append(candidate);estado['candidatos_vistos'].append(candidate[:2])
        def graph(u):
            base=A if u.startswith(A) else B
            if u==base+'servicos':return [opcao('Campanha de integridade',base+'web/cge/w/integridade-mt-2','Campanha institucional')]
            return []
        r,opened,_=executar(graph,retomada=cp.empacotar(estado))
        self.assertIn(candidate[0],opened);self.assertIn(candidate[1],opened)
        self.assertEqual(r['andamento']['pares_comparados'],3)
        self.assertEqual(r['filtro_urls']['pares_excluidos'],0)

class PaginationDOMTests(unittest.TestCase):
    def test_html_contexto_estavel_numeracao_e_ausencia_real(self):
        from playwright.sync_api import sync_playwright
        from ambidiff.core import JS_EXTRAIR,Item,Pagina
        from ambidiff.smart import Inteligencia,Metricas
        with sync_playwright() as pw:
            import shutil
            opts={'headless':True}
            if shutil.which('chromium'):opts['executable_path']=shutil.which('chromium')
            browser=pw.chromium.launch(**opts)
            try:
                page=browser.new_page();pages=[]
                for base,headline in ((A,'Notícia recente de hoje'),(B,'Vídeo antigo e diferente')):
                    page.set_content('<main><section><h2>'+headline+'</h2><nav class="pagination" aria-label="Paginação"><a href="'+base+'noticias?cur=1" aria-label="Primeiro">Primeiro</a><a href="'+base+'noticias?_abc_cur=2">2</a><a href="'+base+'noticias?cur=2" rel="next">Próximo</a></nav></section></main>')
                    items=[Item(**r) for r in page.evaluate(JS_EXTRAIR)['itens']]
                    controls=[i for i in items if i.funcao=='paginacao']
                    self.assertEqual({i.nome for i in controls},{'Primeiro','2','Próximo'})
                    self.assertEqual({i.local for i in controls},{'Paginação'})
                    pages.append(Pagina(base,'',headline,controls,['Início']))
                intel=Inteligencia(Metricas());a,b=pages
                self.assertFalse(intel.comparar(a.itens,b.itens,a,b,'PRD','DES',A,B))
                b.itens=[i for i in b.itens if i.nome!='Próximo']
                diff=intel.comparar(a.itens,b.itens,a,b,'PRD','DES',A,B)
                self.assertTrue(any(d.get('elemento')=='Próximo' for d in diff))
            finally:browser.close()

    def test_paginadores_nomeados_continuam_componentes_distintos(self):
        import shutil
        from playwright.sync_api import sync_playwright
        from ambidiff.core import JS_EXTRAIR,Item,Pagina
        from ambidiff.smart import Inteligencia,Metricas
        with sync_playwright() as pw:
            options={'headless':True}
            if shutil.which('chromium'):options['executable_path']=shutil.which('chromium')
            browser=pw.chromium.launch(**options)
            try:
                page=browser.new_page();pages=[]
                for base in (A,B):
                    html='<main><h2>Títulos editoriais diferentes</h2>'
                    for kind in ('Notícias','Vídeos'):
                        label='Anterior' if base==B and kind=='Vídeos' else 'Próximo'
                        html+='<nav class="pagination" aria-label="'+kind+'"><a href="'+base+('noticias' if kind=='Notícias' else 'videos')+'?cur=2">'+label+'</a></nav>'
                    page.set_content(html+'</main>')
                    items=[Item(**r) for r in page.evaluate(JS_EXTRAIR)['itens'] if r.get('funcao')=='paginacao']
                    self.assertEqual({i.local for i in items},{'Paginação: Notícias','Paginação: Vídeos'})
                    pages.append(Pagina(base,'','Listagens',items,['Início']))
                a,b=pages;r=Inteligencia(Metricas()).comparar(a.itens,b.itens,a,b,'PRD','DES',A,B)
                self.assertTrue(any(d.get('tipo')=='Rótulo' and d.get('texto_a')=='Próximo' and d.get('texto_b')=='Anterior' and 'Vídeos' in d.get('local','') for d in r))
            finally:browser.close()
