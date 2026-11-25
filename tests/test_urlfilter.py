"""Exclusão de navegação conhecida; comparação da origem permanece ativa."""
import copy
import threading
import unittest
from ambidiff.urlfilter import PoliticaURLs,identidade
from ambidiff.frontier import Fila,categoria
from test_update18 import executar,opcao,A,B
from ambidiff import checkpoints as cp


class URLFilterTests(unittest.TestCase):
    def par(self,path,label='Notícia de teste'):
        return A+path,B+path,['Página inicial',label]
    def test_rotas_editoriais_e_excecoes_conservadoras(self):
        for path in ('w/conteudo','-/conteudo'):
            for context in ('Notícias','Conteúdo editorial'):
                self.assertTrue(PoliticaURLs().avaliar(self.par(path),context))
            for label,context in [('ÁUDIOS','Notícias'),('Institucional','Conteúdo'),('Serviço ao cidadão','Notícias'),('Portaria','Conteúdo'),('Opção','Menu lateral'),('Opção desconhecida','Conteúdo principal')]:
                self.assertFalse(PoliticaURLs().avaliar(self.par(path,label),context))
    def test_paginacao_liferay_e_parametros_funcionais(self):
        for query in ('cur=2','page=3','delta=20&cur=5','start=20','_noticias_INSTANCE_abc_cur=3','_abc_start=40'):
            self.assertTrue(PoliticaURLs().avaliar(self.par('noticias?'+query),'Notícias'))
            self.assertFalse(PoliticaURLs().avaliar(self.par('portarias?'+query,'Portarias'),'Legislação'))
        for query in ('cur=1','page=1','start=0','delta=20','c=2&e=3'):
            self.assertFalse(PoliticaURLs().avaliar(self.par('noticias?'+query),'Notícias'))
        self.assertTrue(PoliticaURLs().avaliar(self.par('noticias/page/2'),'Notícias'))
    def test_filtros_editoriais_busca_e_impressao_comprovada(self):
        for query in ('year=2024','_noticias_categoryId=33','month=2','orderby=asc'):
            self.assertTrue(PoliticaURLs().avaliar(self.par('noticias?'+query),'Notícias'))
            self.assertFalse(PoliticaURLs().avaliar(self.par('documentos?'+query,'Documentos'),'Documentos'))
        self.assertTrue(PoliticaURLs().avaliar(self.par('busca?q=teste','Buscar'),'Conteúdo'))
        self.assertFalse(PoliticaURLs().avaliar(self.par('consulta?search=teste','Consultar processo'),'Serviço'))
        represented=[{identidade(A+'pagina')},{identidade(B+'pagina')}]
        for path in ('pagina?print=true','print/pagina'):
            self.assertTrue(PoliticaURLs().avaliar(self.par(path,'Página'),'',represented))
            self.assertFalse(PoliticaURLs().avaliar(self.par(path,'Página')))
        self.assertFalse(PoliticaURLs().avaliar(self.par('printing','Página'),'',represented))
    def test_tracking_nao_altera_identidade_funcional_ou_original(self):
        u=A+'pagina?c=123&e=2&utm_source=a&fbclid=x#tab'
        self.assertEqual(identidade(u),A+'pagina?c=123&e=2#tab')
        self.assertNotEqual(identidade(u),identidade(A+'pagina?c=456&e=2#tab'))
        self.assertNotEqual(identidade(u),identidade(A+'pagina?c=123&e=2#outra'))
        self.assertIn('utm_source=a',u)
    def test_uma_contraparte_estrutural_preserva_par(self):
        self.assertFalse(PoliticaURLs().avaliar((A+'w/noticia',B+'institucional',['Início','Notícia']),'Notícias'))
    def test_excecao_posterior_revoga_exclusao_e_diagnostico_sanitizado(self):
        f=PoliticaURLs();par=self.par('w/conteudo?token=SEGREDO')
        self.assertTrue(f.avaliar(par,'Notícias'));self.assertNotIn('SEGREDO',str(f.resumo(True)))
        self.assertFalse(f.avaliar(par,'Legislação'))
        g=PoliticaURLs(f.estado());self.assertEqual(g.resumo()['pares_excluidos'],0)
        self.assertEqual(g.resumo()['exclusoes_reconsideradas'],1)
    def test_origem_audios_preservada_excluidas_sem_consumir_teto(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            if u!=base:return []
            return [opcao('Notícia '+str(i),base+'w/'+str(i),'Notícias',recurso='navegacao') for i in range(1100)]+[opcao('Serviço',base+'servico','Menu')]+([opcao('ÁUDIOS',A+'audios','Menu',recurso='navegacao')] if u==A else [])
        r,abertas,_=executar(grafo)
        self.assertEqual(r['andamento']['pares_admitidos_html'],3)
        self.assertEqual(r['andamento']['pares_comparados'],2)
        self.assertEqual(r['filtro_urls']['pares_excluidos'],1100)
        self.assertEqual(r['filtro_urls']['urls_excluidas'],2200)
        self.assertEqual(r['filtro_urls']['urls_excluidas_por_categoria']['rota_editorial'],2200)
        self.assertFalse(any('/w/' in u for u in abertas))
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))
        self.assertFalse(any(d['estado']=='inconclusivo' for d in r['diagnosticos_pares']))
    def test_tracking_duplicado_sem_reescrever_evidencia(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            return [opcao('Um',base+'pagina?c=1','Menu'),opcao('Dois',base+'pagina?c=1&utm_source=campanha','Menu'),opcao('Três',base+'pagina?c=2','Menu')] if u==base else []
        r,abertas,_=executar(grafo)
        self.assertEqual(len(abertas),6)
        self.assertEqual(r['filtro_urls']['duplicacoes_evitadas'],1)
        self.assertFalse(any('utm_source' in u for u in abertas))
    def test_exclusao_unilateral_e_promocao_estrutural_posterior(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            if u==base:return [opcao('Avançar',base+'secao','Menu')]+([opcao('Artigo',A+'w/exclusiva','Notícias',recurso='navegacao')] if u==A else [])
            if u==base+'secao':return [opcao('Institucional',base+'w/exclusiva','Menu',recurso='navegacao')]
            return []
        r,abertas,_=executar(grafo)
        self.assertIn(A+'w/exclusiva',abertas);self.assertIn(B+'w/exclusiva',abertas)
        self.assertEqual(r['andamento']['pares_comparados'],3)
        self.assertEqual(r['filtro_urls']['pares_excluidos'],0)
        self.assertEqual(r['filtro_urls']['exclusoes_reconsideradas'],1)
    def test_interrupcao_retomada_preserva_filtro_e_admitidos(self):
        stop=threading.Event();snapshots=[]
        def grafo(u):
            base=A if u.startswith(A) else B
            if u not in (A,B):stop.set();return []
            return [opcao('Notícia',base+'w/artigo','Notícias'),opcao('Serviço',base+'servico','Menu')]
        executar(grafo,parar=stop,checkpoint=lambda s:snapshots.append(copy.deepcopy(s)))
        payload=snapshots[-1]['retomada'];state=cp.validar(payload)
        self.assertIn('filtro_urls',state)
        r,_,_=executar(lambda _:[],retomada=payload)
        self.assertEqual(r['filtro_urls']['pares_excluidos'],1)
        self.assertEqual(r['andamento']['pares_pendentes'],0)
        state.pop('filtro_urls');legacy=cp.empacotar(state)
        r,_,_=executar(lambda _:[],retomada=legacy)
        self.assertEqual(r['andamento']['pares_pendentes'],0)
    def test_promocao_prioridade_nao_duplica_fila(self):
        par=self.par('w/artigo');cats={tuple(par[:2]):4};q=Fila([par],dinamica=True,categorias=cats)
        outro=self.par('servico','Serviço');q.append(outro);cats[tuple(par[:2])]=0;q.promover(tuple(par[:2]))
        self.assertEqual(q.popleft(),par);self.assertEqual(q.popleft(),outro);self.assertFalse(q)

    def test_raizes_editoriais_explicitas_sao_analisadas(self):
        from unittest.mock import patch
        import test_update18 as fixture
        with patch.multiple(fixture,A=A+'w/inicial',B=B+'-/inicial'):
            r,abertas,_=fixture.executar(lambda _:[])
        self.assertEqual(r['andamento']['pares_comparados'],1)
        self.assertEqual(r['filtro_urls']['pares_excluidos'],0)
        self.assertEqual(len(abertas),2)

    def test_http_e_destinos_divergentes_preservados(self):
        def grafo(u):
            base=A if u.startswith(A) else B
            if u!=base:return []
            return [opcao('Serviço quebrado',base+'servico','Menu'),opcao('Destino',base+('um' if base==A else 'outro'),'Menu'),opcao('Notícia',base+'w/artigo','Notícias')]
        r,_,_=executar(grafo,falhas=(A+'servico',))
        self.assertEqual(r['andamento']['pares_com_falha'],1)
        self.assertTrue(any(d['tipo']=='Redirecionamento' for d in r['divergencias']))
        self.assertEqual(r['filtro_urls']['pares_excluidos'],1)
