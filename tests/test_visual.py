"""Imagem real em memória e disco local; nenhuma inferência de screenshot ausente."""
from PIL import Image,ImageDraw
from ambidiff_next.models import Element
from ambidiff_next.visual import compare_components


def component(id,file,**kwargs):return Element(id,'button','Consultar',attrs={'screenshot':file,**kwargs})


def images(root,different=False):
    a=Image.new('RGB',(100,100),'white');b=a.copy()
    if different:ImageDraw.Draw(b).rectangle((0,0,49,49),fill='red')
    a.save(root/'a.png');b.save(root/'b.png')


def test_capturas_iguais_sem_div_visual(tmp_path):
    images(tmp_path)
    r=compare_components(component('a','a.png'),component('b','b.png'),tmp_path)
    assert r['metrics']['completed'] and not r['findings']


def test_diferenca_visual_real_tem_duas_evidencias_e_diff(tmp_path):
    images(tmp_path,True)
    r=compare_components(component('a','a.png'),component('b','b.png'),tmp_path)
    row=r['findings'][0]
    assert row['code']=='aparencia_diferente'
    assert row['evidence']['a']=='a.png' and row['evidence']['b']=='b.png'
    assert (tmp_path/row['evidence']['diff']).is_file()
    assert r['metrics']['different_fraction']==.25


def test_css_oculto_e_sobreposicao_sem_imagens_nao_completa_visual(tmp_path):
    a=component('a','');b=component('b','',occluded=True,clipped=True);b.visible=False
    r=compare_components(a,b,tmp_path)
    assert not r['metrics']['completed']
    assert len(r['findings'])==3 and all(x['confidence']=='possivel' for x in r['findings'])


def test_mascara_dinamica_explicita_registrada_e_limitada(tmp_path):
    images(tmp_path,True)
    mask=[{'box':[0,0,50,50],'reason':'Contador temporal identificado nos dois ambientes'}]
    r=compare_components(component('a','a.png',masks=mask),component('b','b.png',masks=mask),tmp_path)
    assert not r['findings'] and r['metrics']['masks']
    broad=[{'box':[0,0,100,100],'reason':'Ignorar tudo'}]
    r=compare_components(component('a','a.png',masks=broad),component('b','b.png',masks=broad),tmp_path)
    assert r['findings'] and not r['metrics']['masks']


def test_mascara_sem_justificativa_ou_somente_um_lado_nao_oculta(tmp_path):
    images(tmp_path,True)
    r=compare_components(component('a','a.png',masks=[{'box':[0,0,50,50]}]),component('b','b.png'),tmp_path)
    assert r['findings']


def test_travessia_e_imagem_invalida_nao_completam(tmp_path):
    images(tmp_path);(tmp_path/'bad.png').write_text('não é PNG')
    for path in ('../a.png','bad.png'):
        r=compare_components(component('a',path),component('b','b.png'),tmp_path)
        assert not r['metrics']['completed'] and r['diagnostics']


def test_dimensao_diferente_e_posicao_apenas_nao_geram_ausencia(tmp_path):
    images(tmp_path)
    a,b=component('a','a.png'),component('b','b.png');a.bbox={'x':0,'y':0};b.bbox={'x':200,'y':300}
    assert not compare_components(a,b,tmp_path)['findings']
    Image.new('RGB',(120,100),'white').save(tmp_path/'b.png')
    assert any(x['code']=='dimensoes_divergente' for x in compare_components(a,b,tmp_path)['findings'])


def test_dado_editorial_diferente_preserva_imagens_sem_alegar_defeito_visual(tmp_path):
    images(tmp_path,True)
    a,b=component('a','a.png'),component('b','b.png')
    a.editorial=b.editorial=True;a.name='Notícia de hoje';b.name='Notícia de ontem'
    r=compare_components(a,b,tmp_path)
    assert r['metrics']['completed'] and r['findings'][0]['nature']=='editorial'


def test_text_raster_is_inconclusive_preserves_images_not_false_defect(tmp_path):
    images(tmp_path,True)
    attrs={'text_only':True,'visible_text':'Contato','style':{'color':'blue','font_size':'16px'}}
    a=Element('a','link','Contato',bbox={'width':100,'height':100},attrs={'screenshot':'a.png',**attrs})
    b=Element('b','link','Contato',bbox={'width':100,'height':100},attrs={'screenshot':'b.png',**attrs})
    result=compare_components(a,b,tmp_path)
    assert result['metrics']['completed']
    assert not result['findings']
    assert result['diagnostics'][0]['status']=='rasterizacao_textual_inconclusiva'
    assert result['diagnostics'][0]['evidence']=={'a':'a.png','b':'b.png'}
    b.attrs['text_only']=False
    assert compare_components(a,b,tmp_path)['findings']
    b.attrs['text_only']=True;b.attrs['style']={'color':'red','font_size':'16px'}
    assert compare_components(a,b,tmp_path)['findings']
