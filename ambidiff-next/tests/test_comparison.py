"""Regressões sem rede: diferenças conhecidas e correspondências conservadoras."""
from ambidiff_next.models import Element,Page
from ambidiff_next.matching import match_elements
from ambidiff_next.comparison import compare_pages,compare_functions

ROOTS=('https://prd.invalid/','https://homol.invalid/')


def item(id,name,url='',section='Menu principal',**kwargs):
    return Element(id,'link',name,section=section,url=url,**kwargs)


def pages(a,b,**kwargs):
    return Page(ROOTS[0],ROOTS[0],'Portal',a),Page(ROOTS[1],ROOTS[1],'Portal',b,**kwargs)


def test_menu_equivalente_com_html_e_posicoes_diferentes():
    a,b=pages([item('a','Serviços',ROOTS[0]+'servicos',selector='#a',bbox={'x':0,'y':10})],
              [item('b','Serviços',ROOTS[1]+'servicos',section='Rodapé',selector='footer div a',bbox={'x':300,'y':20})])
    result=compare_pages(a,b,ROOTS)
    assert len(result['matches'])==1
    assert not result['findings']


def test_audios_cge_presente_prd_nao_identificado_des_html_ficticio():
    # O parser de navegador é integrado em test_browser; o modelo conserva nome acessível.
    a,b=pages([item('audio','ÁUDIOS',ROOTS[0]+'audios')],[])
    row=compare_pages(a,b,ROOTS)['findings'][0]
    assert row['element']=='ÁUDIOS' and row['nature']=='estrutural'
    assert row['observed_a']=='Presente' and row['observed_b']=='Não identificado'
    assert row['confidence']=='confirmado'


def test_opcao_exclusiva_homol_mesmo_tratamento():
    a,b=pages([],[item('b','Serviço novo',ROOTS[1]+'novo')])
    row=compare_pages(a,b,ROOTS)['findings'][0]
    assert row['observed_b']=='Presente' and row['observed_a']=='Não identificado'


def test_rotulos_semanticos_com_contexto_sao_hipotese_rastreavel():
    a,b=pages([item('a','Consulta de Processos',ROOTS[0]+'servicos/consulta-processual',section='Serviços')],
              [item('b','Consultar Processo',ROOTS[1]+'consulta',section='Serviços ao Cidadão')])
    matches=match_elements(a,b,ROOTS)['matches']
    assert len(matches)==1 and matches[0]['confidence']=='intermediaria'
    result=compare_pages(a,b,ROOTS)
    assert {r['code'] for r in result['findings']}=={'rotulo_diferente','destinos_diferentes'}
    assert any(d.get('status')=='possivel_correspondencia' for d in result['diagnostics'])


def test_consultar_ambiguo_nao_forca_equivalencia():
    a,b=pages([item('a','Consultar',ROOTS[0]+'x')],
              [item('b','Consultar',ROOTS[1]+'y'),item('c','Consultar',ROOTS[1]+'z')])
    result=match_elements(a,b,ROOTS)
    assert not result['matches'] and result['ambiguous']
    assert all(r['confidence']=='inconclusivo' for r in compare_pages(a,b,ROOTS)['findings'])


def test_query_liferay_c_e_fragmentos_preservados():
    for da,db in [('pagina?c=1&e=2','pagina?c=2&e=2'),('pagina#aba1','pagina#aba2')]:
        a,b=pages([item('a','Consultar',ROOTS[0]+da)],[item('b','Consultar',ROOTS[1]+db)])
        assert any(r['code']=='destinos_diferentes' for r in compare_pages(a,b,ROOTS)['findings'])


def test_referencia_externa_igual_nao_diferente_difere_sem_acesso():
    a,b=pages([item('a','Sistema','https://external.invalid/a')],[item('b','Sistema','https://external.invalid/a')])
    assert not compare_pages(a,b,ROOTS)['findings']
    b.elements[0].url='https://external.invalid/b'
    assert compare_pages(a,b,ROOTS)['findings'][0]['code']=='destinos_diferentes'


def test_documento_liferay_e_imagem_nao_confundidos():
    a,b=pages([item('a','Manual',ROOTS[0]+'documents/d/site/manual')],[item('b','Manual',ROOTS[1]+'documents/d/site/manual2')])
    assert compare_pages(a,b,ROOTS)['findings'][0]['nature']=='documento'
    a.elements[0].url=ROOTS[0]+'imagem.png';b.elements[0].url=ROOTS[1]+'outra.png'
    assert compare_pages(a,b,ROOTS)['findings'][0]['nature']!='documento'


def test_editorial_nao_oculta_audios_e_nao_comprova_defasagem():
    a,b=pages([item('a','Notícia 05/11/2026',ROOTS[0]+'noticias/n',editorial=True),item('audio','ÁUDIOS',ROOTS[0]+'audio')],
              [item('b','Notícia 04/11/2026',ROOTS[1]+'noticias/n',editorial=True)])
    result=compare_pages(a,b,ROOTS,{'outdated':'HOMOL'})
    assert any(r['element']=='ÁUDIOS' and r['nature']=='estrutural' for r in result['findings'])
    assert any(r['nature']=='editorial' for r in result['findings'])


def test_falha_extracao_limita_ausencia_auxiliar_nao():
    a,b=pages([item('a','ÁUDIOS')],[],diagnostics=[{'code':'DOM_UNAVAILABLE'}])
    assert compare_pages(a,b,ROOTS)['findings'][0]['confidence']=='inconclusivo'
    b.diagnostics=[{'code':'AUXILIARY_BLOCKED'}]
    assert compare_pages(a,b,ROOTS)['findings'][0]['confidence']=='confirmado'


def test_redirecionamento_divergente_e_http_nao_equivalem():
    a,b=pages([],[]);b.final_url=ROOTS[1]+'login';b.status=404
    assert {r['code'] for r in compare_pages(a,b,ROOTS)['findings']}=={'redirecionamento_diferente','resposta_http_erro'}


def test_funcoes_observadas_divergem_sem_declara_defeito_comprovado():
    r=compare_functions({'status':'executed','changed':True,'observation':'Painel aberto'},
                        {'status':'executed','changed':False,'observation':'Sem alteração'},'Consultar')
    assert r['findings'][0]['code']=='resposta_funcional_diferente'
    assert r['findings'][0]['confidence']=='possivel'
    assert compare_functions({'status':'untested'},{'status':'executed','changed':True})['diagnostics']
    assert not compare_functions({'status':'inconclusive'},{'status':'executed','changed':True})['findings']
    assert compare_functions({'status':'executed','changed':False},{'status':'executed','changed':False})['diagnostics']


def test_ordem_relevante_explicitamente_nao_significa_opcao_ausente():
    a,b=pages([item('a1','Serviços',ROOTS[0]+'s'),item('a2','Contato',ROOTS[0]+'c')],
              [item('b2','Contato',ROOTS[1]+'c'),item('b1','Serviços',ROOTS[1]+'s')])
    assert not compare_pages(a,b,ROOTS)['findings']
    rows=compare_pages(a,b,ROOTS,{'compare_menu_order':True})['findings']
    assert len(rows)==1 and rows[0]['code']=='ordem_opcoes_diferente'


def test_erro_http_e_dom_vazio_nao_comprovam_opcao_ausente():
    a,b=pages([item('a','ÁUDIOS')],[],status=503)
    rows=compare_pages(a,b,ROOTS)['findings']
    assert next(r for r in rows if r['element']=='ÁUDIOS')['confidence']=='inconclusivo'
    b.status=200;b.diagnostics=[{'code':'EMPTY_DOM'}]
    assert compare_pages(a,b,ROOTS)['findings'][0]['confidence']=='inconclusivo'
