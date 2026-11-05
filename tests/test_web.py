"""Painel e exportação locais: nenhum site externo e nenhum navegador requerido."""
import base64
from io import BytesIO
import json
import re
import threading
import zipfile

import pytest

from ambidiff_next.models import finding
from ambidiff_next.reporting import export_report, evidence_file, safe_filename
from ambidiff_next.web import create_app


@pytest.fixture
def app(tmp_path):
    result=create_app(tmp_path)
    result.config.update(TESTING=True)
    return result


def auth(app):return {'X-Next-Token':app.extensions['next_token']}


def seeded(app):
    store=app.extensions['next_store']
    rid=store.create_run({'roots':['http://127.0.0.1:9101/','http://127.0.0.1:9102/'],'labels':['PRD','HOMOL'],'name':'=Órgão teste'})
    a=store.add_finding(rid,finding('opcao_ausente','estrutural','ÁUDIOS','http://127.0.0.1:9101/','http://127.0.0.1:9102/',confidence='confirmado',observed_a='Presente',observed_b='Não identificada',section='Menu'))
    b=store.add_finding(rid,finding('documento_distinto','documento','Contrato','http://127.0.0.1:9101/','http://127.0.0.1:9102/',observed_a='a.pdf',observed_b='b.pdf'))
    return store,rid,a,b


def test_painel_separado_sem_dependencias_externas(app):
    result=app.test_client().get('/')
    assert result.status_code==200
    assert b'AmbiDiff Next' in result.data
    assert b'next-token' in result.data
    assert 'frame-ancestors' in result.headers['Content-Security-Policy']
    assert b'cdn.' not in result.data


def test_mutacao_exige_token_origem_e_host_locais(app):
    client=app.test_client()
    assert client.post('/api/runs',json={}).status_code==403
    assert client.post('/api/runs',json={},headers={**auth(app),'Origin':'https://externo.invalid'}).status_code==403
    assert client.get('/api/runs',headers={'Host':'externo.invalid'}).status_code==403
    assert client.post('/api/runs',json={},headers=auth(app)).status_code==400
    assert client.get('/api/runs/inexistente').status_code==404


def test_urls_inseguras_nao_iniciam_worker(app):
    client=app.test_client()
    for roots in (['http://usuario:senha@localhost/','http://localhost/b'],['http://localhost/logout','http://localhost/b'],['file:///tmp/a','http://localhost/b']):
        assert client.post('/api/runs',json={'roots':roots},headers=auth(app)).status_code==400
    assert app.extensions['next_store'].list_runs()==[]


def test_interrupcao_um_clique_retorna_confirmacao_e_preserva_pendente(tmp_path):
    started=threading.Event()
    class FakeEngine:
        def __init__(self,store,evidence):self.store=store
        def run(self,rid,stop):
            self.store.update_run(rid,status='running')
            self.store.enqueue(rid,'pair',{'urls':['http://127.0.0.1:9101/','http://127.0.0.1:9102/']})
            self.store.add_finding(rid,finding('opcao_ausente','estrutural','ÁUDIOS'))
            started.set()
            assert stop.wait(4)
            self.store.update_run(rid,status='interrupted')
    app=create_app(tmp_path,engine_factory=FakeEngine);client=app.test_client()
    response=client.post('/api/runs',json={'roots':['http://127.0.0.1:9101/','http://127.0.0.1:9102/']},headers=auth(app))
    assert response.status_code==202
    rid=response.json['id'];assert started.wait(2)
    worker=app.extensions['next_workers'][rid]['thread']
    assert client.post('/api/runs',json={'roots':['http://127.0.0.1:9101/','http://127.0.0.1:9102/']},headers=auth(app)).status_code==409
    stopped=client.post(f'/api/runs/{rid}/stop',json={},headers=auth(app))
    assert stopped.status_code==202
    assert 'Interrupção solicitada' in stopped.json['message']
    worker.join(3);assert not worker.is_alive()
    report=client.get(f'/api/runs/{rid}').json
    assert report['run']['status']=='interrupted'
    assert report['findings'][0]['element']=='ÁUDIOS'
    assert report['tasks'][0]['state']=='pending'


def test_selecao_independente_da_revisao_persiste_no_servidor(app):
    store,rid,a,b=seeded(app);client=app.test_client();url=f'/api/runs/{rid}/review'
    assert client.post(url,json={'ids':[a],'action':'select','selected':True},headers=auth(app)).status_code==200
    assert store.report(rid)['reviews'][a]=={'status':'pending','selected':True}
    assert client.post(url,json={'ids':[a],'action':'confirmed'},headers=auth(app)).status_code==200
    assert store.report(rid)['reviews'][a]=={'status':'confirmed','selected':True}
    client=app.test_client()
    assert client.get(f'/api/runs/{rid}').json['findings'][0]['selected'] is True
    assert client.post(url,json={'ids':['DIV-9999'],'action':'select','selected':True},headers=auth(app)).status_code==400
    assert len(store.report(rid)['occurrences'])==2


def test_csv_selecionado_sem_duplicacao_com_excel_e_protecao(app):
    store,rid,a,b=seeded(app);store.review(rid,[a],'select',True)
    response=app.test_client().get(f'/api/runs/{rid}/export?format=csv&scope=selected')
    text=response.data.decode('utf-8-sig')
    assert response.status_code==200
    assert response.data.startswith(b'\xef\xbb\xbf')
    assert ';' in text and "'=Órgão teste" in text
    assert text.count(a)==1 and b not in text
    assert len(store.report(rid)['occurrences'])==2
    store.review(rid,[a],'hidden')
    assert a not in app.test_client().get(f'/api/runs/{rid}/export?format=csv&scope=selected').data.decode('utf-8-sig')


def test_json_completo_e_selecionado_preservam_originais(app):
    store,rid,a,b=seeded(app);store.review(rid,[b],'select',True);client=app.test_client()
    store.review(rid,[a],'false_positive')
    store.log(rid,'Detalhe não relacionado à seleção')
    store.diagnose(rid,{'private_detail':'Inventário não relacionado'})
    store.enqueue(rid,'pair',{'urls':['http://127.0.0.1:9101/outra','http://127.0.0.1:9102/outra']})
    from ambidiff_next.models import Page
    store.save_page(rid,0,Page('http://127.0.0.1:9101/outra','http://127.0.0.1:9101/outra','Página não relacionada'))

    selected=client.get(f'/api/runs/{rid}/export?format=json&scope=selected').json
    complete=client.get(f'/api/runs/{rid}/export?format=json&scope=all').json
    assert len(selected['findings'])==1 and selected['findings'][0]['id']==b
    assert len(selected['occurrences'])==1
    assert selected['export_scope']=='selected'
    assert not any(key in selected for key in ('pages','tasks','logs','diagnostics'))
    assert list(selected['reviews'])==[b]
    assert 'current' not in selected['run']
    assert selected['export_limitations']
    assert complete['pages'] and complete['tasks'] and complete['logs'] and complete['diagnostics']
    assert store.report(rid)['pages'] and store.report(rid)['diagnostics']

    assert len(complete['findings'])==len(store.report(rid)['findings'])==2
    assert client.get(f'/api/runs/{rid}/export?format=exe').status_code==400


def test_html_portatil_zip_e_evidencias_sem_traversal(tmp_path):
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/a1kAAAAASUVORK5CYII=')
    (tmp_path/'a.png').write_bytes(png)
    row=finding('visual_distinto','visual','<script>teste</script>',evidence={'a':'a.png','b':'../privado.png'})
    row.update(id='DIV-0001',occurrence_ids=['occ-1'])
    report={'run':{'id':'run-1','config':{'name':'Órgão'}},'findings':[row],'occurrences':[],'reviews':{}}
    html=export_report(report,'html',tmp_path).data.decode()
    assert 'data:image/png;base64,' in html
    assert '<script>teste</script>' not in html
    assert '&lt;script&gt;' in html
    result=export_report(report,'zip',tmp_path)
    with zipfile.ZipFile(BytesIO(result.data)) as archive:
        assert 'evidencias/a.png' in archive.namelist()
        assert not any('..' in name for name in archive.namelist())
        assert {'relatorio.html','relatorio.json','diagnostico.json','execucao.log','LIMITES.txt'}<=set(archive.namelist())
    assert evidence_file(tmp_path,'../privado.png') is None
    assert safe_filename('CON')=='Portal_CON'
    assert ':' not in safe_filename('Nome: teste?')


def test_logs_cursor_nao_duplica_apos_200(app):
    store,rid,_,_=seeded(app)
    for i in range(300):store.log(rid,f'Mensagem {i}')
    client=app.test_client();first=client.get(f'/api/runs/{rid}/logs?after=0').json
    second=client.get(f'/api/runs/{rid}/logs?after={first["cursor"]}').json
    ids=[r['seq'] for r in first['entries']+second['entries']]
    assert len(ids)==len(set(ids))==300
    assert client.get(f'/api/runs/{rid}/logs?after={second["cursor"]}').json['entries']==[]


def test_retomada_reutiliza_id_e_pendencias_sem_apagar_dados(tmp_path):
    resumed=threading.Event()
    class ResumeEngine:
        def __init__(self,store,evidence):self.store=store
        def run(self,rid,stop):
            self.store.recover(rid);self.store.update_run(rid,status='running')
            resumed.set()
            task=self.store.claim(rid)
            self.store.finish(rid,task['id'],'done')
            self.store.update_run(rid,status='completed')
    app=create_app(tmp_path,engine_factory=ResumeEngine);store,rid,a,b=seeded(app)
    store.enqueue(rid,'pair',{'urls':['http://127.0.0.1:9101/','http://127.0.0.1:9102/']})
    store.update_run(rid,status='interrupted')
    client=app.test_client();response=client.post(f'/api/runs/{rid}/resume',json={},headers=auth(app))
    assert response.status_code==202 and response.json['id']==rid
    assert resumed.wait(2)
    workers=list(app.extensions['next_workers'].values())
    for worker in workers:worker['thread'].join(3)
    assert len(store.report(rid)['findings'])==2
    assert store.report(rid)['tasks'][0]['state']=='done'


def test_interface_real_selecao_filtros_reload_e_download(tmp_path):
    """Integração Chromium: apenas painel local e dados fictícios pré-carregados."""
    import os
    import shutil
    from playwright.sync_api import sync_playwright,expect
    from werkzeug.serving import make_server
    app=create_app(tmp_path);store,rid,a,b=seeded(app)
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    executable=os.getenv('AMBIDIFF_NEXT_CHROMIUM') or shutil.which('chromium')
    try:
        with sync_playwright() as p:
            options={'headless':True}
            if executable:options['executable_path']=executable
            browser=p.chromium.launch(**options)
            try:
                page=browser.new_page()
                page.add_init_script("window.showSaveFilePicker=async function(){throw new DOMException('Indisponível','SecurityError');};")
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                page.get_by_role('button',name='Abrir',exact=True).click()
                expect(page.locator('#findings .finding')).to_have_count(2)
                page.locator('#findings input[type=checkbox]').first.check()
                expect(page.locator('#selected-count')).to_contain_text('1 selecionadas')
                assert store.report(rid)['reviews'][a]['status']=='pending'
                page.reload()
                expect(page.locator('#findings input[type=checkbox]').first).to_be_checked()
                page.locator('#search').fill('1,2')
                assert page.locator('#findings .finding').count()==2
                page.locator('#search').fill('1-1')
                assert page.locator('#findings .finding').count()==1
                page.locator('#filter-nature').select_option('documento')
                assert page.locator('#findings .finding').count()==0
                page.locator('#filter-nature').select_option('')
                assert page.locator('#findings .finding').count()==1
                page.locator('#exports summary').click()
                page.locator('#export-scope').select_option('selected')
                assert page.locator('input[name=format][value=csv]').is_checked()
                with page.expect_download() as download:
                    page.locator('#download').click()
                downloaded=download.value
                from pathlib import Path
                text=Path(downloaded.path()).read_text(encoding='utf-8-sig')
                assert a in text and b not in text
                assert store.report(rid)['findings'][0]['review_status']=='pending'
                assert len(store.report(rid)['occurrences'])==2
            finally:browser.close()
    finally:server.shutdown();thread.join(3);server.server_close()
