from copy import deepcopy
import threading
from ambidiff_next.engine import Engine
from ambidiff_next.store import Store
from ambidiff_next.models import Element,Page,stable_id

ROOTS=['http://a.test/','http://b.test/']

def el(side,name,tail,section='Menu',editorial=False):
    return Element(stable_id('e',side,name),'link',name,role='link',url=ROOTS[side]+tail,section=section,editorial=editorial)

class Session:
    calls=[];interrupt=None;fail=False
    def __init__(self,roots,evidence_dir,stop,config):self.stop=stop;self.metrics={'navigations':0}
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def collect(self,url,side,trail):
        self.calls.append((side,url));self.metrics['navigations']+=1
        if self.interrupt and len(self.calls)==3:self.stop.set()
        if self.fail and url.endswith('servico'):return Page(url,url,'',status=0,diagnostics=[{'code':'TIMEOUT'}])
        elements=[el(side,'Serviço','servico'),el(side,'ÁUDIOS' if side==0 else 'Agenda','audios' if side==0 else 'agenda')]
        if url!=ROOTS[side]:elements=[]
        return Page(url,url,'Portal' if url==ROOTS[side] else 'Serviço',elements)
    def perform(self,*_):return {'status':'untested','changed':False}


def run(tmp_path,session=Session,config=None):
    s=Store(tmp_path/'db.sqlite');r=s.create_run({'roots':ROOTS,**(config or {})})
    Engine(s,tmp_path/'evidence',session).run(r,threading.Event())
    return s,r,s.report(r)


def test_symmetric_absences_no_exclusive_tree_expansion(tmp_path):
    Session.calls=[];Session.fail=False;Session.interrupt=None
    s,r,report=run(tmp_path)
    names={f['element'] for f in report['findings']}
    assert {'ÁUDIOS','Agenda'}<=names
    assert report['run']['metrics']['page_pairs_compared']==2
    assert report['run']['metrics']['pages_without_counterpart']==2
    assert len(Session.calls)==6
    assert report['run']['status']=='partial'
    assert all('not_examined' in c for c in report['run']['metrics']['coverage'].values())


def test_interrupt_persists_and_resume_same_id_without_duplicate_occurrences(tmp_path):
    Session.calls=[];Session.interrupt=True;Session.fail=False
    s,r,partial=run(tmp_path)
    assert partial['run']['status']=='interrupted'
    root_calls=Session.calls.count((0,ROOTS[0]))
    assert any(t['state']=='pending' for t in partial['tasks'])
    ids={f['id'] for f in partial['occurrences']}
    Session.interrupt=False
    Engine(Store(s.path),tmp_path/'evidence',Session).run(r,threading.Event())
    report=s.report(r)
    assert Session.calls.count((0,ROOTS[0]))==root_calls
    assert ids<={f['id'] for f in report['occurrences']}
    assert len({f['id'] for f in report['occurrences']})==len(report['occurrences'])


def test_single_failure_keeps_independent_work(tmp_path):
    Session.calls=[];Session.fail=True;Session.interrupt=False
    s,r,report=run(tmp_path)
    assert any(t['state']=='failed' for t in report['tasks'])
    assert {'ÁUDIOS','Agenda'}<={f['element'] for f in report['findings']}
    assert report['run']['metrics']['page_pairs_compared']==1
    assert report['run']['metrics']['technical_failures']==1
    Session.fail=False


def test_capacity_preserves_admitted_and_marks_sampling(tmp_path):
    Session.calls=[];Session.fail=False;Session.interrupt=False
    s,r,report=run(tmp_path,config={'max_pages':1})
    assert report['run']['metrics']['page_pairs_compared']==1
    assert len(Session.calls)==2
    assert any(t['state']=='sampled' for t in report['tasks'])
    assert report['run']['status']=='partial'


def test_intermediate_semantic_hypothesis_gets_additional_corroboration(tmp_path):
    class Semantic(Session):
        def collect(self,url,side,trail):
            self.metrics['navigations']+=1
            if url==ROOTS[side]:
                label='Consulta de Processos' if side==0 else 'Consultar Processo'
                item=el(side,label,'consulta-processual' if side==0 else 'consulta',section='Serviços' if side==0 else 'Serviços ao Cidadão')
                return Page(url,url,'Portal',[item])
            entries=[Element(stable_id('e',side,k),'heading',k,section='Consulta') for k in ('Número do Processo','Resultados')]
            return Page(url,url,'Consulta de Processos',entries)
    s,r,report=run(tmp_path,Semantic)
    assert report['run']['metrics']['correspondences_corroborated']==1
    assert report['run']['metrics']['candidate_elements']==1
    assert report['run']['metrics']['page_pairs_compared']==2
    assert any(d.get('kind')=='corroboration' and d['accepted'] for d in report['diagnostics'])


def test_generic_portal_title_does_not_confirm_semantic_hypothesis(tmp_path):
    class Ambiguous(Session):
        def collect(self,url,side,trail):
            self.metrics['navigations']+=1
            label='Consulta de Processos' if side==0 else 'Consultar Processo'
            return Page(url,url,'Portal',[el(side,label,'consulta-processual' if side==0 else 'consulta',section='Serviços')])
    s,r,report=run(tmp_path,Ambiguous)
    assert report['run']['metrics']['page_pairs_compared']==1
    assert any(t['state']=='inconclusive' and 'Hipótese' in t['reason'] for t in report['tasks'])
    assert not any(d.get('kind')=='corroboration' and d['accepted'] for d in report['diagnostics'])
