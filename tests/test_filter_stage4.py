"""Regressões da etapa 4: fixtures locais, sem acessar portais reais."""
import unittest
import copy
import threading

from ambidiff.core import Pagina
from ambidiff.pagination import finalidade, paginacao
from ambidiff.portal import EscopoPortal, site_subdominio_dedicado
from ambidiff.urlfilter import PoliticaURLs, chave_evidencia
from unittest.mock import patch

A = 'https://sema.mt.gov.br/'
B = 'https://sema.lab.mt.gov.br/'


class FiltroSemaStage4Tests(unittest.TestCase):
    def par(self,rota,rotulo='Próximo'):
        return (A+rota,B+rota,['Início',rotulo])

    def test_radio_tv_paiaguas_paginacao_liferay(self):
        for rota in ('web/mt/radio-paiaguas','web/mt/tv-paiaguas',
                     'radio-paiaguas','tv_paiaguas'):
            with self.subTest(rota=rota):
                self.assertTrue(finalidade(A+rota)['editorial'])
                f=PoliticaURLs()
                self.assertTrue(f.avaliar(self.par(rota+'?_instance_abc_cur=43'), 'Paginação'))
                self.assertEqual(f.registros[self.par(rota+'?_instance_abc_cur=43')[:2]]['categoria'],'paginacao_editorial')
                self.assertFalse(PoliticaURLs().avaliar(self.par(rota+'?_instance_abc_cur=1'), 'Paginação'))
                self.assertFalse(PoliticaURLs().avaliar(self.par(rota+'?delta=10'), 'Paginação'))

    def test_paginas_documentais_e_servicos_preservados(self):
        for rota,label in [('documentos','Documentos'),('portarias','Portarias'),
                           ('legislacao','Legislação'),('servicos','Serviços')]:
            with self.subTest(rota=rota):
                self.assertFalse(PoliticaURLs().avaliar(self.par(rota+'?_x_cur=43',label),'Paginação'))

    def test_identidade_por_host_dedicado_quando_meta_nao_tem_site(self):
        self.assertEqual(site_subdominio_dedicado(A),'sema')
        self.assertEqual(site_subdominio_dedicado(B),'sema')
        self.assertEqual(site_subdominio_dedicado('https://www.mt.gov.br/'),'')
        self.assertEqual(site_subdominio_dedicado('https://portal.mt.gov.br/'),'')
        for origem in (A,B):
            escopo=EscopoPortal(origem)
            escopo.observar(origem,{'group_id':'123','navegacao':[
                origem+'web/mt/radio-paiaguas',origem+'web/seplag/a',
                origem+'web/mti/b']},True)
            self.assertEqual(escopo.site,'sema')
            self.assertEqual(escopo.fonte_site,'subdominio_heuristico')
            self.assertTrue(escopo.outro(origem+'web/mt/tv-paiaguas'))
            self.assertFalse(escopo.outro(origem+'web/sema/servicos'))
            restaurado=EscopoPortal(origem,escopo.estado())
            self.assertEqual(restaurado.fonte_site,'subdominio_heuristico')

    def test_canonical_explicito_vence_host(self):
        escopo=EscopoPortal(A)
        escopo.observar(A,{'canonical':A+'web/mt/inicio'},True)
        self.assertEqual(escopo.site,'mt')
        self.assertEqual(escopo.fonte_site,'metadados_raiz')
        self.assertFalse(escopo.outro(A+'web/mt/noticias'))
        self.assertTrue(escopo.outro(A+'web/seplag/noticias'))

    def test_metadados_conflitantes_nao_inferem_site(self):
        escopo=EscopoPortal(A)
        escopo.observar(A,{'canonical':A+'web/mt/inicio',
                          'friendly_url':A+'web/outro/inicio'},True)
        self.assertEqual(escopo.site,'')
        self.assertFalse(escopo.outro(A+'web/mt/inicio'))

    def test_evidencia_dom_em_um_lado_e_query_em_ordem_distinta(self):
        f=PoliticaURLs(bases=(A,B))
        original=A+'catalogo?b=2&_portlet_INSTANCE_ABC_cur=43&a=1'
        normalizado=A+'catalogo?_portlet_INSTANCE_ABC_cur=43&a=1&b=2'
        contra=B+'catalogo?a=1&_portlet_INSTANCE_XYZ_cur=43&b=2'
        pagina=Pagina(A,'','Acervo',[],coleta={'referencias_finalidade':[
            {'url':original,'finalidade':'listagem_editorial'}]})
        f.observar(0,pagina,A,True)
        self.assertTrue(f.avaliar((normalizado,contra,['Acervo','43']),'Paginação'))
        registro=f.registros[(normalizado,contra)]
        self.assertTrue(registro['evidencia_unilateral'])
        self.assertEqual(registro['categoria'],'paginacao_editorial')
        self.assertEqual(f.resumo()['paginacoes_assimetricas_com_evidencia'],1)
        novo=PoliticaURLs(f.estado(),(A,B))
        self.assertEqual(novo.evidencias[0],f.evidencias[0])

    def test_nao_inferir_sem_evidencia_nem_entre_paginas_diferentes(self):
        base=A+'catalogo?cur=43'
        f=PoliticaURLs(bases=(A,B))
        f.evidencias[0][base]='listagem_editorial'
        for contra in (B+'catalogo?cur=44',B+'outro?cur=43',B+'catalogo?offset=43'):
            self.assertFalse(f.avaliar((base,contra,['43']),'Paginação'))
        self.assertFalse(PoliticaURLs().avaliar((base,B+'catalogo?cur=43',['43']),'Paginação'))

    def test_nao_suprimir_excecao_documental_mesmo_com_prova_editorial(self):
        f=PoliticaURLs(bases=(A,B))
        for lado,base in enumerate((A,B)):
            f.evidencias[lado][base+'catalogo?cur=43']='listagem_editorial' if lado==0 else 'documental'
        self.assertFalse(f.avaliar((A+'catalogo?cur=43',B+'catalogo?cur=43',['Documentos']),'Documentos'))


class RevisaoStage4Tests(unittest.TestCase):
    def test_metadados_chegam_depois_da_heuristica(self):
        escopo=EscopoPortal(A)
        escopo.observar(A,{},True)  # fluxo real antes da extração do HTML
        self.assertEqual(escopo.site,'sema')
        escopo.observar(A,{'canonical':A+'web/principal/inicio'},True)
        self.assertEqual(escopo.site,'principal')
        self.assertEqual(escopo.fonte_site,'metadados_raiz')
        self.assertFalse(escopo.outro(A+'web/principal/institucional'))

    def test_conflito_posterior_e_checkpoint_nao_reativam_heuristica(self):
        escopo=EscopoPortal(A);escopo.observar(A,{},True)
        escopo.observar(A,{'canonical':A+'web/um','friendly_url':A+'web/dois'},True)
        self.assertEqual(escopo.site,'')
        self.assertEqual(escopo.fonte_site,'metadados_conflitantes')
        escopo=EscopoPortal(A,escopo.estado());escopo.observar(A,{},True)
        self.assertEqual(escopo.site,'')
        self.assertFalse(escopo.outro(A+'web/um'))

    def test_identidades_explicitas_em_observacoes_distintas_conflitam(self):
        escopo=EscopoPortal(A)
        escopo.observar(A,{'canonical':A+'web/um'},True)
        escopo.observar(A,{'friendly_url':A+'web/dois'},True)
        self.assertEqual(escopo.site,'')
        self.assertEqual(escopo.fonte_site,'metadados_conflitantes')

    def test_parametros_funcionais_e_multiplos_indices_nao_comprovam_correspondencia(self):
        for key in ('c','e','delta','categoria'):
            with self.subTest(key=key):
                ua=A+'catalogo?cur=43&'+key+'=1';ub=B+'catalogo?cur=43&'+key+'=2'
                f=PoliticaURLs(bases=(A,B));f.evidencias[0][chave_evidencia(ua)]='listagem_editorial'
                self.assertFalse(f.avaliar((ua,ub,['43']),'Paginação'))
        for qa,qb in (('cur=43&offset=0','cur=43&offset=20'),
                      ('_a_cur=43&_b_cur=2','_x_cur=43&_y_cur=3'),
                      ('cur=43','cur=43&page=2')):
            with self.subTest(query=qb):
                f=PoliticaURLs(bases=(A,B));f.evidencias[0][chave_evidencia(A+'catalogo?'+qa)]='listagem_editorial'
                self.assertFalse(f.avaliar((A+'catalogo?'+qa,B+'catalogo?'+qb,['43']),'Paginação'))

    def test_origem_nao_configurada_ou_fragmento_distinto_nao_recebem_inferencia(self):
        ua=A+'catalogo?cur=43'
        for ub in ('https://nao-autorizado.test/catalogo?cur=43',B+'catalogo?cur=43#outra-aba','http://[invalid'):
            with self.subTest(contraparte=ub):
                f=PoliticaURLs(bases=(A,B));f.evidencias[0][ua]='listagem_editorial'
                self.assertFalse(f.avaliar((ua,ub,['43']),'Paginação'))

    def test_normalizacao_legada_preserva_evidencia_documental_colidente(self):
        estado={'finalidades_observadas':[{},
            {B+'catalogo?b=2&cur=43&a=1':'documental',
             B+'catalogo?a=1&cur=43&b=2':'listagem_editorial'}]}
        f=PoliticaURLs(estado,(A,B));f.evidencias[0][A+'catalogo?a=1&b=2&cur=43']='listagem_editorial'
        self.assertFalse(f.avaliar((A+'catalogo?a=1&b=2&cur=43',B+'catalogo?a=1&b=2&cur=43',['43']),'Paginação'))

    def test_inferencia_simetrica_e_primeira_pagina_preservada(self):
        for lado in (0,1):
            for indice in (1,43):
                urls=(A+'catalogo?_x_cur='+str(indice),B+'catalogo?_y_cur='+str(indice))
                f=PoliticaURLs(bases=(A,B));f.evidencias[lado][urls[lado]]='listagem_editorial'
                self.assertEqual(f.avaliar((*urls,['Próximo']),'Paginação'),indice>1)

    def test_servicos_consema_e_radio_em_contexto_documental(self):
        for rota,label in (('servicos/simcar','SIMCAR'),('servicos/simlam','SIMLAM'),
            ('servicos/sisflora','SISFLORA'),('consema/resolucoes','Resoluções'),
            ('consema/documentos','Documentos'),('consema/servicos','Serviços'),
            ('radio-paiaguas/legislacao','Legislação'),('radiologia/servicos','Serviços')):
            with self.subTest(rota=rota):
                self.assertFalse(PoliticaURLs().avaliar((A+rota+'?cur=43',B+rota+'?cur=43',[label]),'Paginação'))

    def test_motor_respeita_metadados_explicitos_obtidos_apos_navegacao(self):
        import test_update18 as fixture
        ra,rb='https://orgao.xy.gov.br/','https://orgao.lab.xy.gov.br/'
        def graph(u):
            base=ra if u.startswith(ra) else rb
            if u==base:return [fixture.opcao('Institucional',base+'web/principal/institucional','Menu'),
                fixture.opcao('Outro portal',base+'web/outro','Menu')]
            return []
        def meta(u):
            base=ra if u.startswith(ra) else rb
            return {'portal':{'canonical':base+'web/principal/inicio'}}
        with patch.multiple(fixture,A=ra,B=rb):r,opened,_=fixture.executar(graph,metadados=meta)
        self.assertIn(ra+'web/principal/institucional',opened)
        self.assertIn(rb+'web/principal/institucional',opened)
        self.assertFalse(any('web/outro' in u for u in opened))
        self.assertEqual(r['andamento']['pares_comparados'],2)

    def test_motor_radio_tv_primeira_pagina_servicos_consema_e_audios(self):
        from test_update18 import A as ra,B as rb,executar,opcao
        for exclusiva in (ra,rb):
            with self.subTest(audios_em=exclusiva):
                def graph(u):
                    base=ra if u.startswith(ra) else rb
                    if u==base:
                        return [opcao('Rádio',base+'radio-paiaguas','Menu'),opcao('TV',base+'tv-paiaguas','Menu')]+[
                            opcao(n,base+'servicos/'+n.lower(),'Serviços') for n in ('SIMCAR','SIMLAM','SISFLORA')]+[
                            opcao('Resoluções',base+'consema/resolucoes?cur=2','CONSEMA'),
                            opcao('Documentos',base+'consema/documentos?cur=2','CONSEMA')]+([
                            opcao('ÁUDIOS',base+'audio.pdf','Menu')] if base==exclusiva else [])
                    if u in (base+'radio-paiaguas',base+'tv-paiaguas'):
                        return [opcao('1',u+'?_publisher_INSTANCE_X_cur=1','Paginação'),
                                opcao('43',u+'?_publisher_INSTANCE_X_cur=43','Paginação'),
                                opcao('Próximo',u+'?_publisher_INSTANCE_X_cur=115','Paginação')]
                    return []
                r,opened,_=executar(graph)
                self.assertEqual(r['andamento']['pares_comparados'],8)
                self.assertFalse(any('_cur=' in u for u in opened))
                self.assertTrue(any(d.get('elemento')=='ÁUDIOS' for d in r['divergencias']))
                for base in (ra,rb):
                    for n in ('simcar','simlam','sisflora'):self.assertIn(base+'servicos/'+n,opened)
                    for kind in ('resolucoes','documentos'):self.assertIn(base+'consema/'+kind+'?cur=2',opened)

    def test_motor_inferencia_html_unilateral_normalizada_sobrevive_retomada(self):
        from test_update18 import A as ra,B as rb,executar,opcao
        from ambidiff import checkpoints as cp
        stop=threading.Event();snaps=[]
        def graph(u):
            base=ra if u.startswith(ra) else rb
            if u==base:return [opcao('43',base+'catalogo?b=2&cur=43&a=1','Paginação'),
                opcao('Institucional',base+'institucional','Menu')]+([opcao('ÁUDIOS',ra+'audio.pdf','Menu')] if base==ra else [])
            return []
        def meta(u):return {'referencias_finalidade':[
            {'url':ra+'catalogo?b=2&cur=43&a=1','finalidade':'listagem_editorial'}]} if u==ra else {}
        def log(msg):
            if msg.startswith('[PRD/DES] 1 pares'):stop.set()
        r,opened,_=executar(graph,metadados=meta,parar=stop,ao_log=log,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        self.assertEqual(r['estado_execucao'],'interrompido')
        estado=cp.validar(snaps[-1]['retomada'])
        resumed,reopened,_=executar(graph,metadados=meta,retomada=cp.empacotar(estado))
        self.assertFalse(any('catalogo?' in u for u in opened+reopened))
        self.assertEqual(resumed['andamento']['pares_comparados'],2)
        self.assertEqual(resumed['filtro_urls']['paginacoes_assimetricas_com_evidencia'],1)
        self.assertTrue(any(d.get('elemento')=='ÁUDIOS' for d in resumed['divergencias']))


class IntegracaoCheckpointStage4Tests(unittest.TestCase):
    def test_conflito_com_site_explicito_na_url_inicial_continua_inconclusivo(self):
        base = 'https://orgao.test/web/principal'
        escopo = EscopoPortal(base)
        escopo.observar(base, {'canonical': 'https://orgao.test/web/alternativo'}, raiz=True)
        estado = escopo.estado()
        restaurado = EscopoPortal(base, estado)

        self.assertEqual(restaurado.estado(), estado)
        self.assertEqual(restaurado.fonte_site, 'metadados_conflitantes')
        self.assertEqual(restaurado.site, '')
        self.assertFalse(restaurado.outro('https://orgao.test/web/alternativo/noticias'))

    def test_diagnostico_recuperado_conserva_fontes_de_identidade(self):
        from ambidiff import checkpoints as cp
        from test_update18 import A as ra, B as rb, executar

        def metadados(url):
            portal = {'canonical': url + 'web/principal/inicio'}
            if url == rb:
                portal['friendly_url'] = url + 'web/alternativo/inicio'
            return {'portal': portal}

        copias = []
        resultado, _, _ = executar(lambda _: [], metadados=metadados,
                                   checkpoint=lambda d: copias.append(copy.deepcopy(d)))
        snapshot = copias[-1]
        original = copy.deepcopy(snapshot)
        recuperado = cp.recuperar(snapshot)
        obtido = recuperado['filtro_urls']['escopos_portais']

        self.assertEqual(obtido, resultado['filtro_urls']['escopos_portais'])
        self.assertEqual([p['fonte_identidade'] for p in obtido],
                         ['metadados_raiz', 'metadados_conflitantes'])
        self.assertEqual(snapshot, original)


if __name__=='__main__':unittest.main()
