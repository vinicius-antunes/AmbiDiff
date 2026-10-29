"""Estabilidade e interface: fixtures locais, sem portais institucionais."""
import copy
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from ambidiff.core import Item,Pagina
from ambidiff import checkpoints as cp
from test_intermat import A,B,RID

CLOSED='Target page, context or browser has been closed'

class Page:
    def __init__(self,ctx):self.ctx=ctx;self.url='about:blank';self.closed=False
    def is_closed(self):return self.closed
    def close(self):self.closed=True
class Context:
    def __init__(self,browser):self.browser=browser;self.closed=False;self.handlers={};self.pages=[];self.cookies={}
    def on(self,name,handler):self.handlers[name]=handler
    def route(self,*_):pass
    def new_page(self):
        if self.closed or not self.browser.connected:raise RuntimeError(CLOSED)
        p=Page(self);self.pages.append(p);return p
    def close(self):
        self.closed=True
        for p in self.pages:p.close()
        if 'close' in self.handlers:self.handlers['close'](self)
class Browser:
    def __init__(self):self.connected=True;self.contexts=[]
    def is_connected(self):return self.connected
    def new_context(self,**kw):
        if not self.connected:raise RuntimeError(CLOSED)
        assert not kw.get('ignore_https_errors');c=Context(self);self.contexts.append(c);return c
    def close(self):
        self.connected=False
        for c in self.contexts:c.close()
class PW:
    def __init__(self):self.launches=[];self.browsers=[];self.chromium=NS(launch=self.launch)
    def launch(self,**kw):self.launches.append(kw);b=Browser();self.browsers.append(b);return b
    def __enter__(self):return self
    def __exit__(self,*_):pass


def run(n=9,nav=None,extra=None,stop=None,retomada=None,checkpoints=None,comparar=None,nomes=('PRD','DES'),visual=None):
    from ambidiff.paired import executar_pareado
    pw=PW();abertas=[];stop=stop or threading.Event()
    def abrir(p,u):
        if p.is_closed() or not p.ctx.browser.connected:raise RuntimeError(CLOSED)
        abertas.append(u)
        if nav:nav(p,u)
        p.url=u;return NS(url=u,status=200,headers={'content-type':'text/html'})
    def extrair(p,u,trilha,log,**kw):
        base=A if u.startswith(A) else B
        itens=[Item('Opção','Serviço '+str(i),'Serviço '+str(i),local='Menu',destino=base+str(i)) for i in range(1,n)] if u==base else []
        if u==A:itens.append(Item('Opção','ÁUDIOS','ÁUDIOS',local='Menu',destino=A+'audio.pdf'))
        pagina=Pagina(u,'','Portal sintético',itens,trilha,coleta={'estavel':True,'rolagem_limitada':False})
        if extra:extra(pagina)
        return pagina
    with ExitStack() as stack:
        stack.enter_context(patch('playwright.sync_api.sync_playwright',return_value=pw))
        stack.enter_context(patch('ambidiff.paired._abrir',side_effect=abrir))
        stack.enter_context(patch('ambidiff.paired._extrair_page',side_effect=extrair))
        stack.enter_context(patch('ambidiff.paired.comparar_visuais',side_effect=visual) if visual else patch('ambidiff.paired.comparar_visuais',return_value=([],[])))
        stack.enter_context(patch('ambidiff.adaptive.decidir_releitura',return_value=[]))
        stack.enter_context(patch('ambidiff.paired.time.sleep'))
        if comparar:stack.enter_context(patch('ambidiff.paired.comparacao',side_effect=comparar))
        r=executar_pareado(A,B,*nomes,stop,lambda _:None,lambda _:None,retomada=retomada,checkpoint=(lambda d:checkpoints.append(copy.deepcopy(d))) if checkpoints is not None else None)
    return r,pw,abertas


class Recovery19Tests(unittest.TestCase):
    def test_oculto_sem_variavel_e_limpeza_so_apos_analise_contextos_independentes(self):
        def nav(p,u):
            self.assertTrue(p.ctx.browser.connected);self.assertFalse(p.ctx.closed)
            if u==A:p.ctx.cookies['ambiente']='A'
            if u==B:self.assertNotIn('ambiente',p.ctx.cookies)
        with patch.dict(os.environ,{'AMBIDIFF_HEADLESS':'0'}):r,pw,_=run(n=3,nav=nav)
        self.assertTrue(all(x['headless'] for x in pw.launches));self.assertEqual(len(pw.browsers),1)
        self.assertFalse(pw.browsers[0].connected);self.assertTrue(all(c.closed for c in pw.browsers[0].contexts))
        self.assertEqual(r['andamento']['pares_concluidos'],3)

    def test_capturas_com_browser_fechado_nao_repetem_targetclosed(self):
        from unittest.mock import MagicMock
        from ambidiff.paired import _salvar_evidencias
        browser=MagicMock();browser.is_connected.return_value=False
        contextos=[MagicMock(),MagicMock()]
        paginas=[MagicMock(),MagicMock()]
        for ctx,page in zip(contextos,paginas):ctx.new_page.return_value=page
        browser.new_context.side_effect=contextos
        paginas[0].goto.side_effect=RuntimeError(CLOSED)
        registros=[{'id':f'DIV-{n:04d}','presente_em':'PRD','nao_identificado_em':'HOMOL',
            'url_presente':A,'url_comparada':B} for n in range(1,20)]
        logs=[];diagnosticos=[]
        with tempfile.TemporaryDirectory() as td:
            _salvar_evidencias(browser,registros,td,threading.Event(),logs.append,
                'PRD','HOMOL',diagnosticos=diagnosticos)
        self.assertEqual(len([s for s in logs if 'TargetClosedError' in s or 'RuntimeError' in s]),1)
        self.assertIn('capturas restantes ignoradas',logs[-1])
        self.assertEqual(len(diagnosticos),1)
        self.assertTrue(all(ctx.close.called for ctx in contextos))
        self.assertFalse(any(r.get('evidencias') for r in registros))

    def test_capturas_contexto_fechado_na_inicializacao_nao_derrubam_relatorio(self):
        from unittest.mock import MagicMock
        from ambidiff.paired import _salvar_evidencias
        browser=MagicMock();browser.new_context.side_effect=RuntimeError(CLOSED)
        logs=[];falhas=[]
        with tempfile.TemporaryDirectory() as td:
            _salvar_evidencias(browser,[],td,threading.Event(),logs.append,
                'PRD','HOMOL',diagnosticos=falhas)
        self.assertEqual(len(falhas),1)
        self.assertIn('relatório preservado',logs[-1])

    def test_consultar_checkpoints_nao_compete_com_varredura_ativa(self):
        from web import server
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            server.STATE['status']='executando'
            # Um checkpoint grande não deve sequer ser aberto enquanto executando.
            arquivo=Path(td)/f'checkpoint_{RID}.json';arquivo.write_text('{"invalido":true}',encoding='utf-8')
            with patch('ambidiff.checkpoints.validar',side_effect=AssertionError('não deveria validar')):
                response=server.app.test_client().get('/api/checkpoints')
            self.assertEqual(response.status_code,409)
            self.assertIn('andamento',response.get_json()['erro'])
            self.assertTrue(arquivo.exists())

    def test_navegador_encerrado_recupera_e_continua_nove_pares(self):
        vezes=0
        def nav(p,u):
            nonlocal vezes
            if u==A+'1' and vezes==0:vezes+=1;p.ctx.browser.close();raise RuntimeError(CLOSED)
        snaps=[];r,pw,abertas=run(nav=nav,checkpoints=snaps)
        self.assertEqual(r['andamento']['pares_comparados'],9);self.assertEqual(r['andamento']['pares_pendentes'],0)
        self.assertEqual(len(pw.browsers),2);self.assertEqual(abertas.count(A),1)
        self.assertEqual(r['fila_execucao']['estado'],'concluida_com_falhas')
        self.assertTrue(r['falhas'][0]['ciclo_navegador']['navegador_conectado'] is False)
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))
        cp.validar(snaps[-1]['retomada'])

    def test_pagina_fechada_recria_sem_novo_browser(self):
        vezes=0
        def nav(p,u):
            nonlocal vezes
            if u==A+'1' and vezes==0:vezes+=1;p.close();raise RuntimeError(CLOSED)
        r,pw,_=run(n=3,nav=nav)
        self.assertEqual(len(pw.browsers),1);self.assertEqual(r['andamento']['pares_comparados'],3)
        self.assertTrue(r['falhas'][0]['ciclo_navegador']['paginas_fechadas'][0])

    def test_contexto_fechado_recria_e_preserva_contexto_oposto(self):
        vezes=0;ctx_b=[]
        def nav(p,u):
            nonlocal vezes
            if u==B:ctx_b.append(p.ctx)
            if u==A+'1' and vezes==0:vezes+=1;p.ctx.close();raise RuntimeError(CLOSED)
        r,pw,_=run(n=3,nav=nav)
        self.assertEqual(len(pw.browsers),1);self.assertEqual(r['andamento']['pares_comparados'],3)
        self.assertFalse(ctx_b[0] is pw.browsers[0].contexts[-1])
        self.assertTrue(r['falhas'][0]['ciclo_navegador']['contextos_fechados'][0])

    def test_recurso_falha_duas_vezes_estado_falho_e_demais_continuam(self):
        def nav(p,u):
            if u==A+'1':p.close();raise RuntimeError(CLOSED)
        r,_,abertas=run(n=4,nav=nav)
        self.assertEqual(abertas.count(A+'1'),2);self.assertEqual(r['andamento']['pares_comparados'],3)
        self.assertEqual(r['andamento']['pares_com_falha'],1);self.assertEqual(r['andamento']['pares_concluidos'],4)
        self.assertEqual(r['fila_execucao']['estado'],'concluida_com_falhas')

    def test_falha_fatal_salva_todos_concluidos_e_erro_sem_duplicar(self):
        snaps=[]
        def nav(p,u):
            if u not in (A,B):p.ctx.browser.close();raise RuntimeError(CLOSED)
        with self.assertRaisesRegex(RuntimeError,'recuperações'):run(nav=nav,checkpoints=snaps)
        estado=cp.validar(snaps[-1]['retomada']);self.assertTrue(estado['fila'])
        self.assertTrue(estado['brutos']);self.assertEqual(len(estado['paginas_a']),1)
        self.assertTrue(any(f.get('fatal') for f in estado['falhas']))
        r,_,abertas=run(retomada=snaps[-1]['retomada'])
        self.assertNotIn(A,abertas);self.assertEqual(r['andamento']['pares_pendentes'],0)
        from ambidiff.diagnostics import montar_diagnostico
        diag=montar_diagnostico(r);self.assertEqual(diag['contadores_diagnostico']['automacao'],len(estado['falhas']))

    def test_falha_generica_transacao_preserva_bruto_anterior_e_retomada_sem_duplicar(self):
        from ambidiff.core import comparacao
        def comparar(*args,**kw):
            if args[2].url==A+'1':raise RuntimeError('Falha sintética durante comparação')
            return comparacao(*args,**kw)
        snaps=[]
        with self.assertRaisesRegex(RuntimeError,'sintética'):run(n=3,comparar=comparar,checkpoints=snaps)
        e=cp.validar(snaps[-1]['retomada']);self.assertEqual(len(e['paginas_a']),1);self.assertEqual(len(e['brutos']),1)
        r,_,_=run(n=3,retomada=snaps[-1]['retomada']);self.assertEqual(r['andamento']['pares_comparados'],3)
        self.assertEqual(sum(d['elemento']=='ÁUDIOS' for d in r['divergencias']),1)


class Navigation19Tests(unittest.TestCase):
    def navegar(self,func,page=None):
        from ambidiff.navigation import abrir
        from ambidiff.smart import Metricas
        p=page or NS(url='about:blank',is_closed=lambda:False);m=Metricas();eventos=[]
        r=abrir(p,A,A,threading.Event(),m,eventos,'PRD',func)
        return r,m,eventos
    def test_aborto_recuperado_uma_tentativa_e_sem_div(self):
        n=0
        def func(p,u):
            nonlocal n;n+=1
            if n==1:raise RuntimeError('net::ERR_ABORTED')
            return NS(status=200,url=u)
        r,m,ev=self.navegar(func);self.assertEqual(n,2);self.assertTrue(ev[0]['recuperada'])
        self.assertEqual(m.contagens['tentativas_navegacao_adicionais'],1)
    def test_aborto_persistente_tem_limite_e_certificado_nao_e_ignorado(self):
        for erro,limite in [('net::ERR_ABORTED',2),('net::ERR_CERT_COMMON_NAME_INVALID',1)]:
            f=unittest.mock.Mock(side_effect=RuntimeError(erro))
            with self.assertRaisesRegex(RuntimeError,erro):self.navegar(f)
            self.assertEqual(f.call_count,limite)
        from ambidiff.diagnostics import classificar_erro
        self.assertEqual(classificar_erro('net::ERR_ABORTED')['tipo_erro'],'NAVEGACAO_INTERROMPIDA')
        cert=classificar_erro('net::ERR_CERT_COMMON_NAME_INVALID');self.assertEqual(cert['tipo_erro'],'CERTIFICADO_TLS');self.assertIn('endereço',cert['orientacao'])
    def test_aborto_com_destino_observado_nao_inventa_equivalencia(self):
        p=NS(url=A+'anterior',is_closed=lambda:False,wait_for_load_state=lambda *a,**kw:None,evaluate=lambda js:True)
        def f(p,u):p.url=A+'login';raise RuntimeError('net::ERR_ABORTED')
        r,m,ev=self.navegar(f,p);self.assertIsNone(r);self.assertEqual(p.url,A+'login');self.assertTrue(ev[0]['recuperada'])


class Progress19Tests(unittest.TestCase):
    def test_um_de_nove_nunca_aparece_99_na_api_mesmo_callback_final(self):
        from web import server
        with patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            server.STATE.update(status='erro',progresso=99,inicio_monotonic=None,andamento={'pares_descobertos':9,'pares_comparados':1,'pares_visitados':2,'pares_pendentes':8,'pares_concluidos':1,'etapa':'falha'})
            p=server.estado_publico();self.assertEqual(p['progresso'],11);self.assertEqual(p['andamento']['pares_nao_analisados'],8)
    def test_final_com_falhas_distinto_de_parcial_e_da_cobertura(self):
        from ambidiff.execution import resumir
        r={'andamento':{'pares_descobertos':9,'pares_concluidos':9,'pares_comparados':8,'pares_com_falha':1,'pares_pendentes':0},'falhas':[{'erro':'HTTP 404'}]}
        self.assertEqual(resumir(r)['estado'],'concluida_com_falhas')
        r['andamento'].update(pares_concluidos=1,pares_pendentes=8)
        self.assertEqual(resumir(r)['estado'],'parcial')
    def test_fatal_na_lista_e_no_campo_conta_uma_vez(self):
        from ambidiff.diagnostics import registrar_excecao,montar_diagnostico
        r={'andamento':{},'erro_execucao':'Falha sintética'};ex=RuntimeError('Falha sintética')
        registrar_excecao(r,ex,fatal=True);registrar_excecao(r,ex,fatal=True)
        d=montar_diagnostico(r);self.assertEqual(d['contadores_diagnostico']['automacao'],1)
        d=montar_diagnostico({'erro_execucao':'Falha sintética'});self.assertEqual(d['contadores_diagnostico']['automacao'],1)

class Menus19Tests(unittest.TestCase):
    def test_menu_oculto_haspopup_preserva_audios_sem_acionar_excluir(self):
        from playwright.sync_api import sync_playwright
        from test_smart import navegador
        from ambidiff.paired import _extrair_page
        from ambidiff.core import comparacao
        with sync_playwright() as pw:
            b=navegador(pw);pages=[b.new_page(),b.new_page()]
            try:
                dados=[]
                for i,p in enumerate(pages):
                    p.set_content('<nav><button aria-haspopup="menu" aria-expanded="false" onclick="document.querySelector(\'ul\').hidden=false;this.setAttribute(\'aria-expanded\',\'true\')">Menu</button><ul hidden>'+
                        ('<li><a href="https://a.test/audio.pdf">ÁUDIOS</a></li>' if i==0 else '<li><a href="https://b.test/servico">Serviço</a></li>')+
                        '</ul><button aria-expanded="false" aria-controls="remover" aria-label="Excluir" onclick="window.escrita=true">✕</button></nav>')
                    dados.append(_extrair_page(p,A if i==0 else B,['Início'],lambda _:None))
                    self.assertFalse(p.evaluate('!!window.escrita'))
                rows=comparacao(dados[0].itens,dados[1].itens,*dados,'PRD','DES')
                self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in rows))
            finally:b.close()

    def test_componente_com_erro_nao_impede_menu_seguinte(self):
        from playwright.sync_api import sync_playwright
        from test_smart import navegador
        from ambidiff.paired import _extrair_page
        with sync_playwright() as pw:
            b=navegador(pw);p=b.new_page()
            try:
                p.set_content('<nav><button disabled aria-expanded="false" aria-controls="um">Indisponível</button><button aria-expanded="false" aria-controls="dois" onclick="document.querySelector(\'ul\').hidden=false">Outros serviços</button><ul hidden id="dois"><a href="https://a.test/audio.pdf">ÁUDIOS</a></ul></nav>')
                r=_extrair_page(p,A,['Início'],lambda _:None)
                self.assertTrue(any(i.nome=='ÁUDIOS' for i in r.itens));self.assertTrue(r.coleta['avisos_componentes'])
            finally:b.close()

import test_update17 as fixtures17

class Interface19Tests(unittest.TestCase):
    setUp=fixtures17.BrowserUI17Tests.setUp
    abrir=fixtures17.BrowserUI17Tests.abrir
    def test_ambiente_b_homol_e_configuracoes_internas(self):
        self.assertEqual(self.p.locator('#nome-b option').evaluate_all('els=>els.map(e=>e.value)'),['DES','LAB','HOMOL'])
        self.assertEqual(self.p.locator('#nome-b').input_value(),'DES')
        self.assertEqual(self.p.locator('#nome-a option[value="PRD"]').count(),1)
        self.assertEqual(self.p.locator('#estrategia,#orcamento-minutos,#varredura-inteligente,#headless').count(),0)
        self.assertFalse(self.p.locator('#auditar-externos').is_checked());self.assertFalse(self.p.locator('#verificar-cliques').is_checked())
        self.assertFalse(self.p.locator('.execution-diagnostics').evaluate('e=>e.open'))

    def test_resumo_progresso_um_em_nove_e_erro_em_um_unico_aviso(self):
        self.p.locator('[data-section="comparar"]').click()
        s={'status':'erro','progresso':99,'ultimo_id':RID,'andamento':{'pares_descobertos':9,'pares_concluidos':1,'pares_comparados':1,'pares_pendentes':8,'pares_com_falha':0,'etapa':'falha'},'falha_principal':{'ambiente':'DES','url':B,'erro':'Navegador encerrado'},'tempo_decorrido_segundos':12}
        self.p.evaluate('(s)=>{updateProgressInfo(s);executionSummary(s)}',s)
        self.assertTrue(self.p.locator('#progress-percent').inner_text().startswith('11%'))
        self.assertIn('8',self.p.locator('#execution-summary').inner_text())
        self.assertIn('resultados parciais preservados',self.p.locator('#failure-title').inner_text())
        self.assertIn('DES',self.p.locator('#failure-context').inner_text())
        self.assertEqual(self.p.locator('#failure-diagnostics').count(),1)
        self.assertEqual(self.p.locator('#form-error').inner_text(),'')

    def test_estado_vazio_parcial_esconde_filtros_e_mantem_exportacao_completa(self):
        from ambidiff.storage import atomic_json
        atomic_json(self.root/f'comparacao_{RID}.json',{'id':RID,'versao':'1.5','divergencias':[],'situacao_analise':'parcial','paginas':{'PRD':1,'HOMOL':1},'andamento':{'pares_descobertos':9,'pares_comparados':1,'pares_pendentes':8}})
        self.p.evaluate('(id)=>openReport(id)',RID)
        self.assertFalse(self.p.locator('#difference-controls').is_visible())
        self.assertIn('pares efetivamente comparados',self.p.locator('#result-list').inner_text())
        self.assertIn('páginas pendentes',self.p.locator('#result-list').inner_text())
        self.assertEqual(self.p.locator('#export-scope').input_value(),'completo')
        self.assertFalse(self.p.locator('#download-report').is_disabled())
        self.assertFalse(self.p.locator('.export-diagnostics').evaluate('e=>e.open'))
        self.assertFalse(self.p.locator('#data-variations').locator('..').is_visible())

    def test_exportacao_compacta_json_diferente_diagnostico_todos_formatos(self):
        self.abrir(2)
        self.assertEqual(self.p.locator('.export-actions button').count(),1)
        self.assertEqual(self.p.locator('#export-format option').count(),4)
        self.p.locator('#export-scope').select_option('completo')
        self.assertEqual(self.p.locator('#export-format').input_value(),'html')
        self.p.evaluate('window.showSaveFilePicker=undefined')
        for fmt in ('csv','html','pdf','json'):
            self.p.locator('#export-format').select_option(fmt)
            with self.p.expect_download() as info:self.p.locator('#download-report').click()
            self.assertTrue(info.value.suggested_filename.endswith('.'+fmt))
        self.p.locator('.export-diagnostics summary').click()
        self.assertTrue(self.p.locator('[data-export="diagnostico-json"]').is_visible())
        self.assertTrue(self.p.locator('[data-export="diagnostico-txt"]').is_visible())
        self.assertIn('separadamente',self.p.locator('#export-description').inner_text())


    def test_json_completo_e_selecionadas_nao_sao_vazios_e_preservam_origem(self):
        self.abrir(3)
        original=(self.root/f'comparacao_{RID}.json').read_bytes()
        self.p.locator('#export-scope').select_option('completo')
        self.p.locator('#export-format').select_option('json')
        with self.p.expect_download() as info:
            self.p.locator('#download-report').click()
        arquivo=self.root/'export-completo.json'
        info.value.save_as(str(arquivo))
        self.assertGreater(arquivo.stat().st_size,50)
        completo=json.loads(arquivo.read_text(encoding='utf-8'))
        self.assertEqual({d['id'] for d in completo['divergencias']},
                         {'DIV-0001','DIV-0002','DIV-0003'})
        self.assertIn('completo=1',[p for _,p,_ in self.requests if p.startswith('/download/')][-1])

        self.p.locator('.div-export-selection').first.check()
        self.p.wait_for_function("document.querySelector('#selected-count').textContent==='1 IDs selecionados'")
        self.p.locator('#export-scope').select_option('selecionadas')
        self.p.locator('#export-format').select_option('json')
        with self.p.expect_download() as info:
            self.p.locator('#download-report').click()
        arquivo=self.root/'export-selecionado.json'
        info.value.save_as(str(arquivo))
        selecionado=json.loads(arquivo.read_text(encoding='utf-8'))
        self.assertEqual([d['id'] for d in selecionado['divergencias']],['DIV-0001'])
        self.assertEqual(selecionado['ids_selecionados'],['DIV-0001'])
        self.assertIn('selecionadas=1',[p for _,p,_ in self.requests if p.startswith('/download/')][-1])
        self.assertEqual((self.root/f'comparacao_{RID}.json').read_bytes(),original)

    def test_erro_exportacao_aparece_no_painel_sem_download(self):
        self.abrir(1)
        self.p.route('**/download/**',
                     lambda route:route.fulfill(status=500,content_type='application/json',
                       body='{"erro":"Exportação vazia: arquivo original preservado."}'))
        self.p.locator('#export-scope').select_option('completo')
        self.p.locator('#export-format').select_option('json')
        self.p.locator('#download-report').click()
        self.p.wait_for_function("document.querySelector('#export-feedback').textContent.includes('Exportação vazia')")
        self.assertFalse(self.p.locator('#download-report').is_disabled())


    def test_resposta_grande_streaming_liberada_apos_download(self):
        from web import server
        self.abrir(2)
        saida={}
        bloco=b'Exemplo;DIV-0001\n'+b'x'*1024*1024
        def exportar_grande(dados,pasta,run_id,**_kw):
            arquivo=pasta/f'comparacao_{run_id}.csv'
            with arquivo.open('wb') as out:
                for _ in range(6):out.write(bloco)
            saida['path']=arquivo
            return {'csv':str(arquivo)}
        with patch.object(server,'exportar',side_effect=exportar_grande):
            response=self.client.get(f'/download/{RID}/csv?completo=1',buffered=False)
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.is_streamed)
            self.assertEqual(int(response.headers['Content-Length']),len(bloco)*6)
            pedacos=iter(response.response)
            self.assertLessEqual(len(next(pedacos)),1024*1024)
            response.close()
        self.assertFalse(saida['path'].exists())
        self.assertTrue((self.root/f'comparacao_{RID}.json').is_file())

    def test_formatos_independentes_preservam_json_completo_sem_inflar_html(self):
        from web import server
        from ambidiff.storage import atomic_json
        self.abrir(2)
        arquivo=self.root/f'comparacao_{RID}.json'
        payload=json.loads(arquivo.read_text(encoding='utf-8'))
        marcador='DETALHE_COMPLETO_EXPORTACAO_'+'X'*1_000_000
        payload['metricas']={'releituras':[{'log':marcador}]}
        atomic_json(arquivo,payload)
        original=arquivo.read_bytes()
        formatos=[]
        original_exportar=server.exportar
        def acompanhar(dados,pasta,run_id,**kw):
            formatos.append(tuple(kw.get('formatos',())))
            return original_exportar(dados,pasta,run_id,**kw)
        with patch.object(server,'exportar',side_effect=acompanhar):
            for fmt in ('csv','html','json'):
                resposta=self.client.get(f'/download/{RID}/{fmt}?completo=1')
                self.assertEqual(resposta.status_code,200,fmt)
                conteudo=resposta.get_data()
                self.assertGreater(len(conteudo),50,fmt)
                if fmt=='json':
                    completo=json.loads(conteudo)
                    self.assertEqual(len(completo['divergencias']),2)
                    self.assertIn(marcador,completo['metricas']['releituras'][0]['log'])
                elif fmt=='html':
                    self.assertIn(b'DIV-0001',conteudo)
                    self.assertNotIn(marcador.encode(),conteudo)
                else:self.assertIn(b'DIV-0001',conteudo)
                resposta.close()
            with patch('ambidiff.exports.gerar_pdf',side_effect=lambda _html,target:target.write_bytes(b'%PDF-1.7\n'+b'A'*100)):
                resposta=self.client.get(f'/download/{RID}/pdf?completo=1')
                self.assertEqual(resposta.status_code,200)
                self.assertTrue(resposta.get_data().startswith(b'%PDF-1.7'))
                resposta.close()
        self.assertEqual(formatos,[('csv',),('html',),('json',),('html',)])
        self.assertEqual(arquivo.read_bytes(),original)

    def test_servidor_nao_entrega_json_sem_divs_esperadas(self):
        from web import server
        self.abrir(2)
        original=(self.root/f'comparacao_{RID}.json').read_bytes()
        def exportar_truncado(dados, pasta, run_id, **_kw):
            p=pasta/f'comparacao_{run_id}.json'
            p.write_text('{"divergencias":[]}',encoding='utf-8')
            return {'json':str(p)}
        with patch.object(server,'exportar',side_effect=exportar_truncado):
            response=self.client.get(f'/download/{RID}/json?completo=1')
            self.assertEqual(response.status_code,500)
            self.assertIn('sem divergências esperadas',response.get_json()['erro'])
            response.close()
        self.assertEqual((self.root/f'comparacao_{RID}.json').read_bytes(),original)


class Homol19Tests(unittest.TestCase):
    def test_homol_api_nova_e_prd_b_legado_continua_consultavel(self):
        from web import server
        from ambidiff.storage import atomic_json
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            client=server.app.test_client();server.STATE['status']='pronto'
            with patch('web.server.threading.Thread') as worker:
                self.assertEqual(client.post('/api/comparar',json={'url_a':A,'url_b':B,'nome_b':'HOMOL'}).status_code,200)
                params=worker.call_args.kwargs['args'][0];self.assertEqual(params['nome_b'],'HOMOL');self.assertEqual(params['url_b'],B)
            server.STATE['status']='pronto'
            with patch('web.server.threading.Thread') as worker:
                self.assertEqual(client.post('/api/comparar',json={'url_a':A,'url_b':B,'nome_b':'PRD'}).status_code,400);worker.assert_not_called()
            antigo={'id':RID,'versao':'1.5','ambientes':{'LAB':A,'PRD':B},'divergencias':[],'paginas':{'LAB':1,'PRD':1}}
            atomic_json(Path(td)/f'comparacao_{RID}.json',antigo)
            resp=client.get('/api/relatorio/'+RID);self.assertEqual(resp.status_code,200);self.assertEqual(resp.get_json()['ambientes'],antigo['ambientes'])

    def test_homol_relatorio_historico_diagnostico_checkpoint(self):
        from web import server
        snaps=[];r,_,_=run(n=3,nomes=('PRD','HOMOL'),checkpoints=snaps)
        self.assertEqual(cp.validar(snaps[-1]['retomada'])['configuracao']['nome_b'],'HOMOL')
        self.assertEqual(r['divergencias'][0]['nao_identificado_em'],'HOMOL')
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.object(server,'HISTORY_PATH',Path(td)/'historico.json'),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True),patch.object(server,'executar',return_value=r),patch.object(server.PARAR,'is_set',return_value=False):
            server.STATE.update(status='executando',execucao_id=RID,andamento={})
            server.worker({'url_a':A,'url_b':B,'nome_a':'PRD','nome_b':'HOMOL','site_nome':'Portal sintético','auditar_externos':False},RID)
            self.assertEqual(server.STATE['status'],'concluido')
            for nome in (f'comparacao_{RID}.json',f'diagnostico_{RID}.json','historico.json'):
                data=json.loads((Path(td)/nome).read_text());data=data[0] if isinstance(data,list) else data
                self.assertIn('HOMOL',data['ambientes']);self.assertEqual(data['ambientes']['HOMOL'],B)

    def test_worker_fatal_sem_checkpoint_conta_uma_falha(self):
        from web import server
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True),patch.object(server,'executar',side_effect=RuntimeError('Falha inicial sintética')):
            server.worker({'url_a':A,'url_b':B,'nome_a':'PRD','nome_b':'DES','site_nome':'Teste','auditar_externos':False},RID)
            d=json.loads((Path(td)/f'diagnostico_{RID}.json').read_text())
            self.assertEqual(d['contadores_diagnostico']['automacao'],1);self.assertEqual(len(d['falhas']),1)

class IntegrationReal19Tests(unittest.TestCase):
    def test_chromium_real_pagina_fechada_recupera_contextos_e_compara_restante(self):
        from ambidiff import paired
        from fixtures_perf import portais_perf
        from ambidiff.core import _abrir
        closed=False;browsers=[]
        def abrir(p,u):
            nonlocal closed
            browser=p.context.browser;self.assertTrue(browser.is_connected());browsers.append(browser)
            if not closed and u.endswith('/pagina/1'):closed=True;p.close()
            return _abrir(p,u)
        def preparar(a,b):
            a.add_cookies([{'name':'somente_a','value':'fixture-local','url':bases[0]}])
            self.assertFalse(any(c['name']=='somente_a' for c in b.cookies()))
        with portais_perf(3) as (bases,reqs),patch('ambidiff.paired._abrir',side_effect=abrir):
            r=paired.executar_pareado(*bases,'PRD','DES',threading.Event(),lambda _:None,lambda _:None,varredura_inteligente=True,_preparar_contextos=preparar)
        self.assertEqual(r['andamento']['pares_comparados'],3)
        self.assertEqual(r['andamento']['pares_pendentes'],0)
        self.assertEqual(r['metricas']['contagens']['recuperacoes_navegador'],1)
        self.assertEqual(len({id(b) for b in browsers}),1)
        self.assertFalse(browsers[0].is_connected())

    def test_worker_um_de_nove_recupera_divs_e_registra_fatal_sem_alterar_checkpoint(self):
        from web import server
        snaps=[];stop=threading.Event()
        def extra(p):
            if p.url==A+'1':stop.set()
        run(extra=extra,stop=stop,checkpoints=snaps)
        snapshot=snaps[-1];self.assertEqual(snapshot['andamento']['pares_comparados'],1);self.assertEqual(snapshot['andamento']['pares_pendentes'],8)
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.object(server,'HISTORY_PATH',Path(td)/'historico.json'),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True),patch.object(server,'executar',side_effect=RuntimeError('Falha posterior sintética')):
            path=Path(td)/f'checkpoint_{RID}.json';cp.gravar(path,snapshot);original=path.read_bytes()
            server.STATE.update(status='executando',progresso=99,andamento=snapshot['andamento'])
            server.worker({'url_a':A,'url_b':B,'nome_a':'PRD','nome_b':'DES','site_nome':'Portal sintético','auditar_externos':False},RID)
            self.assertEqual(server.STATE['status'],'erro');self.assertEqual(server.STATE['progresso'],11)
            self.assertEqual(server.estado_publico()['progresso'],11);self.assertEqual(original,path.read_bytes())
            r=json.loads((Path(td)/f'comparacao_{RID}.json').read_text());d=json.loads((Path(td)/f'diagnostico_{RID}.json').read_text())
            self.assertEqual(r['fila_execucao']['estado'],'parcial');self.assertEqual(d['contadores_diagnostico']['automacao'],1)
            self.assertTrue(any(div['elemento']=='ÁUDIOS' for div in r['divergencias']))

    def test_erro_de_limpeza_nao_impede_liberar_demais_recursos(self):
        from ambidiff.browser import Navegador
        pw=PW();events=[];r=Navegador(pw,lambda _:None,diagnostico=events.append);r.iniciar();segundo=r.contextos[1]
        r.contextos[0].close=lambda:(_ for _ in ()).throw(RuntimeError('Encerrado'))
        r.fechar();self.assertTrue(segundo.closed);self.assertTrue(any(e['tipo']=='LIMPEZA_RECURSO' for e in events))

class ResourceCosts19Tests(unittest.TestCase):
    def test_checkpoint_sem_fila_nao_lanca_outro_chromium(self):
        snaps=[];run(n=1,checkpoints=snaps)
        r,pw,abertas=run(n=1,retomada=snaps[-1]['retomada'])
        self.assertEqual(pw.launches,[]);self.assertFalse(abertas)
        self.assertEqual(r['andamento']['pares_comparados'],1)
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))

class PartialRecords19Tests(unittest.TestCase):
    def test_provisorios_do_par_incompleto_sobrevivem_sem_duplicar_div_na_retomada(self):
        def extra(p):
            if p.url==A+'1':p.itens.append(Item('Texto','Regra importante apenas em um ambiente','Regra importante apenas em um ambiente',local='Institucional'))
        def visual(pa_page,pb_page,pa,pb,*args):
            if pa.url==A+'1':raise RuntimeError('Falha depois das divergências preliminares')
            return [],[]
        snaps=[]
        with self.assertRaisesRegex(RuntimeError,'preliminares'):run(n=3,extra=extra,visual=visual,checkpoints=snaps)
        e=cp.validar(snaps[-1]['retomada']);evento=next(x for x in e['eventos'] if x['tipo']=='TENTATIVA_DE_PAR_INCOMPLETA')
        self.assertTrue(evento['resultados_provisorios']['divergencias_preliminares'])
        self.assertEqual(len(e['brutos']),1)
        r,_,_=run(n=3,extra=extra,retomada=snaps[-1]['retomada'])
        self.assertEqual(sum('Regra importante' in d['elemento'] for d in r['divergencias']),1)
