"""Regressões independentes dos PRs USEIA/progresso; somente fixtures locais."""
import copy
from email.message import Message
import json
from pathlib import Path
import tempfile
import threading
import unittest
import shutil
from unittest.mock import patch

from ambidiff.core import Item,Pagina
from ambidiff.smart import Inteligencia,Metricas
from ambidiff.documents import Documentos,MAX_BYTES
from ambidiff.paired import executar_pareado,e_arquivo
from ambidiff.functional import verificar_par
from ambidiff.reports import exportar
from ambidiff.diagnostics import montar_diagnostico
from fixtures_smart import portais

A='https://prd.test/';B='https://des.test/'


def navegador(p):
    try:return p.chromium.launch(headless=True)
    except Exception:
        executavel=shutil.which('chromium') or shutil.which('chromium-browser')
        if not executavel:raise
        return p.chromium.launch(executable_path=executavel,headless=True,args=['--no-sandbox'])


def item(nome='Início',destino=A,**kw):
    return Item('Opção',nome,nome,local=kw.pop('local','Serviços'),destino=destino,
                funcao=kw.pop('funcao','link'),estrutura=kw.pop('estrutura','A|estatico'),**kw)


class EquivalenceTests(unittest.TestCase):
    def comparar(self,a,b):
        motor=Inteligencia(Metricas())
        comps=motor.comparar(a,b,Pagina(A,'','Portal',a),Pagina(B,'','Portal',b),'PRD','DES',A,B)
        return motor,comps

    def test_equivalentes_em_posicoes_e_seletores_distintos(self):
        m,c=self.comparar([item(seletor='#menu > a',posicao='Menu lateral')],
                         [item(destino=B,seletor='section > a',posicao='Conteúdo central')])
        self.assertEqual(c,[]);self.assertEqual(len(m.equivalencias),1)
        self.assertIn('Não comprovado',m.equivalencias[0]['funcionamento'])

    def test_menu_exclusivo_audios_nao_desaparece_com_outros_equivalentes(self):
        m,c=self.comparar([item(),item('ÁUDIOS',A+'audios')],[item(destino=B)])
        self.assertEqual([x['elemento'] for x in c],['ÁUDIOS'])
        self.assertEqual(len(m.equivalencias),1)

    def test_texto_igual_nao_comprova_funcao_ou_destino(self):
        m,c=self.comparar([item()],[item(destino=B+'outra')])
        self.assertFalse(m.equivalencias);self.assertTrue(m.inconclusivos)
        m,c=self.comparar([item()],[item(destino=B,funcao='button',estrutura='BUTTON|estatico')])
        self.assertFalse(m.equivalencias);self.assertEqual(c[0]['tipo'],'Função')
        m,c=self.comparar([item(estrutura='A|dinamico')],[item(destino=B,estrutura='A|dinamico')])
        self.assertFalse(m.equivalencias)
        with patch('ambidiff.functional._um_clique',side_effect=['navegou','sem_navegacao_observada']):
            diff=verificar_par(None,Pagina(A,'','Portal',[]),Pagina(B,'','Portal',[]),
                              item(),item(destino=B),'PRD','DES',A,B,lambda _:None)
        self.assertEqual(diff['tipo'],'Clique')

    def test_reuso_exige_nova_evidencia_e_nao_oculta_alteracao(self):
        m=Inteligencia(Metricas());pa=Pagina(A,'','P',[]);pb=Pagina(B,'','P',[])
        for _ in range(2):m.comparar([item()],[item(destino=B)],pa,pb,'PRD','DES',A,B)
        self.assertEqual(m.metricas.contagens['verificacoes_reaproveitadas'],1)
        c=m.comparar([item(),item('ÁUDIOS',A+'audios')],[item(destino=B)],pa,pb,'PRD','DES',A,B)
        self.assertTrue(any(x['elemento']=='ÁUDIOS' for x in c))

    def test_mesmo_rotulo_em_contexto_distinto_nao_oculta_diferenca(self):
        m,c=self.comparar([item(local='Menu principal')],[item(destino=B,local='Rodapé')])
        self.assertFalse(m.equivalencias)
        self.assertTrue(any(x['tipo']=='Contexto' for x in c))


class Response:
    def __init__(self,status=200,**headers):
        self.code=status;self.headers=Message();self.closed=False
        for k,v in headers.items():self.headers[k]=v
    def close(self):self.closed=True
    def read(self,*args):raise AssertionError('O corpo do documento não deve ser lido')


def pdf(nome='manual-rede.pdf',status=200):
    return Response(status,**{'Content-Type':'application/pdf',
                    'Content-Disposition':f'attachment; filename="{nome}"','Content-Length':'90000000','Cache-Control':'max-age=60'})


class DocumentTests(unittest.TestCase):
    def motor(self,respostas):
        d=Documentos(Metricas(),threading.Event());chamadas=[]
        def abrir(req,timeout):
            chamadas.append(req)
            resposta=respostas.pop(0)
            if isinstance(resposta,Exception):raise resposta
            return resposta
        d.opener=type('Opener',(),{'open':staticmethod(abrir)})()
        return d,chamadas

    def par(self,d):return d.comparar(item('Manual rede',A+'manual.pdf'),item('Manual rede',B+'manual.pdf'),A,B)

    def test_acessivel_metadados_compativeis_sem_download(self):
        ra,rb=pdf(),pdf();d,c=self.motor([ra,rb]);r=self.par(d)
        self.assertEqual(r['classificacao'],'Documento acessível e provavelmente equivalente')
        self.assertTrue(all(x.get_method()=='HEAD' for x in c))
        self.assertTrue(ra.closed and rb.closed)
        self.assertEqual(r['a']['bytes_lidos'],0)
        self.assertIn('não comprovam',r['nota'])

    def test_indisponivel_em_apenas_um_ambiente(self):
        d,_=self.motor([pdf(status=404),pdf()])
        self.assertEqual(self.par(d)['classificacao'],'Falha de acesso confirmada em um ambiente')

    def test_finalidade_ou_tipo_diferente(self):
        d,_=self.motor([pdf('manual-saude.pdf'),pdf('manual-tributos.pdf')])
        self.assertIn('Possível divergência',self.par(d)['classificacao'])
        d,_=self.motor([pdf(),Response(200,**{'Content-Type':'application/msword','Content-Disposition':'attachment; filename="manual-rede.doc"'})])
        self.assertIn('Possível divergência',self.par(d)['classificacao'])

    def test_liferay_sem_extensao(self):
        self.assertTrue(e_arquivo(A+'documents/d/cge/portaria-76'))
        d,c=self.motor([pdf(),pdf()])
        r=d.comparar(item('Manual rede',A+'documents/d/cge/manual'),item('Manual rede',B+'manual.pdf'),A,B)
        self.assertIn('provavelmente equivalente',r['classificacao'])
        self.assertEqual(len(c),2)

    def test_head_sem_suporte_range_limitado_e_nenhuma_leitura(self):
        parcial=Response(206,**{'Content-Type':'application/pdf','Content-Range':'bytes 0-0/90000000',
                              'Content-Disposition':'attachment; filename="manual-rede.pdf"'})
        d,c=self.motor([Response(405),parcial,pdf()]);r=self.par(d)
        self.assertEqual([x.get_method() for x in c],['HEAD','GET','HEAD'])
        self.assertEqual(c[1].get_header('Range'),'bytes=0-0')
        self.assertEqual(MAX_BYTES,1)
        self.assertIn('provavelmente equivalente',r['classificacao'])
        self.assertTrue(parcial.closed)

    def test_range_ignorado_aborta_sem_ler_arquivo_grande(self):
        grande=pdf();d,c=self.motor([Response(501),grande,pdf()]);r=self.par(d)
        self.assertEqual(r['classificacao'],'Verificação inconclusiva')
        self.assertIn('corpo não lido',r['a']['motivo'])
        self.assertTrue(grande.closed)

    def test_redirect_permitido_externo_bloqueado_e_timeout(self):
        d,c=self.motor([Response(302,Location='/novo.pdf'),pdf(),pdf()])
        self.assertIn('provavelmente equivalente',self.par(d)['classificacao'])
        self.assertEqual(c[1].full_url,A+'novo.pdf')
        d,c=self.motor([Response(302,Location='https://externo.test/segredo.pdf'),pdf()])
        r=self.par(d);self.assertEqual(len(c),2)
        self.assertIn('não acessado',r['a']['motivo'])
        self.assertFalse(any('externo.test' in x.full_url for x in c))
        d,c=self.motor([TimeoutError('tempo esgotado'),pdf()])
        self.assertEqual(self.par(d)['classificacao'],'Verificação inconclusiva')

    def test_limites_redirect_requisicoes_e_deduplicacao(self):
        d,c=self.motor([pdf(),pdf()]);self.par(d);self.par(d)
        self.assertEqual(len(c),2);self.assertEqual(d.metricas.contagens['documentos_reaproveitados'],1)
        d,c=self.motor([Response(302,Location='/outro.pdf') for _ in range(4)]+[pdf()])
        self.assertEqual(self.par(d)['classificacao'],'Verificação inconclusiva')
        self.assertEqual(len(c),5)
        d,c=self.motor([pdf()])
        with patch('ambidiff.documents.MAX_REQUISICOES',1):
            self.assertEqual(self.par(d)['classificacao'],'Verificação inconclusiva')
        self.assertEqual(len(c),1)

    def test_cache_sem_frescor_exige_revalidacao_e_preserva_mudanca(self):
        respostas=[pdf(),pdf(),pdf('manual-saude.pdf'),pdf()]
        for r in respostas:r.headers.replace_header('Cache-Control','no-cache')
        d,c=self.motor(respostas)
        self.assertIn('provavelmente equivalente',self.par(d)['classificacao'])
        self.assertIn('Possível divergência',self.par(d)['classificacao'])
        self.assertEqual(len(c),4)

    def test_destino_ou_rotulo_com_indicio_de_acao_nao_e_acessado(self):
        d,c=self.motor([])
        self.assertEqual(d.conferir(A+'delete.pdf',A)['situacao'],'inconclusivo')
        r=d.comparar(item('Excluir documento',A+'manual.pdf'),item('Excluir documento',B+'manual.pdf'),A,B)
        self.assertEqual(r['classificacao'],'Verificação inconclusiva')
        self.assertFalse(c)

    def test_transporte_http_real_range_e_redirect_nao_automatico(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        pedidos=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_HEAD(self):
                pedidos.append(('HEAD',self.path))
                self.send_response(302 if self.path=='/redirect' else 405)
                if self.path=='/redirect':self.send_header('Location','http://externo.test/arquivo.pdf')
                self.end_headers()
            def do_GET(self):
                pedidos.append(('GET',self.path,self.headers.get('Range')))
                self.send_response(206);self.send_header('Content-Range','bytes 0-0/90000000')
                self.send_header('Content-Type','application/pdf');self.send_header('Content-Length','1')
                self.end_headers()
                try:self.wfile.write(b'x')
                except (BrokenPipeError,ConnectionResetError):pass
        serv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=serv.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{serv.server_port}/'
        try:
            d=Documentos(Metricas(),threading.Event())
            r=d.conferir(base+'arquivo.pdf',base)
            self.assertEqual(r['situacao'],'acessivel');self.assertEqual(r['bytes_lidos'],0)
            self.assertEqual(pedidos[-1],('GET','/arquivo.pdf','bytes=0-0'))
            r=d.conferir(base+'redirect',base)
            self.assertIn('não acessado',r['motivo'])
            self.assertEqual(pedidos[-1],('HEAD','/redirect'))
        finally:serv.shutdown();serv.server_close();thread.join()


class SmartIntegrationTests(unittest.TestCase):
    def executar(self,bases,**kw):
        with patch('ambidiff.paired._preparar_conteudo',return_value={'estavel':True,'rolagem_limitada':False}):
            return executar_pareado(*bases,'PRD','DES',threading.Event(),lambda _:None,lambda _:None,**kw)

    def test_noticias_dados_defasados_reuso_e_modo_atual(self):
        with portais(4) as (bases,requisicoes):
            atual=self.executar(bases,ambiente_desatualizado='DES',estrategia='profunda',orcamento_minutos=0)
            otimizado=self.executar(bases,ambiente_desatualizado='DES',varredura_inteligente=True,estrategia='profunda',orcamento_minutos=0)
        self.assertEqual(atual['paginas'],otimizado['paginas'])
        self.assertEqual(atual['divergencias'],[])
        self.assertEqual(otimizado['divergencias'],[])
        self.assertTrue(otimizado['variacoes_dados'])
        self.assertTrue(otimizado['registros_editoriais'])
        self.assertEqual(atual['modo_varredura'],'atual')
        self.assertEqual(otimizado['situacao_analise'],'parcial')
        self.assertFalse(otimizado['completo']['PRD'])
        self.assertEqual(otimizado['otimizacao']['quantidade_paginas_sem_inspecao_profunda'],4)
        self.assertGreater(otimizado['metricas']['contagens']['verificacoes_reaproveitadas'],0)
        self.assertLess(otimizado['metricas']['contagens']['operacoes_preparacao'],atual['metricas']['contagens']['operacoes_preparacao'])
        self.assertFalse(any(m=='GET' and p=='/manual.pdf' for _,m,p in requisicoes))

    def test_noticias_com_diferenca_estrutural_nao_reutilizam_template(self):
        with portais(3,estrutura_diferente=True) as (bases,_):
            r=self.executar(bases,ambiente_desatualizado='DES',varredura_inteligente=True)
        self.assertTrue(any(d['tipo']=='Estrutura editorial' for d in r['divergencias']))
        self.assertFalse(any(x['categoria']=='Notícia de template repetido' for x in r['otimizacao']['inspecoes_profundas_omitidas']))

    def test_cge_audios_links_divergentes_e_interrupcao_preservam_parcial(self):
        event=threading.Event();snapshots=[]
        def abrir(page,url):
            host='prd.test' if 'prd.test' in url else 'des.test'
            exclusivo='<a href="https://prd.test/w/audios">ÁUDIOS</a>' if host=='prd.test' else ''
            destino='/destino-a' if host=='prd.test' else '/destino-b'
            page.set_content('<main><h1>CGE sintética</h1><nav>'+exclusivo+
                '<a href="https://'+host+destino+'">Consultar</a><a href="https://'+host+'/seguinte">Seguinte</a></nav></main>')
            return type('R',(),{'status':200,'url':url})()
        def log(msg):
            if msg.startswith('[PRD/DES]'):event.set()
        with patch('ambidiff.paired._abrir',side_effect=abrir), \
             patch('ambidiff.paired._preparar_conteudo',return_value={'estavel':True,'rolagem_limitada':False}):
            r=executar_pareado(A,B,'PRD','DES',event,log,lambda _:None,
                ambiente_desatualizado='DES',varredura_inteligente=True,checkpoint=lambda d:snapshots.append(copy.deepcopy(d)))
        self.assertEqual(r['situacao_analise'],'parcial')
        self.assertTrue(any(d['elemento']=='ÁUDIOS' for d in r['divergencias']))
        self.assertTrue(any(d['tipo']=='Redirecionamento' for d in r['divergencias']))
        self.assertTrue(snapshots[-1]['brutos'])
        self.assertEqual(snapshots[-1]['modo_varredura'],'inteligente')
        self.assertEqual(montar_diagnostico(r)['metricas'],r['metricas'])
        with tempfile.TemporaryDirectory() as d:
            files=exportar(r,Path(d),'teste')
            self.assertEqual(json.loads(Path(files['json']).read_text())['otimizacao'],r['otimizacao'])
            self.assertIn('Metadados não comprovam',Path(files['html']).read_text())

    def test_secao_noticias_ausente_nao_e_equivalente(self):
        def abrir(page,url):
            page.set_content('<main><section><h2>Notícias</h2><p>Publicações</p></section></main>' if url==A else '<main><h2>Serviços</h2></main>')
            return type('R',(),{'status':200,'url':url})()
        with patch('ambidiff.paired._abrir',side_effect=abrir):
            r=self.executar((A,B),ambiente_desatualizado='DES',varredura_inteligente=True)
        self.assertTrue(any(d['tipo']=='Estrutura editorial' for d in r['divergencias']))

    def test_template_com_script_lazy_ou_acao_nao_dispensa_preparacao(self):
        from playwright.sync_api import sync_playwright
        from ambidiff.smart import JS_TEMPLATE
        html='<main><article><h1>Notícia</h1><time datetime="2026-10-01">Data</time><p>Texto</p>{}</article></main>'
        with sync_playwright() as p:
            browser=navegador(p)
            try:
                page=browser.new_page()
                page.route(A+'w/teste',lambda route:route.fulfill(status=200,content_type='text/html',body=html.format('')))
                page.goto(A+'w/teste')
                self.assertTrue(page.evaluate(JS_TEMPLATE,A)['elegivel'])
                for extra in ('<script>setTimeout(()=>{},1000)</script>','<img loading="lazy">','<a href="/x" onclick="return false">Abrir</a>'):
                    page.set_content(html.format(extra))
                    self.assertFalse(page.evaluate(JS_TEMPLATE,A)['elegivel'])
            finally:browser.close()

    def test_interface_api_e_relatorios_anteriores(self):
        from playwright.sync_api import sync_playwright
        from web import server
        with patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            server.STATE.update(status='pronto',ultimo_id=None)
            client=server.app.test_client();enviados=[]
            with sync_playwright() as p:
                browser=navegador(p)
                try:
                    page=browser.new_page();erros=[];page.on('pageerror',lambda ex:erros.append(str(ex)))
                    def responder(route):
                        req=route.request;path=req.url.split('http://ambidiff.test',1)[-1]
                        if path=='/api/comparar':
                            enviados.append(req.post_data_json);route.fulfill(status=200,content_type='application/json',body='{"ok":true}')
                        else:
                            res=client.get(path)
                            route.fulfill(status=res.status_code,content_type=res.content_type,body=res.data);res.close()
                    page.route('http://ambidiff.test/**',responder)
                    page.goto('http://ambidiff.test/',wait_until='networkidle')
                    page.locator('[data-section="comparar"]').click()
                    self.assertEqual(page.locator('#varredura-inteligente,#estrategia,#orcamento-minutos').count(),0)
                    page.locator('details.advanced-options > summary').click()
                    page.locator('#url-a').fill(A);page.locator('#url-b').fill(B)
                    page.locator('#run-button').click();page.wait_for_timeout(200)
                    self.assertTrue(enviados[0]['varredura_inteligente'])
                    page.evaluate('smartResults({divergencias:[]})')
                    self.assertIn('Modo: atual',page.locator('#smart-results').inner_text())
                    self.assertFalse(erros)
                finally:browser.close()
            with patch('web.server.threading.Thread') as worker:
                self.assertEqual(client.post('/api/comparar',json={'url_a':A,'url_b':B,'varredura_inteligente':True}).status_code,200)
                self.assertTrue(worker.call_args.kwargs['args'][0]['varredura_inteligente'])


if __name__=='__main__':unittest.main()
