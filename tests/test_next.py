"""Próxima atualização: dados sintéticos, transporte simulado e somente loopback."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ambidiff.core import Item,Pagina
from ambidiff.paired import link_equivalente,agrupar_registros,executar_pareado
from ambidiff.live import Logs
from ambidiff.sections import comparar_secoes
from ambidiff.relevance import preparar
from ambidiff.smart import Metricas
from ambidiff.destinations import Destinos
from test_smart import navegador
from test_perf import html_run

A='https://a.test/';B='https://b.test/web/portal'
RID='20261022_130000_abcdef'

def option(name,local='Estrutura',destino='',tipo='Opção',selector=''):
    return Item(tipo,name,name,local=local,destino=destino,seletor=selector,natureza='estrutura',funcao='link',estrutura='A||false||||estatico')
def pagina(url,items):return Pagina(url,'@inicio','Portal',items,['Início'],coleta={'estavel':True})

def missing_rows(names=('Ato 002','Ato 004')):
    return [{'id':f'DIV-{i:04}','tipo':'Documento','elemento':n,'local':'Atos','referencia':A+str(i)+'.pdf','url_presente':A,'url_comparada':B,'presente_em':'PRD','nao_identificado_em':'DES','descricao':'Não identificado','ocorrencias':[{'url_presente':A,'url_comparada':B,'local':'Atos'}]} for i,n in enumerate(names,1)]

class LiveTests(unittest.TestCase):
    def test_janela_199_200_201_1000_cursor_e_lacunas(self):
        for quantidade in (199,200,201,1000):
            feed=Logs()
            for n in range(quantidade):feed.adicionar('Par '+str(n))
            r=feed.consultar(max(0,quantidade-5))
            self.assertEqual(len(r['eventos_logs']),5);self.assertEqual(r['cursor_logs'],quantidade)
            self.assertFalse(feed.consultar(quantidade)['eventos_logs'])
            self.assertLessEqual(len(feed.eventos),200)
            future=feed.consultar(quantidade+100);self.assertTrue(future['lacuna_logs']);self.assertTrue(future['eventos_logs'])
            if quantidade>201:self.assertTrue(feed.consultar(1)['lacuna_logs'])
    def test_api_logs_incremental_sem_duplicar_e_arquivo_completo(self):
        from web import server
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.object(server,'FEED',Logs()),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            server.STATE.update(execucao_id=RID,execucao_log_inicio=0,logs=[])
            for i in range(1000):server.log('Linha '+str(i))
            client=server.app.test_client();r=client.get('/api/status?cursor=990').get_json()
            self.assertEqual(len(r['eventos_logs']),10);self.assertEqual(len({x['id'] for x in r['eventos_logs']}),10)
            self.assertFalse(client.get('/api/status?cursor=1000').get_json()['eventos_logs'])
            self.assertTrue(client.get('/api/status?cursor=5').get_json()['lacuna_logs'])
            response=client.get(f'/api/execucao/{RID}/logs');self.assertEqual(len(response.data.decode().splitlines()),1000);response.close()
    def test_run_novo_preserva_sequencia_e_nao_vaza_logs_anteriores(self):
        feed=Logs();feed.adicionar('antigo');previous=feed.seq;feed.eventos.clear();feed.adicionar('novo')
        self.assertGreater(feed.seq,previous);self.assertEqual([e['texto'] for e in feed.consultar(previous)['eventos_logs']],['novo'])

class RootSectionTests(unittest.TestCase):
    def test_raizes_prefixos_queries_caixa_e_externos(self):
        for ua,ub,esperado in [(A,B,True),(A,B+'/',True),(A+'consulta?x=1',B+'/consulta?x=1',True),
             (A+'consulta?x=1',B+'/consulta?x=2',False),(A+'consulta?token=1',B+'/consulta?token=2',False),(A+'Consulta',B+'/consulta',False),(A+'#estrutura',B+'#servicos',False),(A+'#estrutura',B+'#estrutura',True),
             (A+'portal',B+'-outro',False),(A+'consulta','https://externo.test/consulta',False)]:
            self.assertEqual(link_equivalente(ua,ub,A,B),esperado,(ua,ub))
    def test_ausencia_na_secao_e_realocacao_nos_dois_sentidos(self):
        for inverso in (False,True):
            a=pagina(A,[option('Organograma')]);b=pagina(B,[option('Organograma','Serviços')])
            rows=comparar_secoes([],*( (b,a,'DES','PRD') if inverso else (a,b,'PRD','DES')))
            self.assertEqual(len(rows),2)
            self.assertTrue(all('OPCAO_AUSENTE_NA_SECAO' in r['tags'] for r in rows))
            self.assertTrue(all(r['realocado_possivelmente_para'] for r in rows))
            self.assertEqual({r['presente_em'] for r in rows},{'PRD','DES'})
    def test_espacos_e_posicao_na_mesma_secao_nao_sao_ausencia(self):
        rows=comparar_secoes([],pagina(A,[option('Serviços gerais')]),pagina(B,[option('Serviços  gerais')]),'PRD','DES')
        self.assertFalse(rows)
    def test_cge_e_outra_opcao_sao_genericas(self):
        for name in ('ÁUDIOS','Conselho consultivo'):
            rows=comparar_secoes([],pagina(A,[option(name)]),pagina(B,[]),'PRD','DES')
            self.assertEqual(rows[0]['elemento'],name);self.assertEqual(rows[0]['presente_em'],'PRD')
    def test_documentos_uma_div_e_detalhes_json_html_csv(self):
        from ambidiff.reports import exportar
        rows=missing_rows();original=copy.deepcopy(rows);r=preparar({'divergencias':rows,'paginas':{}})
        self.assertEqual(len(r['divergencias']),1);group=r['divergencias'][0]
        self.assertEqual(group['quantidade_itens'],2);self.assertEqual([x['elemento'] for x in group['itens_agrupados']],['Ato 002','Ato 004'])
        self.assertEqual(rows,original)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);paths=exportar({'divergencias':rows,'paginas':{}},root,'teste')
            with open(paths['csv'],encoding='utf-8-sig') as f:self.assertEqual(len(list(csv.DictReader(f,delimiter=';'))),1)
            saved=json.loads(Path(paths['json']).read_text());self.assertEqual(len(saved['divergencias'][0]['registros_agrupados']),2)
            self.assertIn('Ato 004',Path(paths['html']).read_text())
            paths=exportar({'divergencias':rows,'paginas':{},'exportacao_completa':True},root,'completo')
            with open(paths['csv'],encoding='utf-8-sig') as f:self.assertEqual(len(list(csv.DictReader(f,delimiter=';'))),2)
    def test_secoes_distintas_e_naturezas_diferentes_nao_agrupam(self):
        rows=missing_rows();rows[1]['local']='Licenças'
        self.assertEqual(len(preparar({'divergencias':rows})['divergencias']),2)
        rows=missing_rows();rows[1]['tipo']='Redirecionamento';rows[1]['destino_a']=A+'x'
        self.assertEqual(len(preparar({'divergencias':rows})['divergencias']),2)
    def test_reclassificacao_grupo_preserva_bytes_originais(self):
        from ambidiff.storage import atomic_json,reclassificar
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);file=root/f'comparacao_{RID}.json';atomic_json(file,{'divergencias':missing_rows()});original=file.read_bytes()
            r=reclassificar(root,RID,'DIV-0002','inconclusivo')
            self.assertEqual(len(r['divergencias']),2);self.assertEqual(file.read_bytes(),original)

class DestinationTests(unittest.TestCase):
    def checker(self,respostas,externos=True,limite=100,privado=False):
        calls=[];values=iter(respostas)
        def transport(p,ip,timeout):calls.append((p.geturl(),ip,timeout));v=next(values);return v
        def dns(host,port,**kwargs):return [(2,1,6,'',('127.0.0.1' if privado else '93.184.216.34',port))]
        return Destinos(Metricas(),threading.Event(),(A,B),externos=externos,limite=limite,transporte=transport,resolver=dns),calls
    def test_destinos_equivalentes_redirecionados_sem_corpo_e_cache(self):
        d,c=self.checker([(302,{'location':'https://public.test/login'}),(200,{})])
        r=d.comparar('https://public.test/inicio','https://public.test/inicio',A,B)
        self.assertEqual(r['classificacao'],'DESTINO_EQUIVALENTE');self.assertEqual(len(c),2)
        self.assertEqual(r['a']['url_final'],'https://public.test/login');self.assertEqual(r['a']['bytes_lidos'],0)
        self.assertTrue(r['b']['reaproveitado'])
    def test_divergentes_inacessivel_bloqueio_head_e_timeout(self):
        for respostas,expected in [([(200,{}),(200,{})],'DESTINO_DIVERGENTE'), ([(403,{}),(200,{})],'LINK_INACESSIVEL'), ([(405,{}),(200,{})],'VERIFICACAO_INCONCLUSIVA')]:
            d,c=self.checker(respostas);r=d.comparar('https://one.test/','https://two.test/',A,B)
            self.assertEqual(r['classificacao'],expected);self.assertEqual(len(c),2)
        d,c=self.checker([]);d.transporte=lambda *args:(_ for _ in ()).throw(TimeoutError('tempo'))
        self.assertEqual(d.conferir('https://public.test/')['classificacao'],'VERIFICACAO_INCONCLUSIVA')
    def test_privados_redirecionamentos_esquemas_e_credenciais_bloqueados(self):
        d,c=self.checker([(302,{'location':'http://127.0.0.1/admin'})])
        def resolver(host,port,**kwargs):return [(2,1,6,'',('127.0.0.1' if host=='127.0.0.1' else '93.184.216.34',port))]
        d.resolver=resolver;r=d.conferir('https://public.test/')
        self.assertEqual(r['classificacao'],'VERIFICACAO_INCONCLUSIVA');self.assertEqual(len(c),1)
        for url in ('file:///segredo','http://user:password@public.test/','http://public.test/delete','https://public.test:4567/','https://public.test/?token=nao-enviar','https://public.test/?u=http%3A%2F%2Frede.test%2F'):
            d,c=self.checker([(200,{})]);self.assertEqual(d.conferir(url)['classificacao'],'VERIFICACAO_INCONCLUSIVA');self.assertFalse(c)
    def test_origem_privada_explicita_e_permitida_mas_terceiros_nao(self):
        d,c=self.checker([(200,{})],privado=True);self.assertEqual(d.conferir(A)['classificacao'],'DESTINO_ACESSIVEL')
        self.assertEqual(d.conferir('https://terceiro.test/')['classificacao'],'VERIFICACAO_INCONCLUSIVA');self.assertEqual(len(c),1)
    def test_limites_cancelamento_e_externo_nao_habilitado(self):
        for limite,externos,cancel in ((0,True,False),(10,False,False),(10,True,True)):
            d,c=self.checker([(200,{})],externos=externos,limite=limite)
            if cancel:d.parar.set()
            self.assertEqual(d.conferir('https://public.test/')['classificacao'],'VERIFICACAO_INCONCLUSIVA');self.assertFalse(c)
    def test_head_loopback_nao_explora_login_nem_links(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_HEAD(self):
                requests.append(('HEAD',self.path));self.send_response(302 if self.path=='/inicio' else 200)
                if self.path=='/inicio':self.send_header('Location','/login')
                self.end_headers()
            def do_GET(self):requests.append(('GET',self.path));self.send_response(500);self.end_headers()
        serv=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=serv.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{serv.server_port}/'
        try:
            d=Destinos(Metricas(),threading.Event(),(base,));r=d.conferir(base+'inicio')
            self.assertEqual(r['classificacao'],'DESTINO_ACESSIVEL');self.assertEqual(requests,[('HEAD','/inicio'),('HEAD','/login')])
        finally:serv.shutdown();serv.server_close();thread.join()
    def test_documento_head_nao_suportado_nao_usa_get(self):
        from ambidiff.documents import Documentos
        from test_smart import Response
        d=Documentos(Metricas(),threading.Event(),permitir_range=False)
        with patch.object(d.opener,'open',return_value=Response(405)) as request:
            r=d.conferir(A+'arquivo.pdf',A)
            self.assertEqual(request.call_count,1);self.assertEqual(r['situacao'],'inconclusivo');self.assertIn('GET não realizado',r['motivo'])

from contextlib import contextmanager
@contextmanager
def interacoes(modos):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    servers=[];threads=[];pedidos=[]
    for modo in modos:
        def handler(mode):
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_POST(self):pedidos.append(('POST',self.path));self.send_response(500);self.end_headers()
                def do_GET(self):
                    pedidos.append(('GET',self.path))
                    control={'inerte':'<button id="controle" aria-controls="dados" aria-expanded="false">Mostrar informações</button><p id="dados" hidden>Detalhes observados</p>',
                     'disclosure':'<button id="controle" aria-controls="dados" aria-expanded="false" onclick="document.getElementById(\'dados\').hidden=false;this.setAttribute(\'aria-expanded\',\'true\')">Mostrar informações</button><p id="dados" hidden>Detalhes observados</p>',
                     'popup':'<a id="controle" href="/consulta" target="_blank">Consultar</a>',
                     'js':'<a id="controle" href="/" onclick="location.href=\'/consulta\';return false">Consultar</a>',
                     'js_outro':'<a id="controle" href="/" onclick="location.href=\'/outro\';return false">Consultar</a>',
                     'post':'<script>fetch(\'/alterar\',{method:\'POST\'}).catch(()=>{})</script><p>Conteúdo público</p>'}[mode]
                    body=('<html><head><meta charset="utf-8"><link rel="icon" href="data:,"></head><body>'+control+'</body></html>').encode()
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(body)
            return Handler
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(modo));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();servers.append(server);threads.append(thread)
    try:yield [f'http://127.0.0.1:{s.server_port}/' for s in servers],pedidos
    finally:
        for server in servers:server.shutdown();server.server_close()
        for thread in threads:thread.join()

class BrowserNextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.pw=sync_playwright().start();cls.browser=navegador(cls.pw)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.pw.stop()
    def test_mutacao_cosmetica_nao_invalida_sonda_mas_texto_sim(self):
        from ambidiff.adaptive import sondar
        p=self.browser.new_page()
        try:
            p.set_content('<p id="info">Regra institucional</p><span id="clock">01</span>');a=sondar(p)
            p.evaluate("document.querySelector('p').style.color='red'");b=sondar(p)
            self.assertEqual(a['versao'],b['versao'])
            p.evaluate("document.querySelector('#clock').textContent='02'");self.assertEqual(sondar(p)['versao'],b['versao'])
            p.evaluate("document.querySelector('p').textContent='Outra informação'");c=sondar(p)
            self.assertGreater(c['versao'],b['versao'])
        finally:p.close()
    def test_submenu_recolhido_e_details_sao_coletados(self):
        from ambidiff.paired import _extrair_page
        p=self.browser.new_page()
        try:
            p.set_content('<nav aria-label="Institucional"><button aria-expanded="false" aria-controls="sub" onclick="document.getElementById(\'sub\').hidden=false;this.setAttribute(\'aria-expanded\',\'true\')">Estrutura</button><div id="sub" hidden><a href="https://a.test/estrutura">Organização administrativa</a></div></nav><details><summary>Atos</summary><a href="https://a.test/ato.pdf">Ato normativo</a></details>')
            r=_extrair_page(p,A,['Início'],lambda _:None)
            self.assertTrue(any(i.nome=='Organização administrativa' for i in r.itens));self.assertTrue(any(i.nome=='Ato normativo' for i in r.itens))
        finally:p.close()
    def test_formulario_vazio_e_ambientes_neutros(self):
        from web import server
        client=server.app.test_client();html=client.get('/').data.decode()
        p=self.browser.new_page()
        try:
            p.set_content(html)
            self.assertEqual(p.locator('#url-a').input_value(),'');self.assertEqual(p.locator('#url-b').input_value(),'')
            self.assertEqual(p.locator('#nome-a option').count(),3);self.assertEqual(p.locator('#nome-b option').count(),3)
            with patch.object(server.threading,'Thread') as th:
                self.assertEqual(client.post('/api/comparar',json={'url_a':A,'url_b':B,'nome_a':'DES','nome_b':'DES'}).status_code,400);th.assert_not_called()
        finally:p.close()
    def test_frontend_reconecta_logs_rotativos_relogio_e_uma_conclusao(self):
        from web import server
        client=server.app.test_client();p=self.browser.new_page();estado={'n':0,'fail':False,'done':False,'stop':0};errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
        def responder(route):
            req=route.request;url=req.url.split('http://ambidiff.test',1)[-1]
            if url=='/api/parar':
                estado['stop']+=1;route.fulfill(status=200,content_type='application/json',body='{"interrupcao_solicitada":true}');return
            if url.startswith('/api/status'):
                if estado['fail']:estado['fail']=False;route.fulfill(status=503,content_type='application/json',body='{"erro":"indisponível"}');return
                estado['n']+=1;n=estado['n'];data={'status':'concluido' if estado['done'] else 'executando','progresso':34,'interrupcao_solicitada':bool(estado['stop']),'andamento':{'par_atual':8,'ultimo_par_processado':7},'tempo_decorrido_segundos':40+n,'tempo_restante_segundos':None,'execucao_id':RID,'cursor_logs':n*200,'eventos_logs':[{'id':n*200+i,'texto':'Evento '+str(n*200+i)} for i in range(-199,1)],'lacuna_logs':False,'ultimo_id':RID if estado['done'] else None}
                route.fulfill(status=200,content_type='application/json',body=json.dumps(data));return
            if url.startswith('/api/relatorio/'):
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'divergencias':[],'paginas':{}}));return
            res=client.get(url);route.fulfill(status=res.status_code,content_type=res.content_type,body=res.data);res.close()
        try:
            p.route('http://ambidiff.test/**',responder);p.goto('http://ambidiff.test/',wait_until='networkidle');p.wait_for_function('logCursor>=200')
            for _ in range(4):p.evaluate('poll()')
            self.assertEqual(p.locator('#terminal > div').count(),500)
            p.locator('.execution-diagnostics > summary').click()
            self.assertIn('Último par processado: 7',p.locator('#execution-details').inner_text())
            p.locator('#stop-button').click();p.wait_for_function("document.querySelector('#running-label').textContent.includes('Interrupção solicitada')")
            self.assertTrue(p.locator('#stop-button').is_disabled());self.assertEqual(estado['stop'],1)
            estado['fail']=True;p.evaluate('poll()');self.assertIn('indisponível',p.locator('#connection-state').inner_text());self.assertTrue(p.locator('#run-button').is_disabled())
            p.wait_for_function("document.querySelector('#connection-state').textContent==='Comunicação ativa'",timeout=6500)
            self.assertIn('Decorrido:',p.locator('#progress-elapsed').inner_text())
            estado['done']=True;p.evaluate('poll()');p.evaluate('poll()')
            self.assertEqual(p.evaluate('openedRuns.size'),1);self.assertFalse(errors)
        finally:p.close()

    def test_controle_seguro_sem_href_diferente_gera_observacao(self):
        from ambidiff.functional import verificar_par,escolher_candidatos
        with interacoes(('disclosure','inerte')) as (bases,_):
            a=option('Mostrar informações',selector='#controle');b=copy.deepcopy(a);a.controle_alvo=b.controle_alvo='dados';a.funcao=b.funcao='button'
            self.assertEqual(len(escolher_candidatos([(a,b)],*bases)),1)
            diagnostics=[];r=verificar_par(self.browser,pagina(bases[0],[a]),pagina(bases[1],[b]),a,b,'PRD','DES',*bases,lambda _:None,diagnosticos=diagnostics)
            self.assertIsNotNone(r);self.assertEqual(r['tag_observacao'],'FALHA_FUNCIONAL_OBSERVADA')
            self.assertEqual(r['resultado_funcional_a'],'resposta_conteudo');self.assertTrue(diagnostics[0]['conclusivo'])
    def test_popup_e_js_observados_sem_funcao_inferida_por_href(self):
        from ambidiff.functional import _um_clique,verificar_par
        with interacoes(('popup','js')) as (bases,_):
            a=option('Consultar',destino=bases[0]+'consulta',selector='#controle')
            self.assertEqual(_um_clique(self.browser,pagina(bases[0],[a]),a,bases[0]),'navegou')
            b=option('Consultar',destino=bases[1],selector='#controle')
            self.assertEqual(_um_clique(self.browser,pagina(bases[1],[b]),b,bases[1]),'navegou')
        with interacoes(('js','js_outro')) as (bases,_):
            a=option('Consultar',destino=bases[0],selector='#controle');b=option('Consultar',destino=bases[1],selector='#controle')
            r=verificar_par(self.browser,pagina(bases[0],[a]),pagina(bases[1],[b]),a,b,'PRD','DES',*bases,lambda _:None)
            self.assertIsNotNone(r);self.assertNotEqual(r['destino_final_a'],r['destino_final_b'])
    def test_nomes_html_diferentes_mesmo_destino_mantem_rotulo_divergente(self):
        from ambidiff.smart import Inteligencia
        a=option('Organograma',destino=A+'estrutura');b=option('Estrutura Organizacional',destino=B+'/estrutura')
        a.estrutura='A||text|false|||SPAN|estatico';b.estrutura='A||text|false||||estatico'
        rows=Inteligencia(Metricas()).comparar([a],[b],pagina(A,[a]),pagina(B,[b]),'PRD','DES',A,B)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['tipo'],'Rótulo');self.assertEqual(rows[0]['texto_b'],b.nome)
    def test_informacoes_diferentes_preservam_valores_sem_presumir_causa(self):
        a=option('Rita Melo',tipo='Texto',selector='#titular');b=option('Carlos Souza',tipo='Texto',selector='#titular')
        from ambidiff.core import comparacao
        pa=pagina(A,[a]);pb=pagina(B,[b]);rows=comparar_secoes(comparacao([a],[b],pa,pb,'PRD','DES'),pa,pb,'PRD','DES')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['texto_a'],'Rita Melo');self.assertEqual(rows[0]['texto_b'],'Carlos Souza');self.assertTrue(rows[0]['possivel_diferenca_dados'])

class PipelineNextTests(unittest.TestCase):
    def test_requisicao_de_escrita_nao_atinge_servidor(self):
        with interacoes(('post','post')) as (bases,pedidos):
            r=executar_pareado(*bases,'PRD','DES',threading.Event(),lambda _:None,lambda _:None,varredura_inteligente=True)
            self.assertFalse(any(method=='POST' for method,path in pedidos))
            self.assertTrue(any(f.get('tipo_erro')=='POLITICA_SEGURANCA' for f in r['bloqueios_seguranca']))
            self.assertFalse(any(f.get('tipo_erro')=='POLITICA_SEGURANCA' for f in r['falhas']))
            self.assertNotEqual(r['situacao_analise'],'concluido')

    def test_implantacao_em_subpasta_percorre_rotas_equivalentes(self):
        def setup(ca,cb):
            for context,base in ((ca,A),(cb,B)):
                def responder(root):
                    def handle(route):route.fulfill(status=200,content_type='text/html; charset=utf-8',body='<nav aria-label="Serviços"><a href="'+root.rstrip('/')+'/consulta">Consulta</a></nav><p>Portal institucional</p>')
                    return handle
                context.route('**/*',responder(base))
        r=executar_pareado(A,B,'PRD','DES',threading.Event(),lambda _:None,lambda _:None,_preparar_contextos=setup,varredura_inteligente=True)
        self.assertEqual(r['paginas'],{'PRD':2,'DES':2});self.assertFalse(r['divergencias'])

    def test_documentos_ausentes_na_secao_nao_sao_baixados(self):
        a='<section><h2>Portarias</h2><a href="https://portal-a.test/002.pdf">Portaria 002</a><a href="https://portal-a.test/004.pdf">Portaria 004</a></section>'
        b='<section><h2>Portarias</h2><p>Lista de atos</p></section>'
        with patch('ambidiff.documents.Documentos.conferir',side_effect=AssertionError('Não acessar documentos exclusivos')):
            r=html_run(a,b,varredura_inteligente=True)
        data=preparar(r);groups=[d for d in data['divergencias'] if d.get('itens_agrupados')]
        self.assertEqual(len(groups),1);self.assertEqual(len(groups[0]['itens_agrupados']),2)
