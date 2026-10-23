"""Regressões locais da atualização 12; nenhuma URL institucional é acessada."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from ambidiff.core import url_limpa,Item,Pagina
from ambidiff.paired import link_equivalente
from ambidiff.security import registrar,Resumos
from test_intermat import pipeline,A,B,RID


class StabilityTests(unittest.TestCase):
    def test_seguranca_resumida_sem_parametros_e_sem_mudar_contagem(self):
        grupos={};logs=[];res=Resumos()
        for n in range(2200):
            registrar(grupos,'https://www.google.com/recaptcha/api2/anchor?token=SEGREDO'+str(n),'GET','origem',A)
            res.emitir(grupos,logs.append)
        res.emitir(grupos,logs.append,final=True)
        self.assertLessEqual(len(logs),4);self.assertEqual(sum(g['quantidade'] for g in grupos.values()),2200)
        self.assertNotIn('SEGREDO',json.dumps(grupos));self.assertNotIn('?',json.dumps(grupos))
        self.assertTrue(next(iter(grupos.values()))['impacto_possivel'])
        analytics={};registrar(analytics,'https://www.google-analytics.com/g/collect?cid=privado','POST','método')
        self.assertFalse(next(iter(analytics.values()))['impacto_possivel'])
        from ambidiff.security import url_diagnostica
        self.assertEqual(url_diagnostica('https://a.test/p;jsessionid=SEGREDO/r?token=SEGREDO'),'https://a.test/p/r')
    def test_migracao_bloqueios_preserva_total_quando_exemplos_foram_limitados(self):
        from ambidiff.security import restaurar
        original={'grupo':{'categoria':'Google Analytics','dominio':'www.google-analytics.com','metodo':'POST','motivo':'método','quantidade':186,'urls':{'https://www.google-analytics.com/g/collect?cid=SEGREDO':20}}}
        novo=restaurar(original);self.assertEqual(sum(g['quantidade'] for g in novo.values()),186)
        self.assertNotIn('SEGREDO',json.dumps(novo));self.assertIn('SEGREDO',json.dumps(original))
        self.assertEqual(next(iter(novo.values()))['urls']['https://www.google-analytics.com/g/collect'],20)
        self.assertEqual(restaurar(novo),novo)
    def test_urls_invalidas_nao_sao_equivalentes_e_host_e_porta_validados(self):
        for bad in ('/relativa','javascript:void(0)','https://','https://bad host/','https://host:abc/','https://[quebrado','https://u:p@a.test/'):
            with self.subTest(url=bad):
                self.assertFalse(link_equivalente(bad,bad,A,B))
                with self.assertRaises(ValueError):url_limpa(bad)
        self.assertFalse(link_equivalente(A+'?c=1&e=2',B+'?c=2&e=2',A,B))
    def test_referencia_invalida_preserva_os_demais_pares(self):
        def ajustar(p):p.itens.append(Item('Opção','Referência inválida','Referência inválida',local='Serviços',destino='https://bad host/'))
        r,_=pipeline(n=3,ajustar=ajustar)
        self.assertEqual(r['paginas']['PRD'],3);self.assertTrue(any('URL inválida' in p['motivo'] for p in r['pendencias']))
        self.assertTrue(any('ÁUDIOS' in x['elemento'] for x in r['divergencias']))
    def test_retomada_limita_url_fatal_e_preserva_outros_ramos(self):
        snaps=[];pipeline(checkpoint=lambda d:snaps.append(copy.deepcopy(d)));base=snaps[0]['retomada']
        def ajustar(p):
            if p.url in (A,B):p.itens.append(Item('Opção','Outro ramo','Outro ramo',local='Serviços',destino=p.url+'2'))
        for tentativa in range(2):
            snaps=[]
            with self.assertRaisesRegex(RuntimeError,'closed'):pipeline(retomada=base,crash=1,checkpoint=lambda d:snaps.append(copy.deepcopy(d)),ajustar=ajustar)
            base=snaps[-1]['retomada']
        r,opened=pipeline(retomada=base,ajustar=ajustar)
        self.assertNotIn(A+'1',opened);self.assertTrue(r['falhas']);self.assertGreaterEqual(r['paginas']['PRD'],3)
    def test_recuperacao_conserva_editoriais_fila_e_erro_sem_100_porcento(self):
        from web import server
        from ambidiff.storage import atomic_json,ler_original
        snapshots=[];pipeline(checkpoint=lambda d:snapshots.append(copy.deepcopy(d)))
        snap=snapshots[-1];ed={'tipo':'Texto','elemento':'Aviso antigo','presente_em':'DES','local':'Aviso','url_presente':B}
        snap['variacoes_editoriais']=[ed];snap['registros_editoriais']=[ed]
        snap['referencias_pendentes']=[{'elemento':'Referência'}]
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.object(server,'HISTORY_PATH',Path(td)/'historico.json'),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True),patch.object(server,'executar',side_effect=RuntimeError('Falha simulada')):
            atomic_json(Path(td)/f'checkpoint_{RID}.json',snap);server.PARAR.clear()
            server.worker(dict(url_a=A,url_b=B,nome_a='PRD',nome_b='DES',site_nome='',auditar_externos=False),RID)
            r=ler_original(Path(td),RID)
            self.assertTrue(r['variacoes_dados']);self.assertEqual(r['registros_editoriais'],[ed])
            self.assertTrue(r['referencias_pendentes']);self.assertEqual(server.STATE['status'],'erro')
            self.assertIn('Falha simulada',server.STATE['erro']);self.assertLess(server.STATE['progresso'],100)
            self.assertEqual(server.STATE['andamento']['pares_pendentes'],1)

if __name__=='__main__':unittest.main()

class BrowserStabilityTests(unittest.TestCase):
    def test_analytics_nao_falha_e_recaptcha_limita_so_componente(self):
        from ambidiff.paired import executar_pareado
        from ambidiff.relevance import preparar
        for captcha in (False,True):
            def contextos(ca,cb):
                for ctx,base in ((ca,A),(cb,B)):
                    extra=('<nav><a href="'+base+'audio.pdf">ÁUDIOS</a></nav>' if base==A else '')
                    if captcha:
                        extra+='<form id="form"><div class="g-recaptcha"><iframe src="https://www.google.com/recaptcha/api2/anchor?token=SEGREDO"></iframe></div>'+('<button type="button">Consultar serviço</button>' if base==A else '')+'</form>'
                    else:extra='<script>fetch("https://www.google-analytics.com/g/collect?cid=SEGREDO",{method:"POST",mode:"no-cors",body:"x"})</script>'
                    def responder(text):
                        return lambda route:route.fulfill(content_type='text/html; charset=utf-8',body=text)
                    ctx.route(base+'**',responder('<h1>Portal</h1>'+extra))
            r=executar_pareado(A,B,'PRD','DES',threading.Event(),lambda _:None,lambda _:None,_preparar_contextos=contextos)
            self.assertTrue(r['bloqueios_seguranca']);self.assertNotIn('SEGREDO',json.dumps(r['bloqueios_seguranca']))
            if not captcha:self.assertEqual(r['situacao_analise'],'concluido');self.assertFalse(r['divergencias'])
            else:
                rows=preparar(r)['divergencias']
                self.assertTrue(any(d['elemento']=='ÁUDIOS' and d['classificacao']=='relevante' for d in rows))
                self.assertTrue(any(d['elemento']=='Consultar serviço' and d['classificacao']=='inconclusivo' for d in rows))

class ResourceTests(unittest.TestCase):
    def test_link_de_menu_para_midia_nao_oculta_destino_diferente(self):
        def ajustar(p):
            destino=A+'manual.jpg' if p.url.startswith(A) else B+'outro.jpg'
            p.itens.append(Item('Opção','Arquivo da unidade','Arquivo da unidade',local='Menu',
                destino=destino,natureza='estrutura',posicao='Menu de navegação'))
        r,opened=pipeline(n=2,ajustar=ajustar)
        self.assertTrue(any(d['elemento']=='Arquivo da unidade' and d['tipo']=='Redirecionamento' for d in r['divergencias']))
        self.assertFalse(any('.jpg' in u for u in opened))

    def test_pdf_em_um_lado_e_imagem_no_outro_preserva_divergencia_tipo(self):
        from ambidiff.documents import Documentos
        from ambidiff.smart import Metricas
        from test_smart import Response,pdf
        from types import SimpleNamespace
        respostas=iter([Response(200,**{'Content-Type':'image/jpeg'}),pdf()])
        d=Documentos(Metricas(),threading.Event(),permitir_range=False)
        d.opener=SimpleNamespace(open=lambda *a,**k:next(respostas))
        r=d.comparar(Item('Documento','Portaria PDF','Portaria PDF',destino=A+'manual.pdf'),Item('Documento','Portaria PDF','Portaria PDF',destino=B+'manual.pdf'),A,B)
        self.assertTrue(r['divergencia_tipo_observada']);self.assertIn('tipo',r['classificacao'])

    def test_documentos_midias_auxiliares_e_sem_extensao(self):
        from ambidiff.resources import classificar
        for url,contexto,mime,esperado in [('/documents/d/p/manual.pdf','','','documento'),('/documents/d/p/capa.avif','','','midia'),('/documents/d/p/capa','midia','','midia'),('/documents/d/p/manual','','application/pdf','documento'),('/documents/d/p/preview','','image/jpeg','midia'),('/documents/d/p/incerto','','','inconclusivo'),('/assets/app.js','','','auxiliar'),('/servicos','','','navegacao')]:
            self.assertEqual(classificar(A.rstrip('/')+url,contexto,mime),esperado)

class ExportTests(unittest.TestCase):
    def preparar(self,root):
        from ambidiff.storage import atomic_json
        from test_next import missing_rows
        rows=missing_rows()+[{'id':'DIV-0003','tipo':'Opção','elemento':'Outra diferença','local':'Serviços','descricao':'Não selecionada'}]
        dados={'id':RID,'versao':'1.5','site_nome':'SEFAZ sintética','paginas':{'PRD':1,'DES':1},'ambientes':{'PRD':A,'DES':B},'divergencias':rows,
            'metricas':{'contagens':{'pares_comparados':1},'releituras':[{'dom':'MARCADOR_FORA_DA_SELECAO'}]},
            'sinais_desatualizacao':[{'descricao':'MARCADOR_FORA_DA_SELECAO'}]}
        atomic_json(root/f'comparacao_{RID}.json',dados);return dados
    def test_selecao_persistente_grupo_exclusao_e_csv_sem_duplicar(self):
        from web import server
        from ambidiff.storage import selecionar,preparar_relatorio,excluir_div
        import csv,io
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            root=Path(td);self.preparar(root);before=(root/f'comparacao_{RID}.json').read_bytes();server.STATE['status']='pronto'
            selecionar(root,RID,'DIV-0001',True)
            self.assertEqual(preparar_relatorio(root,RID)['ids_selecionados'],['DIV-0001','DIV-0002'])
            self.assertFalse((root/f'revisoes_{RID}.json').exists())
            client=server.app.test_client();r=client.get(f'/download/{RID}/csv?selecionadas=1')
            self.assertEqual(r.status_code,200);rows=list(csv.DictReader(io.StringIO(r.data.decode('utf-8-sig')),delimiter=';'));r.close()
            self.assertEqual(len(rows),1);self.assertIn('DIV-0002',rows[0]['ids_agrupados']);self.assertNotIn('Outra diferença',str(rows))
            excluir_div(root,RID,'DIV-0002');self.assertEqual(preparar_relatorio(root,RID)['ids_selecionados'],['DIV-0001'])
            self.assertEqual((root/f'comparacao_{RID}.json').read_bytes(),before)
            resp=client.get(f'/download/{RID}/json?selecionadas=1');data=resp.get_json();resp.close()
            self.assertEqual(data['escopo_exportacao'],'Somente DIVs selecionadas');self.assertEqual([d['id'] for d in data['divergencias']],['DIV-0001'])
            self.assertNotIn('MARCADOR_FORA_DA_SELECAO',json.dumps(data));self.assertEqual(data['ids_selecionados'],['DIV-0001'])
    def test_id_longo_gerado_em_varredura_extensa_persiste(self):
        from ambidiff.storage import atomic_json,selecionar,preparar_relatorio
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);atomic_json(root/f'comparacao_{RID}.json',{'divergencias':[{'id':'DIV-100000','tipo':'Texto','elemento':'Registro extenso'}]})
            selecionar(root,RID,'DIV-100000',True)
            self.assertEqual(preparar_relatorio(root,RID)['ids_selecionados'],['DIV-100000'])
    def test_nomes_windows_e_pdf_html_portateis_com_evidencia_local(self):
        from web import server
        from ambidiff.storage import selecionar,atomic_json
        from ambidiff.exports import nome_amigavel
        import base64,shutil,subprocess
        self.assertTrue(nome_amigavel('CON','csv','selecionadas',RID).startswith('Portal_CON_'))
        self.assertNotIn('/',nome_amigavel('Órgão / nome: * ?','html','completo',RID))
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True):
            root=Path(td);data=self.preparar(root);server.STATE['status']='pronto'
            ev=root/f'evidencias_{RID}';ev.mkdir();image=ev/'DIV-0003_PRD.png'
            image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j8YQAAAAASUVORK5CYII='))
            data['divergencias'][2]['evidencias']={'PRD':ev.name+'/'+image.name};atomic_json(root/f'comparacao_{RID}.json',data)
            selecionar(root,RID,'DIV-0003',True);client=server.app.test_client()
            html=client.get(f'/download/{RID}/html?selecionadas=1');self.assertEqual(html.status_code,200)
            self.assertIn('data:image/png;base64,',html.data.decode());self.assertNotIn('Ato 002',html.data.decode());self.assertIn('SEFAZ_sintetica_DIVs_Selecionadas',html.headers['Content-Disposition']);html.close()
            pdf=client.get(f'/download/{RID}/pdf?selecionadas=1');self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF-'))
            self.assertIn(b'/Subtype /Image',pdf.data)
            if shutil.which('pdftotext'):
                f=root/'validacao.pdf';f.write_bytes(pdf.data)
                text=subprocess.check_output(['pdftotext',str(f),'-'],text=True)
                self.assertIn('DIV-0003',text);self.assertNotIn('DIV-0001',text)
            pdf.close()
            (ev/'DIV-0002_PRD.png').write_bytes(image.read_bytes())
            data['divergencias'][1]['evidencias']={'PRD':ev.name+'/DIV-0002_PRD.png'};atomic_json(root/f'comparacao_{RID}.json',data)
            selecionar(root,RID,'DIV-0003',False);selecionar(root,RID,'DIV-0001',True)
            group=client.get(f'/download/{RID}/html?selecionadas=1')
            self.assertIn('Captura de PRD para DIV-0002',group.data.decode());self.assertIn('data:image/png;base64,',group.data.decode());group.close()

class BrowserExportTests(unittest.TestCase):
    def test_gaveta_selecao_f5_e_save_picker_sem_confirmar_defeito(self):
        from playwright.sync_api import sync_playwright
        from test_smart import navegador
        from web import server
        from ambidiff.storage import preparar_relatorio
        with tempfile.TemporaryDirectory() as td,patch.object(server,'PASTA',Path(td)),patch.dict(server.STATE,copy.deepcopy(server.STATE),clear=True),sync_playwright() as pw:
            root=Path(td);ExportTests().preparar(root);server.STATE['status']='pronto';client=server.app.test_client();browser=navegador(pw);p=browser.new_page()
            def responder(route):
                req=route.request;url=req.url.split('http://ambidiff.test',1)[-1]
                if url.startswith('/api/status'):route.fulfill(content_type='application/json',body='{"status":"pronto","progresso":0}');return
                res=client.open(url,method=req.method,data=req.post_data,content_type='application/json');route.fulfill(status=res.status_code,content_type=res.content_type,headers={'Content-Disposition':res.headers.get('Content-Disposition','')},body=res.data);res.close()
            try:
                p.route('http://ambidiff.test/**',responder);p.goto('http://ambidiff.test/',wait_until='networkidle')
                self.assertEqual(p.locator('#site-nome').count(),0);self.assertFalse(p.locator('.advanced-options').evaluate('e=>e.open'))
                self.assertFalse(p.locator('#auditar-externos').is_checked());self.assertFalse(p.locator('#verificar-cliques').is_checked())
                p.evaluate('(id)=>openReport(id)',RID);p.locator('input[aria-label="Selecionar DIV-0001 para exportação"]').check()
                p.wait_for_function('currentReport.ids_selecionados.length===2');p.reload(wait_until='networkidle');p.evaluate('(id)=>openReport(id)',RID)
                self.assertTrue(p.locator('input[aria-label="Selecionar DIV-0001 para exportação"]').is_checked())
                p.evaluate("""() => {window.showSaveFilePicker=async options=>{window.saveOptions=options;return {getFile:async()=>({size:0}),createWritable:async()=>({write:async blob=>{window.savedText=await blob.text()},close:async()=>{},abort:async()=>{}})}}}""")
                p.locator('[data-export="csv"]').click();p.wait_for_function('window.savedText')
                self.assertNotIn('Outra diferença',p.evaluate('window.savedText'));self.assertEqual(p.evaluate('window.saveOptions.id'),'ambidiff-exportacoes')
                self.assertFalse(preparar_relatorio(root,RID)['revisoes_manuais'])
                denied=p.evaluate("""async()=>{window.confirm=()=>false;window.wroteExisting=false;window.showSaveFilePicker=async()=>({getFile:async()=>({size:20}),createWritable:async()=>{window.wroteExisting=true}});await downloadExport(document.querySelector('[data-export=csv]'));return !window.wroteExisting;}""")
                self.assertTrue(denied)
                p.evaluate('window.showSaveFilePicker=undefined')
                with p.expect_download() as download:p.locator('[data-export=csv]').click()
                self.assertIn('DIVs_Selecionadas',download.value.suggested_filename)

            finally:browser.close()

class DeduplicationTests(unittest.TestCase):
    def test_repetidos_em_menus_preservam_rotulos_e_uma_visita_por_par(self):
        def ajustar(pag):
            base=A if pag.url.startswith(A) else B
            for n in range(12):pag.itens.append(Item('Opção','Opção '+str(n),'Opção '+str(n),local='Menu '+str(n),destino=base))
        r,opened=pipeline(n=8,ajustar=ajustar,ciclo=True)
        self.assertEqual(len(opened),16);self.assertEqual(len(set(opened)),16)
        m=r['metricas']['contagens'];self.assertGreater(m['urls_duplicadas'],80);self.assertGreater(m['links_encontrados'],180)
        self.assertEqual(m['paginas_reutilizadas'],0);self.assertTrue(any('ÁUDIOS' in d['elemento'] for d in r['divergencias']))
    def test_cache_normalizacao_exata_preserva_queries_significativas(self):
        from ambidiff.core import _url_limpa
        _url_limpa.cache_clear();a=url_limpa(A+'?c=1&e=2');hits=_url_limpa.cache_info().hits
        self.assertEqual(url_limpa(A+'?c=1&e=2'),a);self.assertGreater(_url_limpa.cache_info().hits,hits)
        self.assertNotEqual(url_limpa(A+'?c=2&e=2'),a)
