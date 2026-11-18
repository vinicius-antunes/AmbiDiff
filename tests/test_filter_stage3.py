"""Portais e mídia fictícios: sem acesso a SEMA/CGE ou outros sites reais."""
import copy
import threading
import unittest
from unittest.mock import patch
from ambidiff.core import Pagina
from ambidiff.portal import EscopoPortal
from ambidiff.urlfilter import PoliticaURLs
from ambidiff import checkpoints as cp
from test_update18 import A,B,executar,opcao


class PortalFilterTests(unittest.TestCase):
    def test_friendly_locale_group_e_dominios_independentes(self):
        f=PoliticaURLs(bases=(A+'web/verde',B+'pt/web/homolog'))
        for side,base,group in ((0,A,'10'),(1,B,'20')):
            f.escopos[side].observar(base,{'group_id':group},True)
        self.assertFalse(f.avaliar((A+'web/verde/contato',B+'pt/web/homolog/contato',['Contato'])))
        self.assertTrue(f.avaliar((A+'web/outro',B+'web/terceiro',['Portal vizinho'])))
        self.assertTrue(f.avaliar((A+'?groupId=99',B+'?_portlet_groupId=99',['Outro site'])))
        self.assertFalse(f.escopos[0].outro(A+'documents/d/verde/manual.pdf'))
        self.assertFalse(f.escopos[0].outro('https://external.test/web/outro'))
        self.assertTrue(f.avaliar((A+'web/outro/institucional',B+'pt/web/homolog/institucional',['Institucional'])))
        self.assertFalse(f.registros[(A+'web/outro/institucional',B+'pt/web/homolog/institucional')]['excecao_estrutural'])

    def test_canonical_friendly_navegacao_e_incerteza(self):
        for dados in ({'canonical':A+'web/verde/inicio'}, {'friendly_url':A+'web/verde/inicio'},
                      {'navegacao':[A+'web/verde/a',A+'web/verde/b']}):
            s=EscopoPortal(A);s.observar(A,dados,True)
            self.assertTrue(s.outro(A+'web/outro'))
            s.observar(A+'web/outro',{'canonical':A+'web/outro'},False)
            self.assertTrue(s.outro(A+'web/outro'))
        s=EscopoPortal(A);s.observar(A,{'canonical':A+'web/um','friendly_url':A+'web/dois'},True)
        self.assertFalse(s.outro(A+'web/tres'))

    def test_cem_paginas_midias_e_primeira_preservada(self):
        for label in ('Fotografias','Galerias','Rádio','TV','Vídeos','Áudios','Arquivo editorial'):
            f=PoliticaURLs()
            for n in (1,2,115,500):
                pair=(A+'acervo?_publisher_INSTANCE_Z_cur='+str(n),B+'acervo?_random_cur='+str(n),[label])
                self.assertEqual(f.avaliar(pair),n>1)
            self.assertFalse(f.avaliar((A+'acervo?delta=100',B+'acervo?delta=100',[label])))

    def test_documentos_resolucoes_e_servicos_nao_perdem_paginacao(self):
        f=PoliticaURLs()
        for i,label in enumerate(('Documentos','Legislação','Resoluções','Portarias','Serviço público')):
            self.assertFalse(f.avaliar((A+'catalogo'+str(i)+'?_x_cur=115',B+'catalogo'+str(i)+'?_x_cur=115',[label])))
        self.assertEqual(f.resumo()['paginacoes_documentais_preservadas'],4)

    def test_evidencia_dom_opaca_checkpoint_e_individuais(self):
        f=PoliticaURLs(bases=(A,B))
        for side,base in enumerate((A,B)):
            page=Pagina(base,'','Acervo',[],coleta={'referencias_finalidade':[
                {'url':base+'catalogo?_x_cur=115','finalidade':'listagem_editorial'},
                {'url':base+'item?id=3','finalidade':'editorial_individual'}]})
            f.observar(side,page,base,True)
        f=PoliticaURLs(f.estado(),(A,B))
        self.assertTrue(f.avaliar((A+'catalogo?_x_cur=115',B+'catalogo?_x_cur=115',['115']),'Paginação'))
        self.assertTrue(f.avaliar((A+'item?id=3',B+'item?id=3',['Conteúdo'])))
        self.assertFalse(f.avaliar((A+'catalogo?delta=10',B+'catalogo?delta=10',['Outro'])))
        self.assertFalse(f.avaliar(('http://[invalid','',['Outro'])))
        for side,base in enumerate((A,B)):f.evidencias[side][base+'web/verde/w/colecao?cur=1']='listagem_editorial'
        self.assertFalse(f.avaliar((A+'web/verde/w/colecao?cur=1',B+'web/verde/w/colecao?cur=1',['Primeiro'])))

    def test_portal_estrangeiro_nao_e_liberado_por_institucional(self):
        f=PoliticaURLs(bases=(A+'web/verde',B+'web/verde'))
        pair=(A+'web/outro/institucional',B+'web/outro/institucional',['Institucional'])
        self.assertTrue(f.avaliar(pair));self.assertTrue(f.avaliar(pair))
        self.assertEqual(f.resumo()['pares_excluidos'],1)
        self.assertEqual(f.resumo()['excecoes_estruturais'],0)


def portal_meta(url):
    base=A if url.startswith(A) else B
    return {'portal':{'canonical':base+'web/verde/inicio','group_id':'10'}}


class PortalEngineTests(unittest.TestCase):
    def test_destino_head_divergente_de_portal_vizinho_e_preservado(self):
        def graph(u):
            base=A if u.startswith(A) else B
            return [opcao('Vizinho',base+'web/outro','Menu'),opcao('Vizinho',base+'web/outro','Rodapé')] if u==base else []
        r,opened,_=executar(graph,metadados=portal_meta,redirecionamentos={B+'web/outro':B+'web/destino-diferente'})
        self.assertEqual(opened,[A,B])
        self.assertTrue(any(d.get('situacao')=='DESTINO_DIVERGENTE' for d in r['divergencias']))
        self.assertEqual(len([v for v in r['verificacoes_destinos'] if v.get('escopo')=='Referência sem expansão HTML']),1)

    def test_raiz_redirecionada_estabelece_portal_sem_lista_de_orgaos(self):
        def graph(u):
            base=A if u.startswith(A) else B
            return [opcao('Vizinho',base+'web/vizinho','Menu')] if u==base else []
        r,opened,_=executar(graph,redirecionamentos={A:A+'web/verde/inicio',B:B+'web/verde/inicio'})
        self.assertEqual(opened,[A,B]);self.assertEqual(r['andamento']['pares_comparados'],1)
        self.assertEqual(r['filtro_urls']['excluidas_por_categoria']['outro_portal'],1)

    def test_redirecionamento_editorial_nao_e_contado_como_abertura_evitada(self):
        def graph(u):
            base=A if u.startswith(A) else B
            return [opcao('Fotografias',base+'atalho','Menu')] if u==base else []
        r,opened,_=executar(graph,redirecionamentos={A+'atalho':A+'fotos?_x_cur=115',B+'atalho':B+'fotos?_x_cur=115'})
        self.assertEqual(len(opened),4);self.assertEqual(r['andamento']['pares_comparados'],1)
        self.assertEqual(r['filtro_urls']['navegacoes_planejadas_evitadas'],0)
        self.assertEqual(r['filtro_urls']['pares_contidos_apos_redirecionamento'],1)
        self.assertEqual(r['metricas']['contagens']['navegacoes_html_tentadas'],4)

    def test_exclusiva_editorial_referencia_verificada_e_ambigua_inspecionada(self):
        def graph(u):
            return [opcao('Conteúdo temporal',A+'item?id=3','Acervo'),opcao('Área não classificada',A+'area','Menu')] if u==A else []
        def meta(u):return {'referencias_finalidade':[{'url':A+'item?id=3','finalidade':'editorial_individual'}]} if u==A else {}
        r,opened,_=executar(graph,metadados=meta)
        self.assertNotIn(A+'item?id=3',opened);self.assertIn(A+'area',opened)
        self.assertTrue(any(d['elemento']=='Conteúdo temporal' for d in r['divergencias']))
        self.assertTrue(any(v.get('destino_a')==A+'item?id=3' for v in r['verificacoes_destinos']))
        self.assertEqual(r['filtro_urls']['exclusivas_classificadas_por_finalidade']['editorial'],1)

    def test_servico_compartilhado_fora_prefixo_inicial_sem_liberar_subarvore(self):
        import test_update18 as fixture
        ra,rb=A+'web/verde',B+'web/homolog'
        def graph(u):
            base=A if u.startswith(A) else B
            if u in (ra,rb):return [opcao('SIMCAR',base+'web/servico/entrada','Serviços')]
            return [opcao('Outra área',base+'web/servico/filho','Menu')]
        with patch.multiple(fixture,A=ra,B=rb):r,opened,_=fixture.executar(graph)
        self.assertIn(A+'web/servico/entrada',opened);self.assertIn(B+'web/servico/entrada',opened)
        self.assertFalse(any(u.endswith('/filho') for u in opened))
        self.assertEqual(r['andamento']['pares_comparados'],2)

    def test_outro_portal_head_sem_expandir_e_audios_ambos_sentidos(self):
        for exclusive in (A,B):
            def graph(u):
                base=A if u.startswith(A) else B
                if u==base:return [opcao('Portal vizinho',base+'web/outro','Menu')]+([opcao('ÁUDIOS',base+'audios','Menu')] if base==exclusive else [])
                if '/web/outro' in u:return [opcao('Árvore indevida',base+'web/outro/filho')]
                return []
            r,opened,_=executar(graph,metadados=portal_meta)
            self.assertFalse(any('web/outro' in u for u in opened))
            self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))
            self.assertTrue(any(v.get('escopo')=='Referência sem expansão HTML' for v in r['verificacoes_destinos']))
            self.assertEqual(r['filtro_urls']['excluidas_por_categoria']['outro_portal'],1)

    def test_servicos_compartilhados_exatos_e_institucional_exclusiva(self):
        names=('SIMCAR','SIMLAM','SISFLORA','CONSEMA')
        def graph(u):
            base=A if u.startswith(A) else B
            if u==base:return [opcao(n,base+'web/compartilhado/'+n,'Serviços') for n in names]+([opcao('Institucional',base+'institucional/exclusiva','Menu')] if base==A else [])
            if '/web/compartilhado/' in u:return [opcao('Outro portal',base+'web/compartilhado/noticias','Menu')]
            return []
        r,opened,_=executar(graph,metadados=portal_meta)
        for base in (A,B):
            for n in names:self.assertIn(base+'web/compartilhado/'+n,opened)
        self.assertFalse(any(u.endswith('/noticias') for u in opened))
        self.assertIn(A+'institucional/exclusiva',opened)
        self.assertEqual(r['andamento']['pares_comparados'],5)

    def test_redirecionamento_outro_portal_nao_extrai_ou_expande(self):
        extracted=[]
        def graph(u):
            extracted.append(u);base=A if u.startswith(A) else B
            return [opcao('Atalho',base+'atalho','Menu')] if u==base else []
        r,opened,_=executar(graph,metadados=portal_meta,redirecionamentos={A+'atalho':A+'web/outro',B+'atalho':B+'web/outro'})
        self.assertEqual(extracted,[A,B]);self.assertEqual(r['andamento']['pares_comparados'],1)
        self.assertTrue(any('Redirecionamento observado' in p['motivo'] for p in r['pendencias']))

    def test_dom_opaco_na_admissao_e_retomada_parcial(self):
        stop=threading.Event();snapshots=[]
        def graph(u):
            base=A if u.startswith(A) else B
            if u==base:return [opcao('Acervo',base+'colecao','Menu'),opcao('Institucional',base+'institucional','Menu')]+([opcao('ÁUDIOS',A+'audio.pdf','Menu')] if base==A else [])
            if u==base+'colecao':return [opcao(str(n),base+'colecao?_x_cur='+str(n),'Paginação') for n in range(1,301)]
            return []
        def meta(u):
            base=A if u.startswith(A) else B
            return {**portal_meta(u),'referencias_finalidade':[{'url':base+'colecao?_x_cur='+str(n),'finalidade':'listagem_editorial'} for n in range(1,301)] if u==base+'colecao' else []}
        def log(msg):
            if msg.startswith('[PRD/DES] 2 pares'):stop.set()
        r,_,_=executar(graph,metadados=meta,parar=stop,ao_log=log,checkpoint=lambda d:snapshots.append(copy.deepcopy(d)))
        self.assertEqual(r['situacao_analise'],'parcial')
        self.assertEqual(r['estado_execucao'],'interrompido')
        estado=cp.validar(snapshots[-1]['retomada'])
        resumed,opened,_=executar(graph,metadados=meta,retomada=cp.empacotar(estado))
        self.assertFalse(any('_cur=' in u for u in opened))
        self.assertEqual(resumed['andamento']['pares_comparados'],3)
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in resumed['divergencias']))
        self.assertEqual(resumed['filtro_urls']['excluidas_por_categoria']['paginacao_editorial'],299)


class PortalDOMTests(unittest.TestCase):
    def test_componentes_editoriais_e_administrativos_no_mesmo_html(self):
        import shutil
        from playwright.sync_api import sync_playwright
        from ambidiff.core import JS_EXTRAIR
        with sync_playwright() as pw:
            opts={'headless':True}
            if shutil.which('chromium'):opts['executable_path']=shutil.which('chromium')
            browser=pw.chromium.launch(**opts)
            try:
                page=browser.new_page()
                html='<meta charset="utf-8"><main><h1>Notícias</h1><section><h2>Galerias</h2><nav class="pagination"><a href="/catalogo?_foto_cur=115">115</a></nav></section><section><h2>Legislação</h2><nav class="pagination"><a href="/catalogo?_lei_cur=2">2</a></nav></section><section><h2>Serviços</h2><article><time datetime="2026-01-01">Atualizado</time><a href="/sistema">Sistema</a></article></section><article><a href="/area"><img alt="Institucional">Área</a></article></main>'
                page.route('**/*',lambda r:r.fulfill(status=200,content_type='text/html',body=html))
                page.goto('http://127.0.0.1/catalogo')
                data=page.evaluate(JS_EXTRAIR)
                refs={r['url']:r['finalidade'] for r in data['referencias_finalidade']}
                self.assertEqual(refs['http://127.0.0.1/catalogo?_foto_cur=115'],'listagem_editorial')
                self.assertEqual(refs['http://127.0.0.1/catalogo?_lei_cur=2'],'documental')
                self.assertNotIn('http://127.0.0.1/sistema',refs)
                self.assertNotIn('http://127.0.0.1/area',refs)
            finally:browser.close()

    def test_metadados_liferay_e_acervo_sem_nome_editorial_na_url(self):
        import shutil
        from playwright.sync_api import sync_playwright
        from ambidiff.core import JS_EXTRAIR
        with sync_playwright() as pw:
            opts={'headless':True}
            if shutil.which('chromium'):opts['executable_path']=shutil.which('chromium')
            browser=pw.chromium.launch(**opts)
            try:
                page=browser.new_page()
                for heading,card,expected in (
                    ('Acervo','<article><time datetime="2026-01-01">Hoje</time><a href="/item?id=1">Conteúdo</a></article>'*2,'listagem_editorial'),
                    ('Fotografias','<figure><a href="/item?id=2"><img alt="Foto" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="></a></figure>','listagem_editorial'),
                    ('Resoluções','<article><time datetime="2026-01-01">Hoje</time></article>'*2,'documental')):
                    html='<meta charset="utf-8"><link rel="canonical" href="http://127.0.0.1/web/verde/acervo"><script>window.Liferay={ThemeDisplay:{getScopeGroupId:()=>123,getLayoutRelativeURL:()=>"/web/verde/acervo"}}</script><main><h1>'+heading+'</h1>'+card+'<nav class="pagination"><a href="/acervo?_random_INSTANCE_ABC_cur=115">115</a><a href="/acervo?delta=10">Próximo</a></nav></main>'
                    page.route('**/*',lambda r:r.fulfill(status=200,content_type='text/html',body=html))
                    page.goto('http://127.0.0.1/acervo')
                    data=page.evaluate(JS_EXTRAIR)
                    self.assertEqual(data['portal']['group_id'],'123')
                    refs={r['url']:r['finalidade'] for r in data['referencias_finalidade']}
                    self.assertEqual(refs['http://127.0.0.1/acervo?_random_INSTANCE_ABC_cur=115'],expected)
                    self.assertTrue(any(i['nome']=='115' for i in data['itens']))
                    if expected=='listagem_editorial':self.assertIn('editorial_individual',refs.values())
                    page.unroute('**/*')
            finally:browser.close()
