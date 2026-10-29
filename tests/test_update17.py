"""Melhorias 13–17: fixtures sintéticas locais; sem portais corporativos."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ambidiff.core import Pagina,Item
from ambidiff import checkpoints as cp
from test_intermat import pipeline,A,B,RID


class CheckpointTests(unittest.TestCase):
    def test_cache_paginas_concluidas_preserva_campos_e_invalida_substituicao(self):
        from dataclasses import asdict,replace
        p=Pagina(A,'','Portal',[Item('Opção','ÁUDIOS','ÁUDIOS')],['Início'])
        cache=cp.PaginasSerializadas()
        self.assertEqual(cache.converter({A:p}),{A:asdict(p)})
        cache.converter({A:p});self.assertEqual(cache.convertidas,1);self.assertEqual(cache.reutilizadas,1)
        p2=replace(p,titulo='Novo');self.assertEqual(cache.converter({A:p2})[A]['titulo'],'Novo')
        self.assertEqual(cache.convertidas,2)

    def test_falha_gravacao_preserva_checkpoint_valido_e_limpa_temporario(self):
        snaps=[];pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'checkpoint.json';io=cp.gravar(path,snaps[-1]);antes=path.read_bytes()
            with patch('ambidiff.checkpoints.os.replace',side_effect=OSError('Disco indisponível')):
                with self.assertRaises(OSError):cp.gravar(path,snaps[0])
            self.assertEqual(antes,path.read_bytes());self.assertEqual(list(Path(td).glob('*.tmp')),[])
            estado=cp.validar(json.loads(path.read_text())['retomada']);self.assertTrue(estado['brutos'])
            self.assertGreater(io['bytes'],0)

    def test_checkpoint_v1_anterior_corrupcao_e_retomada_sem_duplicar(self):
        snaps=[];r,_=pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        antigo=cp.empacotar(snaps[-1]['retomada']['estado'])
        self.assertEqual(cp.validar(antigo)['configuracao']['url_a'],A)
        bad=copy.deepcopy(antigo);bad['estado']['brutos']=[]
        with self.assertRaisesRegex(ValueError,'integridade'):cp.validar(bad)
        with self.assertRaises(ValueError):cp.validar({'versao_checkpoint':1})
        retomado,abertas=pipeline(retomada=antigo)
        self.assertNotIn(A,abertas);self.assertEqual(r['divergencias'][0]['id'],retomado['divergencias'][0]['id'])
        self.assertEqual(len({d['id'] for d in retomado['divergencias']}),len(retomado['divergencias']))

    def test_instrumentacao_e_agendamento_sem_disparos_duplicados(self):
        snaps=[];pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        def salvar(d):snaps.append(copy.deepcopy(d));return {'serializacao_json':.01,'gravacao':.02,'bytes':100}
        r,_=pipeline(n=100,retomada=snaps[0]['retomada'],checkpoint=salvar)
        m=r['metricas'];self.assertLess(m['contagens']['checkpoints_salvos'],8)
        self.assertGreater(m['tempos_segundos']['checkpoint_conversao_paginas'],0)
        self.assertGreater(m['tempos_segundos']['checkpoint_gravacao'],0)
        self.assertTrue(any('ÁUDIOS' in d['elemento'] for d in r['divergencias']))


class ShareTests(unittest.TestCase):
    def row(self,a,b,endpoint='https://www.facebook.com/sharer/sharer.php',key='u'):
        from urllib.parse import urlencode
        return {'id':'DIV-0001','tipo':'Redirecionamento','elemento':'Compartilhar',
            'destino_a':endpoint+'?'+urlencode({key:a}),'destino_b':endpoint+'?'+urlencode({key:b})}
    def test_endpoints_conhecidos_codificacao_parametros_e_tipo_verificado(self):
        from ambidiff.relevance import classificar,preparar
        for endpoint,key in [('https://www.facebook.com/sharer/sharer.php','u'),('https://twitter.com/intent/tweet','url'),('https://x.com/intent/tweet','url')]:
            row=self.row(A+'noticia?c=1&e=2',B+'noticia?e=2&c=1',endpoint,key)
            for tipo in ('Redirecionamento','Destino verificado'):
                row['tipo']=tipo;self.assertEqual(classificar(row,{'PRD':A,'DES':B})[0],'baixa')
            r=preparar({'ambientes':{'PRD':A,'DES':B},'divergencias':[row]})
            self.assertEqual(r['resumo_compartilhamento']['registros'],1);self.assertEqual(r['registros_originais'],[row])
            from ambidiff.diagnostics import montar_diagnostico
            diag=montar_diagnostico({'ambientes':{'PRD':A,'DES':B},'divergencias':[row]})
            self.assertEqual(len(diag['equivalencias_compartilhamento']),1)
        self.assertEqual(classificar(self.row(A+'~pagina',B+'%7epagina'),{'PRD':A,'DES':B})[0],'baixa')

    def test_caminho_query_hosts_incorretos_e_urls_invalidas_permanecem(self):
        from ambidiff.relevance import classificar
        for a,b in [(A+'um',B+'dois'),(A+'n?c=1',B+'n?c=2'),(B+'n',A+'n'),(A+'n',A+'n'),('https://','https://'),(A+'n',B+'n%2Foutro'),(A+'n#um',B+'n#dois')]:
            with self.subTest(a=a,b=b):self.assertEqual(classificar(self.row(a,b),{'PRD':A,'DES':B})[0],'relevante')
        for endpoint in ('https://social.test/share','https://facebook.com.evil.test/sharer/sharer.php'):
            self.assertEqual(classificar(self.row(A,B,endpoint),{'PRD':A,'DES':B})[0],'relevante')
        row=self.row(A,B);row.update(tipo='Destino verificado',situacao='LINK_INACESSIVEL')
        self.assertEqual(classificar(row,{'PRD':A,'DES':B})[0],'relevante')
        row.update(tipo='Opção',situacao='Ausente');self.assertEqual(classificar(row,{'PRD':A,'DES':B})[0],'relevante')
        env={'PRD':A+'prd','DES':A+'des'}
        self.assertEqual(classificar(self.row(A+'prd/n',A+'des/n'),env)[0],'baixa')
        self.assertEqual(classificar(self.row(A+'prd/n',A+'prd/n'),env)[0],'relevante')


def portal_editorial(p):
    base=A if p.url.startswith(A) else B
    if p.url==base:
        p.itens=[Item('Opção','Notícia '+str(i),'Notícia '+str(i),local='Notícias',destino=base+'noticias/'+str(i)) for i in range(1,301)]
        p.itens.append(Item('Opção','Serviço público','Serviço público',destino=base+'servicos/999',local='Menu'))
        if base==A:p.itens.append(Item('Opção','ÁUDIOS','ÁUDIOS',local='Menu',destino=base+'audio.pdf'))
    else:
        p.itens=[]
        if '/noticias/' in p.url:
            p.itens=[Item('Opção','Voltar','Voltar',local='Notícias',destino=base)]
            if p.url.endswith('/1'):p.itens.append(Item('Opção','Consulta importante','Consulta importante',destino=base+'consulta/1000',local='Serviços'))


class StrategyTests(unittest.TestCase):
    def vazio(self):
        snaps=[];pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        return snaps[0]['retomada']

    def test_progressiva_padrao_amostra_editorial_preserva_importantes_e_continua(self):
        snaps=[];r,abertas=pipeline(n=2,estrategia='progressiva',orcamento_minutos=0,retomada=self.vazio(),ajustar=portal_editorial,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        self.assertEqual(r['cobertura']['estrategia'],'progressiva');self.assertEqual(r['motivo_encerramento'],'estrategia_editorial')
        self.assertEqual(r['cobertura']['pares_adiados_editoriais'],297)
        self.assertIn(A+'servicos/999',abertas);self.assertIn(A+'consulta/1000',abertas)
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))
        self.assertEqual(r['situacao_analise'],'parcial')
        self.assertLess(abertas.index(A+'servicos/999'),abertas.index(A+'noticias/1'))
        r2,mais=pipeline(n=2,retomada=snaps[-1]['retomada'],ajustar=portal_editorial,estrategia='profunda',orcamento_minutos=0)
        self.assertNotIn(A,mais);self.assertEqual(r2['andamento']['pares_pendentes'],0)
        self.assertEqual(r['divergencias'][0]['id'],r2['divergencias'][0]['id'])
        self.assertEqual(len(mais),594)

    def test_mais_de_mil_paginas_importantes_sem_teto_funcional(self):
        r,opened=pipeline(n=1005,ciclo=True,estrategia='profunda',orcamento_minutos=0)
        self.assertEqual(r['paginas']['PRD'],1005);self.assertEqual(len(set(opened)),2010)
        self.assertEqual(r['andamento']['pares_pendentes'],0)

    def test_orcamento_cooperativo_preserva_fila_e_retomada(self):
        from ambidiff.strategy import Escopo
        with patch('ambidiff.strategy.time.perf_counter',return_value=0):e=Escopo('progressiva',20)
        with patch('ambidiff.strategy.time.perf_counter',return_value=1201):self.assertTrue(e.expirou())
        contador={'n':0};snaps=[]
        def ajustar(p):contador['n']+=1
        with patch.object(Escopo,'expirou',lambda _:contador['n']>=4):
            r,_=pipeline(n=8,estrategia='progressiva',orcamento_minutos=20,ajustar=ajustar,retomada=self.vazio(),checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        self.assertEqual(r['motivo_encerramento'],'orcamento');self.assertGreater(r['andamento']['pares_pendentes'],0)
        self.assertEqual(r['situacao_analise'],'parcial');self.assertNotEqual(r['estado_execucao'],'interrompido')
        r2,opened=pipeline(n=8,retomada=snaps[-1]['retomada'])
        self.assertEqual(r2['paginas']['PRD'],8);self.assertNotIn(A,opened)

    def test_checkpoint_anterior_permanece_profundo_sem_orcamento(self):
        old=self.vazio();old['estado']['configuracao'].pop('estrategia');old['estado']['configuracao'].pop('orcamento_minutos')
        r,_=pipeline(retomada=cp.empacotar(old['estado']))
        self.assertEqual(r['cobertura']['estrategia'],'dinamica');self.assertEqual(r['cobertura']['orcamento_minutos'],0)

    def test_liferay_w_sem_contexto_editorial_nao_e_adiado(self):
        def ajustar(p):
            base=A if p.url.startswith(A) else B
            idx=int(p.url.rsplit('/',1)[-1] or '0')
            p.itens=[Item('Opção','Página '+str(idx+1),'Página '+str(idx+1),destino=base+'w/'+str(idx+1),local='Conteúdo principal')] if idx<7 else []
        r,_=pipeline(n=8,ajustar=ajustar)
        self.assertEqual(r['paginas']['PRD'],8);self.assertFalse(r['cobertura']['pares_adiados_editoriais'])

    def test_continuacao_progressiva_avanca_sem_repetir_representantes(self):
        snaps=[];r,_=pipeline(n=2,estrategia='progressiva',orcamento_minutos=0,retomada=self.vazio(),ajustar=portal_editorial,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        r2,opened=pipeline(n=2,retomada=snaps[-1]['retomada'],ajustar=portal_editorial)
        self.assertEqual(r2['cobertura']['pares_adiados_editoriais'],294)
        self.assertFalse(set(opened)&{A+'noticias/'+str(i) for i in range(1,4)})
        self.assertEqual(len(r2['segmentos_coleta'][-2]['amostras_editoriais']),3)


def report_fixture(root,n=3):
    from ambidiff.storage import atomic_json
    rows=[{'id':f'DIV-{i:04}','tipo':'Opção','elemento':'Item '+str(i),'local':'Menu '+str(i),
        'presente_em':'PRD' if i%2 else 'DES','nao_identificado_em':'DES' if i%2 else 'PRD',
        'descricao':'Diferença sintética '+str(i),'url_presente':A,'url_comparada':B} for i in range(1,n+1)]
    atomic_json(root/f'comparacao_{RID}.json',{'id':RID,'versao':'1.5','site_nome':'Portal sintético',
        'ambientes':{'PRD':A,'DES':B},'divergencias':rows,'situacao_analise':'parcial','paginas':{'PRD':1,'DES':1}})


class BulkSelectionTests(unittest.TestCase):
    def test_milhares_todas_exclusoes_exportacao_csv_e_limpar_sem_revisar(self):
        from ambidiff.storage import selecionar_lote,excluir_div,registrar_revisao,ler_selecao,ler_original
        from web import server
        import csv,io
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            root=Path(td);report_fixture(root,2200);server.STATE['status']='pronto'
            original=(root/f'comparacao_{RID}.json').read_bytes()
            excluir_div(root,RID,'DIV-0002');registrar_revisao(root,RID,'DIV-0001','confirmada')
            r=selecionar_lote(root,RID,'todas');self.assertEqual(len(r['ids_selecionados']),2199);self.assertNotIn('DIV-0002',r['ids_selecionados'])
            response=server.app.test_client().get(f'/download/{RID}/csv?selecionadas=1')
            rows=list(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig')),delimiter=';'));response.close()
            self.assertEqual(len(rows),2199)
            selecionar_lote(root,RID,'limpar');self.assertFalse(ler_selecao(root,RID))
            self.assertEqual(json.loads((root/f'revisoes_{RID}.json').read_text()),{'DIV-0001':'confirmada'})
            self.assertEqual(original,(root/f'comparacao_{RID}.json').read_bytes())

    def test_filtros_combinados_id_baixa_relevancia_e_preserva_selecao_fora(self):
        from ambidiff.storage import selecionar_lote,selecionar,filtrar_divergencias
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);report_fixture(root,60);selecionar(root,RID,'DIV-0002',True)
            r=selecionar_lote(root,RID,'filtradas',{'busca':'Item','lado':'PRD','tipo':'Opção','revisao':'pendentes'})
            self.assertEqual(len(r['ids_selecionados']),31)
            r=selecionar_lote(root,RID,'filtradas',{'busca':'DIV-0040','lado':'PRD','categoria':'Não correspondente'})
            self.assertIn('DIV-0040',r['ids_selecionados'])
            rows=[{'id':'DIV-0001','classificacao':'baixa'},{'id':'DIV-0002','classificacao':'relevante'}]
            self.assertEqual(len(filtrar_divergencias(rows,{})),1)
            self.assertEqual(len(filtrar_divergencias(rows,{'mostrar_todas':True})),2)

    def test_grupos_parciais_e_falha_de_gravacao_preserva_selecao(self):
        from test_update12 import ExportTests
        from ambidiff.storage import selecionar,selecionar_lote,ler_selecao
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ExportTests().preparar(root)
            selecionar(root,RID,'DIV-0002',True);self.assertEqual(ler_selecao(root,RID),{'DIV-0002'})
            selecionar_lote(root,RID,'todas');self.assertEqual(ler_selecao(root,RID),{'DIV-0001','DIV-0002','DIV-0003'})
            before=(root/f'selecoes_{RID}.json').read_bytes()
            with patch('ambidiff.storage.os.replace',side_effect=OSError('Disco cheio')):
                with self.assertRaises(OSError):selecionar_lote(root,RID,'limpar')
            self.assertEqual(before,(root/f'selecoes_{RID}.json').read_bytes())
            self.assertFalse(list(root.glob('*.tmp')))

    def test_api_lote_validacao_gravacao_e_padrao_progressivo(self):
        from web import server
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            root=Path(td);report_fixture(root);server.STATE['status']='pronto';client=server.app.test_client()
            self.assertEqual(client.put(f'/api/relatorio/{RID}/selecao',json={'acao':'todas'}).status_code,200)
            for data in ({'acao':'inventada'},{'acao':'filtradas','filtros':[]},{'acao':'todas','ids':['DIV-9999']}):
                self.assertEqual(client.put(f'/api/relatorio/{RID}/selecao',json=data).status_code,400)
            with patch('ambidiff.storage.atomic_json',side_effect=OSError('Disco')):
                r=client.put(f'/api/relatorio/{RID}/selecao',json={'acao':'limpar'});self.assertEqual(r.status_code,500);self.assertIn('preservada',r.get_json()['erro'])
            with patch('web.server.threading.Thread') as worker:
                r=client.post('/api/comparar',json={'url_a':A,'url_b':B});self.assertEqual(r.status_code,200)
                params=worker.call_args.kwargs['args'][0]
                self.assertEqual(params['estrategia'],'dinamica');self.assertEqual(params['orcamento_minutos'],0);self.assertTrue(params['varredura_inteligente'])
            server.STATE['status']='pronto'
            for valor in (-1,True,'20',None,1441):
                with patch('web.server.threading.Thread') as worker:
                    self.assertEqual(client.post('/api/comparar',json={'url_a':A,'url_b':B,'orcamento_minutos':valor}).status_code,400)
                    worker.assert_not_called()

    def test_falha_pdf_preserva_original_e_retorna_erro_claro(self):
        from web import server
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            root=Path(td);report_fixture(root);server.STATE['status']='pronto'
            before=(root/f'comparacao_{RID}.json').read_bytes()
            with patch('ambidiff.exports.gerar_pdf',side_effect=RuntimeError('Falha local simulada')):
                r=server.app.test_client().get(f'/download/{RID}/pdf?completo=1')
                self.assertEqual(r.status_code,500);self.assertEqual(r.get_json()['erro'],'Falha local simulada')
            self.assertEqual(before,(root/f'comparacao_{RID}.json').read_bytes())


class BrowserUI17Tests(unittest.TestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright
        from test_smart import navegador
        from web import server
        from contextlib import ExitStack
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()));self.stack.enter_context(patch.object(server,'PASTA',self.root));self.stack.enter_context(patch.object(server,'HISTORY_PATH',self.root/'historico.json'))
        self.stack.enter_context(patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True));server.STATE.update(status='pronto',ultimo_id=None)
        self.client=server.app.test_client();pw=self.stack.enter_context(sync_playwright());self.browser=navegador(pw);self.addCleanup(self.browser.close);self.p=self.browser.new_page();self.requests=[];self.fail_download=False
        def responder(route):
            req=route.request;path=req.url.split('http://ambidiff.test',1)[-1];self.requests.append((req.method,path,req.post_data))
            if path.startswith('/api/status'):route.fulfill(content_type='application/json',body='{"status":"pronto","progresso":0}');return
            if self.fail_download and path.startswith('/download/'):
                route.fulfill(status=500,content_type='application/json',body='{"erro":"Falha de geração simulada"}');return
            r=self.client.open(path,method=req.method,data=req.post_data,content_type='application/json')
            route.fulfill(status=r.status_code,content_type=r.content_type,headers={'Content-Disposition':r.headers.get('Content-Disposition','')},body=r.data);r.close()
        self.p.route('http://ambidiff.test/**',responder);self.p.goto('http://ambidiff.test/',wait_until='networkidle')
    def abrir(self,n=3):
        report_fixture(self.root,n);self.p.evaluate('(id)=>openReport(id)',RID)

    def test_sem_relatorio_exportacao_orientada_e_defaults_avancados(self):
        self.assertTrue(self.p.locator('[data-export="csv"]').is_disabled())
        self.assertIn('Abra uma comparação',self.p.locator('#export-feedback').inner_text())
        self.assertEqual(self.p.locator('#orcamento-minutos,#estrategia,#varredura-inteligente').count(),0)
        self.assertFalse(self.p.locator('.advanced-options').evaluate('(e)=>e.open'))
        self.abrir();self.p.locator('[data-export="csv"]').click()
        self.assertIn('Selecione ao menos',self.p.locator('#export-feedback').inner_text())
        self.assertFalse(any(path.startswith('/download/') for _,path,_ in self.requests))

    def test_lote_filtradas_inclui_nao_renderizadas_persiste_e_individual(self):
        self.abrir(105);self.assertEqual(self.p.locator('.result-card').count(),40)
        self.p.locator('#filter-side').select_option('PRD');self.p.locator('#select-filtered-divs').click()
        self.p.wait_for_function("document.querySelector('#selected-count').textContent==='53 IDs selecionados'")
        puts=[x for x in self.requests if x[0]=='PUT'];self.assertEqual(len(puts),1);self.assertLess(len(puts[0][2]),1000)
        self.p.reload(wait_until='networkidle');self.p.evaluate('(id)=>openReport(id)',RID)
        self.assertEqual(self.p.locator('#selected-count').inner_text(),'53 IDs selecionados')
        self.p.locator('#select-all-divs').click();self.p.wait_for_function("document.querySelector('#selected-count').textContent==='105 IDs selecionados'")
        self.p.locator('#clear-selected-divs').click();self.p.wait_for_function("document.querySelector('#selected-count').textContent==='0 IDs selecionados'")
        self.p.locator('.div-export-selection').first.check();self.p.wait_for_function("document.querySelector('#selected-count').textContent==='1 IDs selecionados'")
        self.assertFalse((self.root/f'revisoes_{RID}.json').exists())

    def test_formatos_teclado_cancelamento_e_falha_visivel(self):
        self.abrir(2);self.p.evaluate('window.showSaveFilePicker=undefined');self.p.locator('#export-scope').select_option('completo')
        for ext in ('csv','html','pdf','json'):
            self.p.locator('#export-format').select_option(ext);button=self.p.locator('#download-report');button.focus()
            with self.p.expect_download() as info:button.press('Enter')
            self.assertTrue(info.value.suggested_filename.endswith('.'+ext))
            self.assertIn('enviado ao navegador',self.p.locator('#export-feedback').inner_text())
        # O recurso de escolha de arquivos pode existir e falhar; a exportação
        # não deve depender dele para salvar relatórios.
        self.p.evaluate('()=>{window.pickerInvocado=false;window.showSaveFilePicker=async()=>{window.pickerInvocado=true;throw new DOMException("Sem permissão","NotAllowedError")};}')
        self.p.locator('#export-format').select_option('csv')
        with self.p.expect_download() as info:self.p.locator('#download-report').click()
        self.assertTrue(info.value.suggested_filename.endswith('.csv'))
        self.assertFalse(self.p.evaluate('window.pickerInvocado'))
        self.fail_download=True
        self.p.locator('#export-format').select_option('pdf');self.p.locator('#download-report').click();self.p.wait_for_function("document.querySelector('#export-feedback').textContent.includes('Falha de geração simulada')")
        self.assertTrue(self.p.locator('#export-feedback').is_visible());self.assertFalse(self.p.locator('[data-export="pdf"]').is_disabled())

    def test_grupo_parcial_e_falha_no_lote_nao_desincroniza_interface(self):
        from test_update12 import ExportTests
        from ambidiff.storage import selecionar
        ExportTests().preparar(self.root);selecionar(self.root,RID,'DIV-0002',True)
        self.p.evaluate('(id)=>openReport(id)',RID)
        group=self.p.locator('.div-export-selection[aria-label="Selecionar DIV-0001 para exportação"]')
        self.assertTrue(group.evaluate('(e)=>e.indeterminate'))
        with patch('ambidiff.storage.atomic_json',side_effect=OSError('Disco cheio')):
            self.p.locator('#select-all-divs').click()
            self.p.wait_for_function("document.querySelector('#selection-feedback').textContent.includes('Seleção não salva')")
        self.assertEqual(self.p.locator('#selected-count').inner_text(),'1 IDs selecionados')
        self.assertTrue(group.evaluate('(e)=>e.indeterminate'));self.assertFalse((self.root/f'revisoes_{RID}.json').exists())
