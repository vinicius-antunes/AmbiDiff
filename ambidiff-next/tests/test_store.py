from ambidiff_next.store import Store
from ambidiff_next.models import finding


def test_incremental_resume_immutable_reviews_and_selection(tmp_path):
    s=Store(tmp_path/'state.sqlite3');r=s.create_run({'roots':['http://a.test/','http://b.test/']})
    assert s.enqueue(r,'page_pair',{'urls':['http://a.test/','http://b.test/']})
    assert not s.enqueue(r,'page_pair',{'urls':['http://a.test/','http://b.test/']})
    t=s.claim(r);assert t['attempts']==1
    again=Store(s.path);again.recover(r);assert again.tasks(r)[0]['state']=='pending'
    assert again.claim(r)['attempts']==2
    again.recover(r);assert again.tasks(r)[0]['state']=='failed'
    raw=finding('ausente','estrutural','ÁUDIOS','http://a.test/','http://b.test/',confidence='confirmado')
    gid=s.add_finding(r,raw);assert s.add_finding(r,raw)==gid
    s.review(r,[gid],'select',selected=True)
    assert s.report(r,True)['findings'][0]['review_status']=='pending'
    s.review(r,[gid],'confirmed');assert s.report(r)['occurrences']==[raw]
    s.review(r,[gid],'hidden');assert s.report(r,True)['findings']==[]
    assert Store(s.path).report(r)['occurrences']==[raw]


def test_1000_incremental_logs_no_duplicates_and_secrets_redacted(tmp_path):
    s=Store(tmp_path/'db.sqlite');r=s.create_run({})
    for i in range(1001):s.log(r,f'log {i} https://a.test/p?token=segredo&c=123')
    cursor=0;ids=[]
    while True:
        result=s.logs(r,cursor)
        if not result['entries']:break
        assert all('segredo' not in x['message'] and '123' not in x['message'].split('https://',1)[1] for x in result['entries'])
        ids.extend(x['seq'] for x in result['entries']);cursor=result['cursor']
    assert len(ids)==len(set(ids))==1001
    assert Store(s.path).logs(r,cursor)['entries']==[]


def test_distinct_sections_and_destinations_not_grouped_by_label(tmp_path):
    s=Store(tmp_path/'db.sqlite');r=s.create_run({})
    a=finding('destinos','navegacao','Consultar','a','b',section='Serviços',observed_a='/um',observed_b='/dois')
    b=finding('destinos','navegacao','Consultar','a','b',section='Legislação',observed_a='/tres',observed_b='/quatro')
    assert s.add_finding(r,a)!=s.add_finding(r,b)
    assert len(s.report(r)['occurrences'])==2


def test_one_stop_does_not_regress_terminal_state(tmp_path):
    s=Store(tmp_path/'db.sqlite');r=s.create_run({});s.interrupt(r)
    assert s.get_run(r)['status']=='stop_requested'
    s.update_run(r,status='completed');s.interrupt(r)
    assert s.get_run(r)['status']=='completed'
