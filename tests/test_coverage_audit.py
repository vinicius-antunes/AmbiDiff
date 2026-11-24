"""Auditoria com navegação simulada, checkpoint real e histórico local."""
import csv
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ambidiff.checkpoints import gravar, validar
from ambidiff.coverage_audit import AuditoriaCobertura, caminho_auditoria
from ambidiff.paired import executar_pareado
from ambidiff.urlfilter import PoliticaURLs
from test_update18 import A, B, cadeia, executar, opcao


RID = '20261124_100000_aaaaaa'
NOVO = '20261124_100001_bbbbbb'
LEGADO = '20261124_100002_cccccc'


def grafo(url):
    base = A if url.startswith(A) else B
    if url == base:
        opcoes = [
            opcao('SIMCAR',base+'web/verde/servicos/simcar','Serviços'),
            opcao('Rádio',base+'radio-paiaguas','Menu'),
            opcao('Portal vizinho',base+'web/outro/institucional','Menu'),
            opcao('Acesso pendente',base+'falha','Menu'),
            opcao('Documento',base+'manual.pdf','Documentos'),
        ]
        if base == A:
            opcoes.extend((opcao('ÁUDIOS',base+'audio.pdf','Menu'),
                           opcao('Atendimento exclusivo',base+'setor-sol','Menu')))
        return opcoes
    if url == base+'radio-paiaguas':
        return [opcao('Página 43',url+'?_x_cur=43','Paginação'),
                opcao('SIMCAR',base+'web/verde/servicos/simcar','Serviços')]
    return []


def metadados(url):
    base = A if url.startswith(A) else B
    return {'portal':{'canonical':base+'web/verde/inicio'}} if url==base else {}


class CoberturaTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pasta = Path(temp.name)
        self.checkpoint = self.pasta/'checkpoint.json'

    def executar(self, mapa, auditoria=None, **kw):
        def executar_com_auditoria(*a,**opcoes):
            return executar_pareado(*a,auditoria_cobertura=auditoria,**opcoes)
        with patch('test_update18.executar_pareado',side_effect=executar_com_auditoria):
            return executar(mapa,checkpoint=lambda voz:gravar(self.checkpoint,voz),**kw)

    def ler(self, rid=RID):
        return json.loads(caminho_auditoria(self.pasta,rid).read_bytes())

    def test_decisoes_completas_sem_alterar_navegacao_ou_divs(self):
        args = {'falhas':(B+'falha',),'metadados':metadados}
        esperado, urls, _ = self.executar(grafo,**args)
        obtido, com_auditoria, _ = self.executar(grafo,AuditoriaCobertura(self.pasta,RID),**args)
        self.assertEqual(com_auditoria,urls)
        for chave in ('divergencias','estados_pares','filtro_urls','documentos_verificados','diagnosticos_pares'):
            self.assertEqual(obtido[chave],esperado[chave],chave)
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in obtido['divergencias']))
        doc = self.ler()
        por_url = {r['url_a']:r for r in doc['referencias']}
        self.assertEqual(por_url[A]['status'],'comparada')
        radio = next(r for r in doc['referencias'] if r['categoria']=='paginacao_editorial')
        self.assertEqual(radio['status'],'excluida')
        self.assertFalse(radio['comparacao_html'])
        self.assertEqual(radio['paginacao'][0],[{'parametro':'cur','valor':43}])
        self.assertEqual(radio['origem']['pagina_a'],A+'radio-paiaguas')
        self.assertTrue(radio['motivo_filtro'])
        vizinho = por_url[A+'web/outro/institucional']
        self.assertEqual((vizinho['status'],vizinho['categoria']),('excluida','outro_portal'))
        self.assertEqual(vizinho['fontes_portal'],['metadados_raiz','metadados_raiz'])
        self.assertEqual(vizinho['origem']['pagina_a'],A)
        servicos = [r for r in doc['referencias'] if r['url_a']==A+'web/verde/servicos/simcar']
        self.assertEqual(len(servicos),1)
        self.assertTrue(servicos[0]['excecao_estrutural'])
        self.assertEqual(servicos[0]['status'],'comparada')
        self.assertEqual(por_url[A+'manual.pdf']['categoria'],'documental')
        self.assertEqual(por_url[A+'manual.pdf']['status'],'nao_html')
        self.assertEqual(por_url[A+'setor-sol']['status'],'sem_contraparte')
        self.assertEqual(por_url[A+'falha']['status'],'falha')
        self.assertIn('HTTP',por_url[A+'falha']['tipos_falha'])
        self.assertEqual(doc['resumo']['referencias_unicas'],len(doc['referencias']))
        self.assertEqual(doc['resumo']['por_categoria_e_status']['paginacao_editorial'],{'excluida':1})
        self.assertNotIn('referencias',json.loads(self.checkpoint.read_bytes())['retomada']['estado'])

    def test_auditoria_ultrapassa_amostra_e_distingue_queries_sanitizadas(self):
        def muitos(url):
            base = A if url.startswith(A) else B
            if url==base:
                return [opcao('Rádio',base+'radio-paiaguas','Menu')]
            if url==base+'radio-paiaguas':
                return [opcao(f'Página {n}',f'{url}?cur={n}&token=cred-sintetica','Paginação') for n in range(2,124)]
            return []
        r,_,_ = self.executar(muitos,AuditoriaCobertura(self.pasta,RID))
        doc = self.ler()
        excluidas = [l for l in doc['referencias'] if l['status']=='excluida']
        self.assertEqual(len(r['filtro_urls']['referencias']),100)
        self.assertEqual(len(excluidas),122)
        self.assertEqual(len({x['id_referencia'] for x in excluidas}),122)
        self.assertNotIn('cred-sintetica',json.dumps(doc))
        self.assertEqual({x['url_a'] for x in excluidas},{A+'radio-paiaguas'})

    def test_interrupcao_retomada_com_rastreio_e_checkpoint_legado(self):
        for original in (RID,LEGADO):
            with self.subTest(original=original):
                sinal = threading.Event()
                def parar(mensagem):
                    if mensagem.startswith('[PRD/DES] 1 pares'):
                        sinal.set()
                anterior = AuditoriaCobertura(self.pasta,original) if original==RID else None
                parcial,_,_ = self.executar(cadeia(4),anterior,parar=sinal,ao_log=parar)
                self.assertEqual(parcial['andamento']['pares_comparados'],1)
                snap = json.loads(self.checkpoint.read_bytes())['retomada']
                self.assertTrue(validar(snap)['fila'])
                if anterior:
                    doc = self.ler(original)
                    self.assertEqual(doc['marco'],'interrupcao_final')
                    self.assertEqual(doc['resumo']['por_status']['comparada'],1)
                    self.assertEqual(doc['checkpoint_sha256'],snap['sha256_estado'])
                nova = AuditoriaCobertura(self.pasta,NOVO,retomada_de=original,retomada=snap)
                final,abertas,_ = self.executar(cadeia(4),nova,retomada=snap)
                self.assertNotIn(A,abertas)
                self.assertEqual(final['andamento']['pares_comparados'],4)
                resumo = self.ler(NOVO)
                self.assertEqual(resumo['historico_anterior_incompleto'],original==LEGADO)
                self.assertEqual(resumo['resumo']['por_status']['comparada'],4)
                self.assertEqual(resumo['retomada_de'],original)
                self.assertEqual(len({r['id_referencia'] for r in resumo['referencias']}),len(resumo['referencias']))
                self.assertEqual([d['id'] for d in parcial['divergencias'] if d['elemento']=='ÁUDIOS'],
                                 [d['id'] for d in final['divergencias'] if d['elemento']=='ÁUDIOS'])

    def test_provas_e_reconsideracao_registram_observacao_sem_provar_equivalencia(self):
        auditoria = AuditoriaCobertura(self.pasta,RID)
        politica = PoliticaURLs(bases=(A,B),observar_decisao=auditoria.observar_politica)
        p = (A+'catalogo?cur=43',B+'catalogo?cur=43',['43'])
        politica.evidencias[0][p[0]] = 'listagem_editorial'
        politica.evidencias[1][p[1]] = 'listagem_editorial'
        self.assertTrue(politica.avaliar(p))
        politica.evidencias[0][p[0]] = 'documental'
        politica.evidencias[1][p[1]] = 'documental'
        self.assertFalse(politica.avaliar(p))
        seguro = auditoria._linha(tuple(p[:2]),'fixture',{}, {},politica.registros[p[:2]],None,False,{})
        self.assertEqual(seguro['evidencia_utilizada'],['documental','documental'])
        self.assertIn('paginacao_editorial',seguro['exclusoes_observadas'])
        self.assertTrue(seguro['reconsiderada'])
        self.assertFalse(seguro['comparacao_html'])

    def test_historico_api_csv_json_sanitizacao_e_exclusao(self):
        from web import server
        auditoria = AuditoriaCobertura(self.pasta,RID)
        segredo = 'valor-super-secreto'
        auditoria.observar(('https://usu:senha-falsa@origem.test/token/'+segredo+'?token=segredo-query',''),
                           {'pagina_a':'https://origem.test/?cookie=segredo-cookie','trilha':['Authorization: Bearer '+segredo]},
                           status='sem_contraparte',motivo='=2+2')
        self.executar(cadeia(2),auditoria)
        historico = self.pasta/'historico.json'
        historico.write_text(json.dumps([{'id':RID},{'id':LEGADO}]),encoding='utf-8')
        (self.pasta/f'comparacao_{RID}.json').write_text('{}',encoding='utf-8')
        with patch.object(server,'PASTA',self.pasta),patch.object(server,'HISTORY_PATH',historico),server.app.test_client() as client:
            hist = client.get('/api/historico').get_json()
            self.assertEqual([r['auditoria_cobertura'] for r in hist],[True,False])
            prefix = '/api/auditoria-cobertura/'
            self.assertEqual(client.get(prefix+LEGADO+'/json').status_code,404)
            self.assertEqual(client.get(prefix+RID+'/html').status_code,400)
            with client.get(prefix+RID+'/json',buffered=True) as resposta:
                self.assertEqual(resposta.status_code,200)
                raw = resposta.get_data(as_text=True)
            with client.get(prefix+RID+'/csv',buffered=True) as resposta:
                self.assertEqual(resposta.status_code,200)
                texto = resposta.get_data(as_text=True)
            for termo in (segredo,'senha-falsa','segredo-query','segredo-cookie'):
                self.assertNotIn(termo,raw+texto)
            linhas = list(csv.DictReader(texto.lstrip('\ufeff').splitlines(),delimiter=';'))
            self.assertEqual([(x['id_referencia'],x['status']) for x in linhas],
                [(x['id_referencia'],x['status']) for x in json.loads(raw)['referencias']])
            self.assertIn("'=2+2",texto)
            from ambidiff.storage import excluir_execucoes
            excluir_execucoes(self.pasta,historico,[RID])
            self.assertEqual(client.get(prefix+RID+'/csv').status_code,404)

    def test_falha_na_gravacao_da_auditoria_preserva_checkpoint_e_resultado(self):
        auditoria = AuditoriaCobertura(self.pasta,RID)
        with patch.object(auditoria,'salvar',side_effect=OSError('Disco indisponível')):
            resultado,_,_ = self.executar(cadeia(3),auditoria)
        self.assertEqual(resultado['andamento']['pares_comparados'],3)
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in resultado['divergencias']))
        self.assertTrue(validar(json.loads(self.checkpoint.read_bytes())['retomada']))
        self.assertFalse(auditoria.caminho.exists())


from test_update17 import BrowserUI17Tests as _BrowserUI


class HistoricoCoberturaChromiumTests(unittest.TestCase):
    setUp = _BrowserUI.setUp

    def test_download_aparece_apenas_na_execucao_com_auditoria(self):
        from web import server
        historico = [{'id':rid,'data':data,'total':1,'site_nome':'Portal sintético','site_id':'fixture'}
                     for rid,data in ((RID,'24/11/2026 10:00:00'),(LEGADO,'23/11/2026 10:00:00'))]
        server.HISTORY_PATH.write_text(json.dumps(historico),encoding='utf-8')
        gravar(caminho_auditoria(self.root,RID),{
            'versao':1,'execucao_id':RID,
            'referencias':[{'id_referencia':'par-fixture','execucao_id':RID,'status':'comparada'}]})
        self.p.evaluate("nav('historico')")
        self.p.locator('#history-list .folder-card > summary').click()
        auditar = self.p.get_by_text('Exportar auditoria de cobertura',exact=True)
        self.assertEqual(auditar.count(),1)
        auditar.click()
        self.assertEqual(self.p.get_by_role('link',name='Baixar auditoria de cobertura em CSV').count(),1)
        self.assertTrue(self.p.get_by_text('Auditoria detalhada indisponível para esta execução.',exact=True).is_visible())
        with self.p.expect_download() as download:
            self.p.get_by_role('link',name='Baixar auditoria de cobertura em JSON').click()
        self.assertEqual(download.value.suggested_filename,f'auditoria_cobertura_{RID}.json')


# Evita que o unittest descubra novamente a suíte compartilhada pelo setUp.
del _BrowserUI
