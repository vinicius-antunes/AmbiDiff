from ambidiff_next.planner import Planner,editorial_group
from ambidiff_next.models import Element
from ambidiff_next.store import Store


def test_hundreds_editorial_tasks_sampled_not_validated(tmp_path):
    s=Store(tmp_path/'db');r=s.create_run({});p=Planner(s,r,{'roots':['http://a.test/','http://b.test/'],'max_pages':1000})
    for i in range(200):
        e=Element(str(i),'link',f'Notícia {i}',url=f'http://a.test/noticias/{i}',section='Notícias',editorial=True)
        p.propose(e.url,f'http://b.test/noticias/{i}',['Notícias',e.name],e)
    tasks=s.tasks(r)
    assert sum(t['state']=='pending' for t in tasks)==2
    assert sum(t['state']=='sampled' for t in tasks)==198
    assert all('não validada' in t['reason'] for t in tasks if t['state']=='sampled')


def test_pagination_cycle_query_preserved_and_document_not_html_slot(tmp_path):
    s=Store(tmp_path/'db');r=s.create_run({});p=Planner(s,r,{'roots':['http://a.test/','http://b.test/'],'max_pages':1})
    for i in range(4):
        e=Element(str(i),'link','Próximo',url=f'http://a.test/noticias/{i}',section=f'Notícia {i}',editorial=True)
        p.propose(e.url,f'http://b.test/noticias/{i}',['Notícias'],e)
    assert sum(t['state']=='pending' for t in s.tasks(r))==1
    d=Element('doc','document','Lei',url='http://a.test/documents/d/portal/lei')
    assert p.propose(d.url,'http://b.test/documents/d/portal/lei',['Lei'],d)
    assert any(t['kind']=='document' and t['state']=='pending' for t in s.tasks(r))


def test_news_routes_without_css_classes_are_still_sampled(tmp_path):
    s=Store(tmp_path/'db');r=s.create_run({});p=Planner(s,r,{'roots':['http://a.test/','http://b.test/']})
    for i in range(20):
        e=Element(str(i),'link',f'Publicação {i}',url=f'http://a.test/noticias/{i}',section='Atualizações')
        p.propose(e.url,f'http://b.test/noticias/{i}',[e.name],e)
    assert sum(t['state']=='pending' for t in s.tasks(r))==2
