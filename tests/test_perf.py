"""Regressões genéricas: somente HTML sintético, mocks e loopback."""
import copy
from datetime import datetime
import json
import shutil
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ambidiff.core import Item,Pagina,JS_EXTRAIR,comparacao,executar
from ambidiff.smart import Inteligencia,Metricas
from ambidiff.adaptive import preparar,sondar,decidir_releitura,cobertura_nao_piorou
from ambidiff.paired import agrupar_registros,_link_pairs,executar_pareado
from ambidiff.relevance import preparar as classificar_relatorio
from ambidiff.taxonomy import enriquecer,relacionar,TAGS

A='https://portal-a.test/';B='https://portal-b.test/'

def pagina(base,itens=None):return Pagina(base,'@inicio','Portal',itens or [],['Início'],coleta={'estavel':True,'rolagem_limitada':False})
def item(nome,destino='',**kw):return Item('Opção',nome,nome,local='Serviços',destino=destino,funcao='link',estrutura='A|link|estatico',**kw)
def comparar_smart(a,b):return Inteligencia(Metricas()).comparar(a,b,pagina(A,a),pagina(B,b),'PRD','LAB',A,B)

def html_run(a,b,**kwargs):
    def contexts(ca,cb):
        for context,html in ((ca,a),(cb,b)):
            def response(text):
                def handle(route):route.fulfill(status=200,content_type='text/html; charset=utf-8',body=text)
                return handle
            context.route('**/*',response(html))
    stop=kwargs.pop('parar',threading.Event())
    return executar_pareado(A,B,'PRD','LAB',stop,lambda _:None,kwargs.pop('progresso',lambda _:None),_preparar_contextos=contexts,**kwargs)

class ComparisonPerfTests(unittest.TestCase):
    def test_opcoes_exclusivas_nomes_e_sentidos_variados(self):
        for nome,reverse in [('ÁUDIOS',False),('Solicitar certidão',False),('Consultar orçamento',True)]:
            x=item(nome);a,b=([x],[]) if not reverse else ([],[x])
            rows=enriquecer(comparar_smart(a,b))
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['tag_tecnica'],'OPCAO_AUSENTE')
            self.assertEqual(rows[0]['presente_em'],'LAB' if reverse else 'PRD')
            self.assertEqual(classificar_relatorio({'divergencias':rows})['divergencias'][0]['classificacao'],'relevante')
    def test_posicao_diferente_equivalencia_sem_ausencia(self):
        a=item('Consulta',A+'consulta',posicao='Cabeçalho');b=item('Consulta',B+'consulta',posicao='Rodapé')
        self.assertEqual(comparar_smart([a],[b]),[])
    def test_menu_reorganizado_mantem_elementos(self):
        a=[item(n,A+n) for n in ('Alfa','Beta','Gama')];b=[item(n,B+n) for n in ('Gama','Alfa','Beta')]
        self.assertEqual(comparar_smart(a,b),[])
    def test_rotulo_novo_associado_por_destino_papel_contexto(self):
        a=item('CONSULTAR',A+'busca');b=item('PESQUISAR',B+'busca')
        rows=enriquecer(comparar_smart([a],[b]));self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['tag_tecnica'],'ROTULO_DIVERGENTE')
        self.assertEqual(rows[0]['texto_b'],'PESQUISAR')
        self.assertEqual(len(_link_pairs(pagina(A,[a]),pagina(B,[b]),aceitar_rotulos=True)),1)
    def test_rotulos_nao_pareiam_ambiguidade_ou_funcao_distinta(self):
        a=item('Ver processo',A+'busca');b=item('Pesquisar',B+'busca')
        rows=comparar_smart([a],[b,item('Procurar',B+'busca')])
        self.assertFalse(any(r['tipo']=='Rótulo' for r in rows))
        b.funcao='button';self.assertFalse(any(r['tipo']=='Rótulo' for r in comparar_smart([a],[b])))
    def test_par_com_mesmo_rotulo_nao_e_trocado_por_outro(self):
        a=item('Consultar',A+'busca');b=item('Consultar',B+'busca');other=item('Outro serviço',B+'busca')
        a.estrutura=b.estrutura=other.estrutura='A|link|dinamico'
        rows=comparar_smart([a],[b,other])
        self.assertFalse(any(r['tipo']=='Rótulo' for r in rows))
        self.assertTrue(any(r['elemento']=='Outro serviço' for r in rows))
    def test_destinos_distintos_continuam_visiveis(self):
        from ambidiff.paired import _diff_destino
        row=_diff_destino(pagina(A),pagina(B),item('Prestação',A+'energia.pdf'),item('Prestação',B+'agua.pdf'),'PRD','LAB')
        data=classificar_relatorio({'divergencias':[row]});out=data['divergencias'][0]
        self.assertIn('DESTINO_DIVERGENTE',out['tags']);self.assertIn('DOCUMENTO_DIVERGENTE',out['tags'])
        self.assertEqual(out['grau_confianca'],'confirmada_referencia');self.assertEqual(out['classificacao'],'relevante')
        self.assertFalse(out['teste_funcional_executado'])
    def test_funcao_diferente_nao_e_falha_confirmada_sem_teste(self):
        a=item('Ver situação');b=item('Ver situação');b.funcao='button'
        rows=enriquecer(comparar_smart([a],[b]));self.assertIn('FUNCAO_DIVERGENTE',[r['tag_tecnica'] for r in rows])
        self.assertFalse(any(r['teste_funcional_executado'] for r in rows))
        self.assertEqual(enriquecer([{'tipo':'Clique','teste_funcional_executado':True}])[0]['tag_tecnica'],'FALHA_FUNCIONAL_VERIFICADA')
    def test_coleta_inconclusiva_e_evidencia_sem_seletor(self):
        row=enriquecer([{'tipo':'Contexto','marcacoes':{'PRD':'Área da página; elemento não localizado nesta captura'}}])[0]
        self.assertEqual(row['grau_confianca'],'inconclusiva')
        self.assertNotIn('confirmada',row['grau_confianca'])
    def test_widget_repetido_preserva_registros_e_relaciona_partes(self):
        rows=[]
        for n in range(208):
            for tipo,nome in [('Imagem','Ilustração de contato'),('Opção','Abrir canal auxiliar')]:
                rows.append({'tipo':tipo,'elemento':nome,'presente_em':'LAB','nao_identificado_em':'PRD','local':'Auxílio','url_presente':f'{B}{n}','url_comparada':f'{A}{n}','componente_id':'#widget-x','descricao':'Não identificado no outro ambiente','seletor':'#imagem' if tipo=='Imagem' else '#abrir'})
        original=copy.deepcopy(rows);groups=agrupar_registros(rows)
        self.assertEqual(len(groups),2);self.assertEqual(rows,original)
        self.assertTrue(all(r['ocorrencias_total']==208 for r in groups))
        self.assertEqual(len({r['id_ocorrencia'] for g in groups for r in g['registros_individuais']}),416)
        relations=relacionar(groups);self.assertEqual(len(relations),208)
        self.assertTrue(all(set(g['ids'])=={r['id'] for r in groups} and not g['causa_confirmada'] for g in relations))
    def test_secao_compartilhada_hipotese_e_pagina_sozinha_nao_relaciona(self):
        rows=[{'id':'DIV-0001','tipo':'Opção','url_presente':A,'secao_id':'#servicos'},
              {'id':'DIV-0002','tipo':'Texto','url_presente':A,'secao_id':'#servicos'},
              {'id':'DIV-0003','tipo':'Imagem','url_presente':A}]
        rel=relacionar(rows);self.assertEqual(rel[0]['ids'],['DIV-0001','DIV-0002'])
        for r in rows:r.pop('secao_id',None)
        self.assertEqual(relacionar(rows),[])
    def test_secao_alterada_relaciona_diferencas_nos_dois_sentidos(self):
        rows=[{'id':'DIV-0001','tipo':'Opção','url_presente':A,'url_comparada':B,'secao_id':'#institucional'},
              {'id':'DIV-0002','tipo':'Texto','url_presente':B,'url_comparada':A,'secao_id':'#institucional'}]
        groups=relacionar(rows)
        self.assertEqual(len(groups),1);self.assertEqual(groups[0]['ids'],['DIV-0001','DIV-0002'])
        self.assertEqual(set(groups[0]['urls']),{A,B});self.assertFalse(groups[0]['causa_confirmada'])
    def test_agrupamento_nao_funde_destinos_nem_muta_ids(self):
        rows=[{'id':f'DIV-{i:04}','tipo':'Rótulo','elemento':'Consultar / Pesquisar','destino_a':A+str(i),'destino_b':B+str(i),'descricao':'Rótulos diferentes'} for i in (1,2)]
        self.assertEqual(len(agrupar_registros(rows)),2)
        report={'divergencias':rows};raw=copy.deepcopy(report);out=classificar_relatorio(report)
        self.assertEqual(report,raw);self.assertEqual([r['id'] for r in out['divergencias']],['DIV-0001','DIV-0002'])
    def test_metricas_duracao_monotonica_e_serializacao(self):
        with patch('ambidiff.smart.time.perf_counter',side_effect=[10,15]):
            m=Metricas();m.finalizar()
        self.assertEqual(m.temporal()['duracao_segundos'],5)
        self.assertIsNotNone(datetime.fromisoformat(m.temporal()['iniciado_em']).tzinfo)
        self.assertIsNotNone(datetime.fromisoformat(m.temporal()['finalizado_em']).tzinfo)
        self.assertEqual(json.loads(json.dumps(m.temporal()))['duracao_segundos'],5)
    def test_releitura_pior_preserva_primeira_coleta(self):
        old=pagina(A,[item('Ver'),item('Abrir')]);new=pagina(A,[item('Ver')])
        self.assertFalse(cobertura_nao_piorou(old,new))
        new.itens.append(item('Abrir'));self.assertTrue(cobertura_nao_piorou(old,new))
        new.coleta['estavel']=False;self.assertFalse(cobertura_nao_piorou(old,new))

class BrowserPerfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.pw=sync_playwright().start()
        try:cls.browser=cls.pw.chromium.launch(headless=True)
        except Exception:
            executable=shutil.which('chromium') or shutil.which('chromium-browser')
            if not executable:cls.pw.stop();raise
            cls.browser=cls.pw.chromium.launch(headless=True,executable_path=executable,args=['--no-sandbox'])
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.pw.stop()
    def test_estavel_sem_segunda_preparacao_por_divergencia(self):
        pages=[self.browser.new_page(),self.browser.new_page()]
        try:
            pag=[]
            for page,base in zip(pages,(A,B)):
                page.set_content('<main><p>Conteúdo institucional</p></main>')
                stats=preparar(page,lambda _:None);p=pagina(base);p.coleta=stats;pag.append(p)
                self.assertTrue(stats['estavel']);self.assertEqual(stats['verificacoes_omitidas'],[])
            diffs=[{'tipo':'Texto','elemento':str(i)} for i in range(15)]
            self.assertEqual(decidir_releitura(*pages,*pag,diffs,threading.Event()),[])
            pages[0].evaluate("document.querySelector('p').textContent='Alteração efetiva'")
            self.assertIn('DOM mudou após a coleta',decidir_releitura(*pages,*pag,diffs,threading.Event()))
        finally:
            for p in pages:p.close()
    def test_pagina_dinamica_lazy_e_aba_sao_inspecionadas(self):
        from ambidiff.paired import _extrair_page
        page=self.browser.new_page(viewport={'width':1000,'height':600})
        try:
            page.set_content('''<main><button role="tab" onclick="document.getElementById('painel').textContent='Dados da aba carregados'">Informações</button><p id="painel">Prévia</p></main><div style="height:2000px"></div><p id="lazy"></p>
            <script>addEventListener('scroll',()=>{if(scrollY>500)document.getElementById('lazy').textContent='Conteúdo ativado por rolagem'});setTimeout(()=>{const p=document.createElement('p');p.textContent='Conteúdo tardio observado';document.body.append(p)},300)</script>''')
            p=_extrair_page(page,A,['Início'],lambda _:None)
            labels=[i.nome for i in p.itens]
            self.assertTrue(any('Dados da aba carregados' in n for n in labels))
            self.assertTrue(any('Conteúdo ativado por rolagem' in n for n in labels))
            self.assertTrue(any('Conteúdo tardio observado' in n for n in labels))
            self.assertGreater(p.coleta['passos_rolagem'],0)
        finally:page.close()
    def test_interrupcao_cooperativa_da_preparacao(self):
        page=self.browser.new_page();stop=threading.Event();stop.set()
        try:
            page.set_content('<p>Conteúdo já observado</p>')
            stats=preparar(page,lambda _:None,parar=stop)
            self.assertFalse(stats['estavel']);self.assertTrue(stats['rolagem_limitada'])
        finally:page.close()
    def test_nome_baixar_nao_comprova_documento_e_ancestrais_coletados(self):
        page=self.browser.new_page()
        try:
            page.set_content('<section id="conteudo"><div data-component="canal" id="aux"><a href="https://portal-a.test/consulta">Baixar informações</a><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" alt="Ilustração canal"></div></section>')
            rows=page.evaluate(JS_EXTRAIR)['itens'];link=next(i for i in rows if i['nome']=='Baixar informações')
            self.assertEqual(link['tipo'],'Opção');self.assertEqual(link['componente_id'],'#aux');self.assertEqual(link['secao_id'],'#conteudo')
        finally:page.close()

    def test_interface_tags_relacoes_ids_e_tempos(self):
        from web import server
        from ambidiff.storage import atomic_json
        rid='20261022_120002_abcdef'
        rows=[{'id':'DIV-0001','tipo':'Imagem','elemento':'Marca auxiliar','url_presente':A,'componente_id':'#aux'},
              {'id':'DIV-0002','tipo':'Opção','elemento':'Abrir atendimento','url_presente':A,'componente_id':'#aux'}]
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)):
            atomic_json(Path(td)/f'comparacao_{rid}.json',{'divergencias':rows,'paginas':{'PRD':1,'LAB':1},'ambientes':{'PRD':A,'LAB':B},'iniciado_em':'2026-10-22T08:00:00-04:00','finalizado_em':'2026-10-22T08:00:05-04:00','duracao_segundos':5})
            client=server.app.test_client();page=self.browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            try:
                def respond(route):
                    url=route.request.url.split('http://ambidiff.test',1)[-1];r=client.get(url)
                    route.fulfill(status=r.status_code,content_type=r.content_type,body=r.data);r.close()
                page.route('http://ambidiff.test/**',respond)
                page.goto('http://ambidiff.test/',wait_until='networkidle')
                page.evaluate(f'openReport("{rid}")');page.wait_for_selector('#div-div-0001')
                self.assertIn('Duração:',page.locator('#report-summary').inner_text())
                self.assertIn('OPCAO_AUSENTE',page.locator('#div-div-0002').inner_text())
                page.locator('#smart-results').locator('..').locator('summary').first.click()
                relation=page.locator('#smart-results details').filter(has_text='Ocorrências relacionadas')
                relation.locator('summary').click();relation.get_by_role('button',name='DIV-0002',exact=True).click()
                self.assertEqual(page.locator('.result-card').count(),1);self.assertTrue(page.locator('#div-div-0002').count())
                self.assertFalse(errors)
            finally:page.close()

    def test_captura_sem_seletor_nao_comprova_ausencia_visual(self):
        from ambidiff.paired import _salvar_evidencias
        from fixtures_perf import portais_perf
        with portais_perf(1) as (bases,_),tempfile.TemporaryDirectory() as td:
            page=self.browser.new_page()
            try:
                page.goto(bases[0],wait_until='domcontentloaded')
                self.assertEqual(page.get_by_role('button',name='Canal auxiliar',exact=True).count(),1)
            finally:page.close()
            rows=[{'id':'DIV-0001','tipo':'Opção','elemento':'Canal auxiliar','presente_em':'PRD','nao_identificado_em':'LAB',
                   'url_presente':bases[0],'url_comparada':bases[1],'seletor':'#seletor-nao-identificado'}]
            _salvar_evidencias(self.browser,rows,Path(td)/'evidencias_sinteticas',threading.Event(),lambda _:None,'PRD','LAB')
            self.assertIn('não localizado',rows[0]['marcacoes']['PRD'])
            self.assertTrue((Path(td)/rows[0]['evidencias']['PRD']).is_file())
            self.assertEqual(enriquecer(rows)[0]['grau_confianca'],'possivel')

    def test_diferenca_funcional_observada_por_clique_local(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from ambidiff.functional import verificar_par
        servers=[];threads=[]
        for inert in (True,False):
            def handler(sem_acao):
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args):pass
                    def do_GET(self):
                        action='onclick="return false"' if sem_acao else ''
                        body=('<html><head><link rel="icon" href="data:,"></head><body><a id="consulta" href="/consulta" '+action+'>Consultar processo</a></body></html>').encode()
                        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                return Handler
            serv=ThreadingHTTPServer(('127.0.0.1',0),handler(inert));thread=threading.Thread(target=serv.serve_forever,daemon=True);thread.start();servers.append(serv);threads.append(thread)
        try:
            ba,bb=[f'http://127.0.0.1:{s.server_port}/' for s in servers]
            ia=item('Consultar processo',ba+'consulta',seletor='#consulta');ib=item('Consultar processo',bb+'consulta',seletor='#consulta')
            row=verificar_par(self.browser,pagina(ba),pagina(bb),ia,ib,'PRD','LAB',ba,bb,lambda _:None)
            self.assertIsNotNone(row);self.assertTrue(row['teste_funcional_executado'])
            self.assertNotEqual(row['resultado_funcional_a'],row['resultado_funcional_b'])
            self.assertEqual(enriquecer([row])[0]['tag_tecnica'],'FALHA_FUNCIONAL_VERIFICADA')
        finally:
            for server in servers:server.shutdown();server.server_close()
            for thread in threads:thread.join()

class PipelinePerfTests(unittest.TestCase):
    def test_atraso_real_justifica_releitura_e_muda_diagnostico(self):
        from ambidiff import paired
        original=paired._extrair_page;agendada=False
        def extrair(page,url,*args,**kwargs):
            nonlocal agendada
            p=original(page,url,*args,**kwargs)
            if url==A and not agendada:
                agendada=True
                page.evaluate("setTimeout(()=>{const p=document.createElement('p');p.textContent='Regra disponibilizada tardiamente';document.querySelector('main').append(p)},150)")
            return p
        a='<main><p>Atendimento</p></main>'
        b='<main><p>Atendimento</p><p>Regra disponibilizada tardiamente</p></main>'
        with patch('ambidiff.paired._extrair_page',side_effect=extrair):r=html_run(a,b,varredura_inteligente=True)
        logs=r['metricas']['releituras'];self.assertTrue(logs)
        self.assertTrue(logs[0]['adotada']);self.assertTrue(logs[0]['diagnostico_modificado'])
        self.assertGreater(logs[0]['duracao_segundos'],0)
        self.assertFalse(any('Regra disponibilizada' in d['elemento'] for d in r['divergencias']))
    def test_diferenca_estavel_nao_rele_imagem_botao_e_textos(self):
        a='<section id="aviso"><h1>Regras de atendimento</h1>'+''.join(f'<p>Regulamento institucional número {i}</p>' for i in range(8))+'</section><aside data-component="aux"><button>Canal auxiliar</button></aside>'
        b='<section id="aviso"><h1>Regras de atendimento</h1><p>Expediente encerrado</p></section>'
        r=html_run(a,b,varredura_inteligente=True)
        self.assertEqual(r['metricas']['contagens'].get('operacoes_segunda_leitura',0),0)
        self.assertTrue(any(d['elemento']=='Canal auxiliar' for d in r['divergencias']))
        self.assertEqual(r['paginas'],{'PRD':1,'LAB':1})
        self.assertEqual(r['metricas']['contagens']['preparacoes_profundas'],2)
    def test_interrupcao_preserva_tempo_diagnostico_checkpoint_e_exportacao(self):
        from ambidiff.reports import exportar
        from ambidiff.diagnostics import montar_diagnostico
        stop=threading.Event();snaps=[]
        r=html_run('<nav><a href="'+A+'seguinte">Outra seção</a></nav><p>Regra alfa</p>',
                   '<nav><a href="'+B+'seguinte">Outra seção</a></nav><p>Regra beta</p>',
                   varredura_inteligente=True,parar=stop,progresso=lambda p:stop.set() if p>0 else None,checkpoint=lambda d:snaps.append(copy.deepcopy(d)))
        self.assertEqual(r['situacao_analise'],'parcial');self.assertTrue(snaps)
        self.assertEqual(snaps[-1]['iniciado_em'],r['iniciado_em']);self.assertIsNone(snaps[-1]['finalizado_em'])
        self.assertIsNotNone(r['finalizado_em']);self.assertGreater(r['duracao_segundos'],0)
        with tempfile.TemporaryDirectory() as td:
            paths=exportar(r,Path(td),'parcial');saved=json.loads(Path(paths['json']).read_text())
            self.assertEqual(saved['iniciado_em'],r['iniciado_em']);self.assertEqual(saved['situacao_analise'],'parcial')
            self.assertIn('exportacao',saved);self.assertIn('duracao_segundos',montar_diagnostico(saved))
            self.assertIn('tag_tecnica',Path(paths['csv']).read_text(encoding='utf-8-sig'))
    def test_falha_automacao_tem_classificacao_propria(self):
        from ambidiff.diagnostics import montar_diagnostico
        r=html_run('<p>Exemplo A</p>','<p>Exemplo B</p>',varredura_inteligente=True)
        r['falhas']=[{'ambiente':'LAB','erro':'Timeout de navegação','url':B}]
        diag=montar_diagnostico(r)
        self.assertEqual(diag['falhas'][0]['grau_confianca'],'falha_automacao')
        self.assertEqual(diag['falhas'][0]['tag_tecnica'],'COLETA_INCONCLUSIVA')

    def test_redirecionamento_inicial_divergente_preserva_diagnostico(self):
        from fixtures_perf import portais_perf
        with portais_perf(1,redirecionar_lab=True) as (bases,_):
            r=executar(*bases,'PRD','LAB',threading.Event(),lambda _:None,lambda _:None,varredura_inteligente=True)
        self.assertEqual(r['paginas'],{'PRD':0,'LAB':0});self.assertEqual(r['situacao_analise'],'inconclusivo')
        self.assertIn('DESTINO_DIVERGENTE',r['divergencias'][0]['tags'])
        self.assertIsNone(r['media_segundos_por_par'])

    def test_controles_ausentes_junto_com_secao_permanecem_relacionados(self):
        a='<main><section id="servicos"><h2>Credenciamento</h2><p>Regras institucionais para habilitação</p><button>Abrir licenças</button></section></main>'
        b='<main><p>Resumo administrativo</p></main>'
        r=html_run(a,b,varredura_inteligente=True)
        data=classificar_relatorio(r);controle=next(d for d in data['divergencias'] if d['elemento']=='Abrir licenças')
        self.assertEqual(controle['classificacao'],'relevante');self.assertEqual(controle['tag_tecnica'],'OPCAO_AUSENTE')
        groups=[g for g in data['grupos_relacionados'] if controle['id'] in g['ids']]
        self.assertTrue(groups);self.assertTrue(all(not g['causa_confirmada'] for g in groups))

class RecoveryPerfTests(unittest.TestCase):
    def test_recuperacao_preserva_checkpoint_tempos_e_falha(self):
        from web import server
        from ambidiff.storage import atomic_json
        rid='20261022_120000_abcdef'
        params={'url_a':A,'url_b':B,'nome_a':'PRD','nome_b':'LAB','site_nome':'Teste','auditar_externos':False}
        snap={'site_nome':'Teste','iniciado_em':'2026-10-22T08:00:00-04:00','duracao_segundos':8.5,'finalizado_em':None,
              'ambientes':{'PRD':A,'LAB':B},'paginas':{'PRD':1,'LAB':1},'brutos':[],
              'variacoes_editoriais':[{'tipo':'Texto','elemento':'Publicação sintética'}],
              'andamento':{'etapa':'capturas','ultimo_par_processado':1},'falhas':[],'pendencias':[],
              'meta_varredura':{'PRD':{'visitadas':1,'pendentes':2}}}
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.object(server,'HISTORY_PATH',Path(td)/'historico.json'),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            checkpoint=Path(td)/f'checkpoint_{rid}.json';atomic_json(checkpoint,snap);original=checkpoint.read_bytes()
            with patch.object(server,'executar',side_effect=RuntimeError('Falha sintética de captura')):server.worker(params,rid)
            saved=json.loads((Path(td)/f'comparacao_{rid}.json').read_text())
            self.assertEqual(saved['iniciado_em'],snap['iniciado_em']);self.assertIsNotNone(saved['finalizado_em'])
            self.assertEqual(saved['duracao_no_checkpoint_segundos'],8.5)
            self.assertEqual(saved['situacao_analise'],'parcial');self.assertEqual(saved['estado_execucao'],'falha')
            self.assertEqual(checkpoint.read_bytes(),original);self.assertEqual(len(saved['registros_editoriais']),1)
    def test_falha_sem_checkpoint_tambem_tem_campos_temporais(self):
        from web import server
        rid='20261022_120001_abcdef'
        params={'url_a':A,'url_b':B,'nome_a':'PRD','nome_b':'LAB','site_nome':'Teste','auditar_externos':False}
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            with patch.object(server,'executar',side_effect=RuntimeError('Falha antes de coletar')):server.worker(params,rid)
            saved=json.loads((Path(td)/f'diagnostico_{rid}.json').read_text())
            self.assertIsNotNone(saved['iniciado_em']);self.assertIsNotNone(saved['finalizado_em']);self.assertGreaterEqual(saved['duracao_segundos'],0)
            self.assertEqual(saved['grau_confianca'],'falha_automacao')
