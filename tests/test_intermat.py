"""Atualização extensiva: portais fabricados, sem acesso corporativo."""
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from ambidiff.core import Item,Pagina
from ambidiff.frontier import Fila
from ambidiff.checkpoints import empacotar,validar
from ambidiff.paired import executar_pareado,e_arquivo
from ambidiff.relevance import preparar
from ambidiff.smart import Metricas
from test_smart import navegador,Response,pdf

A='https://a.test/';B='https://b.test/'
RID='20261022_150000_abcdef'

def option(nome,destino='',tipo='Opção'):
    return Item(tipo,nome,nome,local='Institucional',destino=destino,funcao='link',natureza='estrutura')

class Page:
    url='about:blank'
class Context:
    def new_page(self):return Page()
    def route(self,*args):pass
    def on(self,*args):pass
    def close(self):pass
class Browser:
    def new_context(self,**kwargs):return Context()
    def close(self):pass
class PW:
    def __enter__(self):return NS(chromium=NS(launch=lambda **_:Browser()))
    def __exit__(self,*args):pass

def pipeline(n=4,stop=None,checkpoint=None,retomada=None,crash=None,clock=None,extracao_falha=None,ciclo=False,stop_na_extracao=None):
    stop=stop or threading.Event();opened=[]
    def abrir(page,url):
        idx=int(urlsplit(url).path.rsplit('/',1)[-1] or '0')
        if crash==idx:raise RuntimeError('Target page, context or browser has been closed')
        page.url=url;opened.append(url)
        return NS(status=200,url=url)
    def extrair(page,url,trilha,log,**kwargs):
        idx=int(urlsplit(url).path.rsplit('/',1)[-1] or '0')
        if stop_na_extracao==idx:stop.set()
        if extracao_falha==idx:raise RuntimeError('DOM indisponível')
        base=A if url.startswith(A) else B
        itens=[option('Próximo',base+str(idx+1))] if idx+1<n else []
        if ciclo and idx+1==n:itens.extend([option('Voltar',base),option('Voltar',base)])
        if idx==0 and base==A:itens.append(option('ÁUDIOS',A+'audio.pdf',tipo='Documento'))
        return Pagina(url,'','Portal',itens,trilha,coleta={'estavel':True,'rolagem_limitada':False})
    def log(msg):
        if checkpoint and msg.startswith('[PRD/DES]') and not retomada:stop.set()
    with ExitStack() as stack:
        stack.enter_context(patch('playwright.sync_api.sync_playwright',return_value=PW()))
        stack.enter_context(patch('ambidiff.paired._abrir',side_effect=abrir))
        stack.enter_context(patch('ambidiff.paired._extrair_page',side_effect=extrair))
        stack.enter_context(patch('ambidiff.paired.comparar_visuais',return_value=([],[])))
        stack.enter_context(patch('ambidiff.adaptive.decidir_releitura',return_value=[]))
        stack.enter_context(patch('ambidiff.paired.time.sleep'))
        if clock:stack.enter_context(patch('ambidiff.paired.time.monotonic',side_effect=clock))
        r=executar_pareado(A,B,'PRD','DES',stop,log,lambda _:None,checkpoint=checkpoint,retomada=retomada)
    return r,opened

class ExecutionTests(unittest.TestCase):
    def test_portal_2603_pares_ultrapassa_hora_sem_limite_global_e_sem_ciclos(self):
        tick=iter(range(0,100000000,4000))
        r,opened=pipeline(2603,clock=lambda:next(tick))
        self.assertEqual(r['paginas'],{'PRD':2603,'DES':2603})
        self.assertEqual(len(opened),5206);self.assertEqual(len(set(opened)),5206)
        self.assertEqual(r['andamento']['pares_pendentes'],0)
        self.assertFalse(any(m['motivo_parada'] for m in r['meta_varredura'].values()))
        self.assertTrue(any('ÁUDIOS' in x['elemento'] for x in r['divergencias']))
    def test_ciclo_voltar_e_repeticao_nao_ampliam_cobertura(self):
        r,opened=pipeline(5,ciclo=True)
        self.assertEqual(r['paginas']['PRD'],5);self.assertEqual(len(opened),10)
        self.assertEqual(r['andamento']['pares_pendentes'],0)
    def test_coleta_individual_sem_limite_global_mantem_timeout_por_operacao(self):
        from ambidiff.core import coletar_site
        page=NS(url=A,wait_for_load_state=lambda *a,**k:None,wait_for_timeout=lambda *a:None,
            evaluate=lambda *a:{'title':'Portal','itens':[{'tipo':'Texto','nome':'Portal','chave':'Portal'}],'links':[]})
        ctx=NS(new_page=lambda:page,close=lambda:None)
        with patch('ambidiff.core._abrir',return_value=NS(status=200)),patch('ambidiff.core.coletar_aba'),patch('ambidiff.core.time.monotonic',side_effect=[0,7201,7202,7203,7204,7205]):
            paginas,_,completo,_=coletar_site(NS(new_context=lambda **k:ctx),A,threading.Event(),lambda _:None,lambda _:None,'PRD')
        self.assertTrue(paginas);self.assertTrue(completo)
    def test_fila_prioriza_institucional_sem_excluir_editorial_ou_causar_inanicao(self):
        news=(A+'noticias/1',B+'noticias/1',['Início','Notícia'])
        f=Fila([news,(A+'conselho',B+'conselho',['Início','Conselho'])])
        self.assertIn('conselho',f.popleft()[0])
        for n in range(6):
            f.append((A+'estrutura'+str(n),B+'estrutura'+str(n),['Início','Estrutura']))
            f.popleft()
        f.append((A+'estrutura',B+'estrutura',['Início','Estrutura']))
        self.assertEqual(f.popleft(),news)
    def test_interrupcao_retomada_nao_repete_par_ou_ids_e_preserva_pendentes(self):
        snapshots=[]
        first,_=pipeline(checkpoint=lambda d:snapshots.append(copy.deepcopy(d)))
        cp=json.loads(json.dumps(snapshots[-1]['retomada']))
        self.assertEqual(first['paginas']['PRD'],1);self.assertEqual(len(validar(cp)['fila']),1)
        resumed,opened=pipeline(retomada=cp)
        self.assertEqual(resumed['paginas']['PRD'],4);self.assertEqual(len(opened),6)
        self.assertNotIn(A,opened);self.assertEqual(len(resumed['segmentos_coleta']),2)
        self.assertEqual(first['divergencias'][0]['id'],resumed['divergencias'][0]['id'])
        self.assertEqual(len(resumed['divergencias']),len(first['divergencias']))
    def test_crash_navegador_checkpoint_reenvia_par_nao_concluido(self):
        snaps=[]
        # Callback não solicita parada neste caso: retoma uma execução vazia válida.
        pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        base=snaps[0]['retomada']
        snaps=[]
        with self.assertRaisesRegex(RuntimeError,'closed'):
            pipeline(retomada=base,crash=1,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        # Checkpoint inicial preserva fila completa se o processo falhar antes do próximo intervalo.
        cp=snaps[-1]['retomada'];self.assertTrue(validar(cp)['fila'])
        r,_=pipeline(retomada=cp);self.assertEqual(r['paginas']['PRD'],4)
    def test_extracao_isolada_inconclusiva_nao_fabrica_ausencia(self):
        r,_=pipeline(extracao_falha=0)
        self.assertFalse(r['divergencias']);self.assertEqual(r['situacao_analise'],'inconclusivo')
        self.assertTrue(r['pendencias']);self.assertTrue(r['falhas'])
    def test_interromper_extracao_devolve_par_incompleto_a_fila(self):
        snaps=[];pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        base=snaps[0]['retomada'];snaps=[]
        r,_=pipeline(retomada=base,stop_na_extracao=1,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        self.assertEqual(r['paginas']['PRD'],1)
        estado=validar(snaps[-1]['retomada']);self.assertIn(A+'1',[p[0] for p in estado['fila']])
        self.assertNotIn([A+'1',B+'1'],estado['visitados'])
        resumed,opened=pipeline(retomada=snaps[-1]['retomada'])
        self.assertEqual(resumed['paginas']['PRD'],4);self.assertEqual(len(opened),6)
    def test_integridade_versao_e_fila_fora_escopo_recusadas(self):
        snaps=[];pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        cp=snaps[-1]['retomada'];bad=copy.deepcopy(cp);bad['estado']['fila'][0][0]='https://outro.test/'
        with self.assertRaisesRegex(ValueError,'integridade'):validar(bad)
        with self.assertRaisesRegex(ValueError,'escopo'):validar(empacotar(bad['estado']))
        bad=copy.deepcopy(cp);bad['versao_checkpoint']=999
        with self.assertRaisesRegex(ValueError,'incompatível'):validar(bad)
    def test_api_retoma_em_novo_id_preserva_revisao_e_nao_sobrescreve_original(self):
        from web import server
        snaps=[];pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True),patch.object(server.threading,'Thread') as thread:
            root=Path(td);root.joinpath(f'checkpoint_{RID}.json').write_text(json.dumps(snaps[-1]))
            root.joinpath(f'comparacao_{RID}.json').write_text('{"original":true}')
            root.joinpath(f'revisoes_{RID}.json').write_text('{"DIV-0001":"confirmada"}')
            server.STATE['status']='pronto';client=server.app.test_client()
            self.assertTrue(client.get('/api/checkpoints').get_json()[0]['valido'])
            response=client.post('/api/retomar/'+RID);self.assertEqual(response.status_code,200)
            novo=response.get_json()['id'];self.assertNotEqual(novo,RID)
            self.assertEqual(json.loads(root.joinpath(f'revisoes_{novo}.json').read_text()),{'DIV-0001':'confirmada'})
            self.assertEqual(root.joinpath(f'comparacao_{RID}.json').read_text(),'{"original":true}')
            self.assertEqual(client.post('/api/retomar/'+RID).status_code,409);thread.assert_called_once()

class DocumentQualityTests(unittest.TestCase):
    def test_mais_de_20_documentos_head_e_cache_url_entre_contextos(self):
        from ambidiff.documents import Documentos
        calls=[];d=Documentos(Metricas(),threading.Event(),permitir_range=False,observacao_por_execucao=True)
        def open_(req,timeout):
            calls.append(req);res=pdf();res.headers.replace_header('Cache-Control','no-cache');return res
        d.opener=NS(open=open_)
        for n in range(25):d.comparar(option('Portaria '+str(n),A+str(n)+'.pdf'),option('Portaria '+str(n),B+str(n)+'.pdf'),A,B)
        self.assertEqual(len(calls),50)
        d.comparar(option('Outro rótulo',A+'0.pdf'),option('Outro rótulo',B+'0.pdf'),A,B)
        self.assertEqual(len(calls),50);self.assertTrue(all(x.get_method()=='HEAD' for x in calls))
        self.assertFalse(e_arquivo(A+'documents/d/portal/icon.svg'));self.assertTrue(e_arquivo(A+'documents/d/portal/portaria'))
    def test_2232_referencias_reutilizam_duas_urls_sem_ler_corpo(self):
        from ambidiff.documents import Documentos
        d=Documentos(Metricas(),threading.Event(),permitir_range=False,observacao_por_execucao=True);calls=[]
        def responder(req,timeout):calls.append(req);return pdf()
        d.opener=NS(open=responder)
        for n in range(2232):d.comparar(option('Referência '+str(n),A+'manual.pdf'),option('Referência '+str(n),B+'manual.pdf'),A,B)
        self.assertEqual(len(calls),2);self.assertEqual(len(d.resultados),2232)
        self.assertTrue(all(r['a']['bytes_lidos']==r['b']['bytes_lidos']==0 for r in d.resultados))
    def test_normativas_texto_controle_agrupadas_com_membros_e_revisao_preservada(self):
        rows=[]
        for n,(tipo,txt,side) in enumerate([('Texto','Portaria nº 275/2026','PRD'),('Opção','Portaria nº 275/2026','PRD'),('Texto','Portaria nº 001/2025','DES'),('Opção','Portaria nº 001/2025','DES')]):
            rows.append({'id':f'DIV-{n+1:04}','tipo':tipo,'elemento':txt,'presente_em':side,'local':'Preço da terra','url_presente':A if side=='PRD' else B,'url_comparada':B if side=='PRD' else A})
        r=preparar({'divergencias':rows});self.assertEqual(len(r['divergencias']),1)
        self.assertEqual(len(r['divergencias'][0]['registros_agrupados']),4)
        manual=preparar({'divergencias':rows},{'DIV-0001':'inconclusivo'})
        self.assertTrue(any(x['id']=='DIV-0001' and x['classificacao']=='inconclusivo' for x in manual['divergencias']))
    def test_rotulo_editorial_repetido_nao_oculta_opcao_estrutural(self):
        from ambidiff.intelligence import separar_editoriais
        menu=option('Comunicados',A+'comunicados');news=option('Comunicados',A+'w/comunicados')
        menu.local='Menu';news.local='Notícias';news.natureza='editorial';news.entidade='/w/comunicados'
        rows=[{'tipo':'Opção','elemento':'Comunicados','presente_em':'PRD','local':'Menu'},
              {'tipo':'Opção','elemento':'Comunicados','presente_em':'PRD','local':'Notícias'}]
        regs,editoriais=separar_editoriais(rows,Pagina(A,'','',[]),Pagina(B,'','',[]),[menu,news],[],('PRD','DES'),'DES')
        self.assertEqual([r['local'] for r in regs],['Menu']);self.assertEqual(len(editoriais),1)
    def test_diagnostico_separa_acesso_automacao_e_bloqueios(self):
        from ambidiff.diagnostics import montar_diagnostico
        d=montar_diagnostico({'falhas':[{'tipo_erro':'HTTP','erro':'HTTP 403'},{'tipo_erro':'EXTRACAO','erro':'DOM null'},{'tipo_erro':'POLITICA_SEGURANCA','erro':'Bloqueado'}]})
        self.assertEqual(d['contadores_diagnostico'],{'acesso':1,'automacao':1,'bloqueios':1})
        self.assertEqual(len(d['falhas']),2);self.assertNotIn('POLITICA_SEGURANCA',d['falhas_por_tipo'])
    def test_relatorio_v2_menor_e_hidratacao_compatibilidade_revisao(self):
        from ambidiff.reports import exportar
        from ambidiff.storage import ler_original,preparar_relatorio,reclassificar
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);data={'id':RID,'formato_compacto':True,'divergencias':[{'id':'DIV-0001','tipo':'Texto','elemento':'Informação','descricao':'Diferente'}],
                'otimizacao':{'equivalencias_verificadas':[{'elemento':'Controle','evidencia':'x'*500} for _ in range(100)]},'metricas':{'releituras':[{'DOM':'x'*5000}]}}
            paths=exportar(data,root,RID);principal=json.loads(Path(paths['json']).read_text())
            self.assertEqual(principal['formato_relatorio'],2);self.assertNotIn('otimizacao',principal)
            self.assertLess(Path(paths['json']).stat().st_size,(root/f'detalhes_{RID}.json').stat().st_size)
            self.assertEqual(ler_original(root,RID)['otimizacao'],data['otimizacao'])
            before=Path(paths['json']).read_bytes();reclassificar(root,RID,'DIV-0001','editorial')
            self.assertEqual(preparar_relatorio(root,RID)['divergencias'][0]['classificacao'],'editorial')
            self.assertEqual(Path(paths['json']).read_bytes(),before)
            exportar(dict(data,exportacao_completa=True),root,'completo')
            self.assertEqual(json.loads(root.joinpath('comparacao_completo.json').read_text())['otimizacao'],data['otimizacao'])

class BrowserQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.pw=sync_playwright().start();cls.browser=navegador(cls.pw)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.pw.stop()
    def test_ancora_observada_fragmento_incerto_e_rota_funcional(self):
        from ambidiff.urlpolicy import fragmento
        pa=self.browser.new_page();pb=self.browser.new_page()
        try:
            for p,base in ((pa,A),(pb,B)):
                p.route(base,lambda r:r.fulfill(content_type='text/html',body='<main><h1>Portal</h1><a href="/documents/d/portal/icon.svg">Ícone</a><a id="link" href="#123">Ir</a><section id="123">Texto</section></main>'))
                p.goto(base)
            from ambidiff.core import JS_EXTRAIR
            self.assertFalse(any(x['tipo']=='Documento' for x in pa.evaluate(JS_EXTRAIR)['itens']))
            ia=option('Ir',A+'#123');ib=option('Ir',B);ia.seletor='#link';ib.seletor='#link'
            self.assertEqual(fragmento(ia,ib,pa,pb,A,B),'rolagem')
            ia.destino=A+'#nao-observado';self.assertEqual(fragmento(ia,ib,pa,pb,A,B),'inconclusivo')
            ia.destino=A+'#/servico';self.assertEqual(fragmento(ia,ib,pa,pb,A,B),'funcional')
        finally:pa.close();pb.close()
    def test_aviso_editorial_agrupado_preserva_institucional_e_download(self):
        from ambidiff.core import JS_EXTRAIR
        from ambidiff.intelligence import separar_editoriais,agrupar_variacoes
        pages=[];items=[]
        try:
            for base,html in ((A,'<h1>Portal</h1>'),(B,'<h1>Portal</h1><section role="alert"><h2>Aviso eleitoral</h2><p>Comunicado público.</p><p>Publicações temporariamente suspensas.</p></section><section><h2>Conselho</h2><p>Presidente Ana</p><a download href="/arquivo">Baixar Arquivo para Download</a></section>')):
                p=self.browser.new_page();pages.append(p);p.set_content('<base href="'+base+'">'+html)
                items.append([Item(**i) for i in p.evaluate(JS_EXTRAIR)['itens']])
            from ambidiff.core import comparacao
            pa=Pagina(A,'','',items[0]);pb=Pagina(B,'','',items[1]);comps=comparacao(items[0],items[1],pa,pb,'PRD','DES')
            regs,eds=separar_editoriais(comps,pa,pb,*items,('PRD','DES'),'DES')
            self.assertTrue(any('Presidente' in r['elemento'] for r in regs));self.assertTrue(any('Download' in r['elemento'] for r in regs))
            groups=agrupar_variacoes(eds,'DES');self.assertEqual(len(groups),1);self.assertEqual(len(groups[0]['registros']),3)
        finally:
            for p in pages:p.close()
    def test_interface_busca_membro_revisa_grupo_e_exporta_so_relevantes(self):
        from web import server
        from ambidiff.reports import exportar
        from test_next import missing_rows
        from ambidiff.storage import preparar_relatorio
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            root=Path(td);server.STATE['status']='pronto'
            exportar({'id':RID,'formato_compacto':True,'divergencias':missing_rows(),'paginas':{'PRD':1,'DES':1},'ambientes':{'PRD':A,'DES':B}},root,RID)
            original=root.joinpath(f'comparacao_{RID}.json').read_bytes();client=server.app.test_client();p=self.browser.new_page();downloads=[]
            def responder(route):
                req=route.request;url=req.url.split('http://ambidiff.test',1)[-1]
                if url.startswith('/download/'):downloads.append(url)
                if url.startswith('/api/status'):
                    route.fulfill(content_type='application/json',body='{"status":"pronto","progresso":0}');return
                res=client.open(url,method=req.method,data=req.post_data,content_type='application/json')
                route.fulfill(status=res.status_code,content_type=res.content_type,body=res.data);res.close()
            try:
                p.route('http://ambidiff.test/**',responder);p.goto('http://ambidiff.test/',wait_until='networkidle')
                p.evaluate('(id)=>openReport(id)',RID)
                p.locator('#search-results').fill('DIV-0002');self.assertIn('1 divergência',p.locator('#visible-count').inner_text())
                p.locator('#result-list button',has_text='Confirmar DIV').click()
                p.wait_for_function("currentReport.divergencias[0].revisao_manual==='confirmada'")
                revisoes=preparar_relatorio(root,RID)['revisoes_manuais'];self.assertEqual(set(revisoes),{'DIV-0001','DIV-0002'})
                p.locator('#filter-review').select_option('pendentes');self.assertIn('0 divergência',p.locator('#visible-count').inner_text())
                p.locator('#filter-review').select_option('confirmadas')
                p.locator('select[aria-label="Reclassificar DIV-0001"]').select_option('editorial')
                p.wait_for_function("currentReport.divergencias[0].classificacao==='editorial'")
                p.locator('#export-scope').select_option('relevantes');self.assertFalse(downloads)
                response=client.get(f'/download/{RID}/csv?relevantes=1')
                self.assertEqual(response.status_code,200);self.assertEqual(len(response.data.decode('utf-8-sig').splitlines()),1);response.close()
                self.assertEqual(root.joinpath(f'comparacao_{RID}.json').read_bytes(),original)
            finally:p.close()
    def test_dom_null_tem_retentativa_limitada_sem_falsa_div(self):
        from ambidiff.paired import _extrair_page
        p=self.browser.new_page();m=Metricas();m.parar=threading.Event()
        try:
            p.set_content('<h1>Inicial</h1>')
            p.evaluate("() => {document.body.remove();setTimeout(()=>{let b=document.createElement('body');b.innerHTML='<h1>Restaurado</h1>';document.documentElement.append(b)},100)}")
            with patch('ambidiff.paired._preparar_conteudo',return_value={'estavel':True,'rolagem_limitada':False}):
                r=_extrair_page(p,A,['Início'],lambda _:None,metricas=m)
            self.assertTrue(any(i.nome=='Restaurado' for i in r.itens));self.assertEqual(m.contagens['tentativas_extracao_adicionais'],1)
        finally:p.close()
    def test_tema_escuro_foco_teclado_e_classificacao(self):
        from web import server
        client=server.app.test_client();p=self.browser.new_page()
        try:
            p.set_content(client.get('/').data.decode());p.add_style_tag(path=str(Path('web/static/style.css').resolve()))
            for selector in ('#export-scope','#show-all-differences','#nome-a'):
                loc=p.locator(selector)
                if not loc.is_visible():p.locator('.screen').evaluate_all('(els)=>els.forEach(e=>{e.style.display="block"})')
                loc.focus();self.assertTrue(loc.evaluate('e=>document.activeElement===e'))
                self.assertEqual(loc.evaluate('e=>getComputedStyle(e).colorScheme'),'dark')
            self.assertNotEqual(p.locator('#export-scope').evaluate('e=>getComputedStyle(e).backgroundColor'),'rgb(255, 255, 255)')
        finally:p.close()

if __name__=='__main__':unittest.main()
