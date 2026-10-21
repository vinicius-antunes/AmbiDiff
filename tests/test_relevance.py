"""Cenários sintéticos; nomes históricos não controlam a classificação."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ambidiff.relevance import preparar, classificar, SVG
from ambidiff.reports import exportar
from ambidiff.storage import atomic_json, preparar_relatorio, reclassificar

RID='20261021_120000_abcdef'

def svg(**kw):
    return dict({'id':'DIV-0099','tipo':'Ícone','elemento':'Consultar','situacao':SVG,
                 'assinatura_a':'M0 0','assinatura_b':'M1 1','url_presente':'https://a.test/um'},**kw)

def report(rows):return {'id':RID,'divergencias':rows,'ambientes':{'PRD':'https://a.test/','DES':'https://b.test/'},'paginas':{},'variacoes_dados':[]}

class RelevanceTests(unittest.TestCase):
    def test_svg_somente_tecnico_e_id_independente(self):
        for ident in ('DIV-0001','DIV-0044'):
            row=svg(id=ident)
            self.assertEqual(classificar(row)[0],'baixa')
            self.assertIn('não verificada',classificar(row)[1])
    def test_excecoes_de_impacto(self):
        for field in ('impacto_visual_confirmado','falha_funcional','problema_acessibilidade','diferenca_estrutural'):
            self.assertEqual(classificar(svg(**{field:True}))[0],'relevante')
        self.assertEqual(classificar({'tipo':'Ícone','situacao':'Não identificado','elemento':'Consultar'})[0],'relevante')
        self.assertEqual(classificar({'tipo':'Botão','elemento':'Entrar','situacao':'Não identificado'})[0],'relevante')
    def test_institucional_audios_documentos_preservados(self):
        for modo in ('atual','inteligente'):
            rows=[{'id':f'DIV-{i:04}','tipo':tipo,'elemento':nome,'destino_a':'https://a.test/a.pdf','destino_b':'https://b.test/b.pdf'} for i,(tipo,nome) in enumerate([
                ('Opção','ÁUDIOS'),('Texto','Aviso institucional: atendimento suspenso'),('Texto','Contribuintes: prazo alterado'),('Redirecionamento','Manual de orientação'),('Opção','Messenger institucional')],1)]
            data=report(rows);data['modo_varredura']=modo
            self.assertTrue(all(r['classificacao']=='relevante' for r in preparar(data)['divergencias']))
    def test_messenger_estrito_agrupamento_localizacoes(self):
        rows=[{'id':f'DIV-{i:04}','tipo':'Redirecionamento','elemento':'Messenger','destino_a':'https://m.me/example','destino_b':'https://m.me/example','url_presente':f'https://a.test/{i}'} for i in (1,2)]
        original=copy.deepcopy(rows);data=preparar(report(rows));group=data['divergencias'][0]
        self.assertEqual(len(data['divergencias']),1);self.assertEqual(group['classificacao'],'baixa')
        self.assertEqual(len(group['ocorrencias']),2);self.assertEqual(len(group['registros_agrupados']),2)
        self.assertEqual(rows,original)
        functional=dict(rows[0],tipo='Clique')
        self.assertEqual(classificar(functional)[0],'relevante')
        missing=dict(rows[0],tipo='Opção')
        self.assertEqual(classificar(missing)[0],'relevante')
        self.assertEqual(preparar(data),data)
        rows[1]['destino_b']='https://m.me/outro'
        self.assertEqual(classificar(rows[1])[0],'relevante')
    def test_compartilhamento_somente_origem(self):
        data=report([]);env=data['ambientes']
        r={'tipo':'Redirecionamento','destino_a':'https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fa.test%2Faviso','destino_b':'https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fb.test%2Faviso'}
        self.assertEqual(classificar(r,env)[0],'baixa')
        r['destino_b']+='2';self.assertEqual(classificar(r,env)[0],'relevante')
        r['destino_b']=r['destino_a'].replace('a.test','evil.test');self.assertEqual(classificar(r,env)[0],'relevante')
    def test_inconclusivo_editorial_sem_inferir_por_nome(self):
        self.assertEqual(classificar({'tipo':'Contexto'})[0],'inconclusivo')
        self.assertEqual(classificar({'tipo':'Texto','elemento':'Notícias institucionais'})[0],'relevante')
        data=report([]);data['variacoes_dados']=[{'categoria':'Notícias','exemplos':[{'elemento':'Publicação sintética'}]}]
        self.assertEqual(preparar(data)['editoriais_preservados'],data['variacoes_dados'])
    def test_reclassificacao_preserva_original_e_grupos(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/f'comparacao_{RID}.json';atomic_json(path,report([svg()]))
            original=path.read_bytes()
            out=reclassificar(root,RID,'DIV-0099','relevante')
            self.assertEqual(out['divergencias'][0]['classificacao'],'relevante')
            self.assertEqual(out['divergencias'][0]['classificacao_automatica'],'baixa')
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(preparar(out)['divergencias'][0]['classificacao'],'relevante')
            self.assertEqual(reclassificar(root,RID,'DIV-0099','automatica')['divergencias'][0]['classificacao'],'baixa')
            with self.assertRaises(ValueError):reclassificar(root,RID,'DIV-0099','invalid')
    def test_exportacoes_principal_completo_json_html_csv(self):
        from ambidiff.diagnostics import montar_diagnostico
        data=report([svg(),{'id':'DIV-0002','tipo':'Opção','elemento':'ÁUDIOS'}]);original=copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as tmp:
            paths=exportar(data,Path(tmp),'principal')
            self.assertEqual(len(json.loads(Path(paths['json']).read_text())['divergencias']),2)
            with open(paths['csv'],encoding='utf-8-sig') as f:rows=list(csv.DictReader(f,delimiter=';'))
            self.assertEqual([r['elemento'] for r in rows],['ÁUDIOS'])
            html=Path(paths['html']).read_text();self.assertIn('Diagnóstico completo',html)
            self.assertNotIn('data-div-id="DIV-0099"',html)
            self.assertIn('M0 0',html)
            data['exportacao_completa']=True
            paths=exportar(data,Path(tmp),'completo')
            with open(paths['csv'],encoding='utf-8-sig') as f:self.assertEqual(len(list(csv.DictReader(f,delimiter=';'))),2)
            self.assertEqual(len(montar_diagnostico(data)['diferencas_completas']),2)
        data.pop('exportacao_completa');self.assertEqual(data,original)
    def test_interface_mostrar_todas_reclassificar_exportar(self):
        from playwright.sync_api import sync_playwright
        from web import server
        with tempfile.TemporaryDirectory() as tmp,patch.object(server,'PASTA',Path(tmp)):
            root=Path(tmp);path=root/f'comparacao_{RID}.json';atomic_json(path,report([svg(),{'id':'DIV-0002','tipo':'Opção','elemento':'ÁUDIOS'}]));original=path.read_bytes()
            client=server.app.test_client()
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                try:
                    page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    def respond(route):
                        req=route.request;url=req.url.split('http://ambidiff.test',1)[-1]
                        res=client.open(url,method=req.method,json=req.post_data_json if req.method=='PUT' else None)
                        route.fulfill(status=res.status_code,content_type=res.content_type,body=res.data);res.close()
                    page.route('http://ambidiff.test/**',respond)
                    page.goto('http://ambidiff.test/',wait_until='networkidle')
                    page.evaluate(f'openReport("{RID}")');page.wait_for_selector('#div-div-0002')
                    self.assertEqual(page.locator('.result-card').count(),1)
                    page.locator('#show-all-differences').check();self.assertEqual(page.locator('.result-card').count(),2)
                    page.locator('[aria-label="Reclassificar DIV-0099"]').select_option('relevante')
                    page.wait_for_function("document.querySelector('[aria-label=\"Reclassificar DIV-0099\"]').value==='relevante'")
                    page.wait_for_timeout(100)
                    page.locator('#show-all-differences').uncheck();self.assertEqual(page.locator('.result-card').count(),2)
                    self.assertFalse(errors);self.assertEqual(path.read_bytes(),original)
                finally:browser.close()
            csv_response=client.get(f'/download/{RID}/csv');self.assertIn('ÁUDIOS',csv_response.data.decode('utf-8-sig'));csv_response.close()

    def test_svg_dom_e_icone_ausente_em_controle_equivalente(self):
        from playwright.sync_api import sync_playwright
        from ambidiff.visual import comparar_visuais
        from ambidiff.core import Pagina
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            try:
                pages=[browser.new_page(),browser.new_page()]
                for page,path in zip(pages,['M1 1','M2 2']):
                    page.set_content(f'<main><button>Consultar<svg width="20" height="20"><path d="{path}"/></svg></button></main>')
                pa=Pagina('https://a.test/','@inicio','Portal',[],['Início']);pb=Pagina('https://b.test/','@inicio','Portal',[],['Início'])
                icons,_=comparar_visuais(*pages,pa,pb)
                self.assertEqual(classificar(icons[0])[0],'baixa')
                pages[1].set_content('<main><button>Consultar</button></main>')
                icons,_=comparar_visuais(*pages,pa,pb)
                self.assertEqual(classificar(icons[0])[0],'relevante')
                self.assertTrue(icons[0]['diferenca_estrutural'])
            finally:browser.close()
    def test_reclassificar_membro_de_json_ja_agrupado(self):
        rows=[svg(id='DIV-0001'),svg(id='DIV-0002',url_presente='https://a.test/dois')]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paths=exportar(report(rows),root,RID);before=Path(paths['json']).read_bytes()
            changed=reclassificar(root,RID,'DIV-0002','inconclusivo')
            self.assertEqual(len(changed['divergencias']),2)
            self.assertEqual(next(r for r in changed['divergencias'] if r['id']=='DIV-0002')['classificacao'],'inconclusivo')
            self.assertEqual(Path(paths['json']).read_bytes(),before)
    def test_confirmacao_manual_nao_e_engolida_por_grupo_tecnico(self):
        data=preparar(report([svg(id='DIV-0001'),svg(id='DIV-0002',revisao_manual='confirmada')]))
        self.assertEqual(len(data['divergencias']),2)
        self.assertEqual(data['divergencias'][1]['classificacao'],'relevante')
