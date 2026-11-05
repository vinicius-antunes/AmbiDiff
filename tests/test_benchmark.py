"""Contrato do benchmark: não premia velocidade obtida com cobertura perdida."""
import importlib.util
from pathlib import Path
from urllib.request import urlopen, Request

SPEC=importlib.util.spec_from_file_location('next_benchmark',Path(__file__).resolve().parents[1]/'scripts'/'benchmark_comparative.py')
benchmark=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(benchmark)


def measurements(seconds,detected=None):
    known=detected if detected is not None else [t['id'] for t in benchmark.TRUTH]
    return {'seconds':seconds,'status':'completed','metrics':{'elements_checked':30,'functional_executed':4,'visual_compared':8},
            'quality':{'detected_truth_ids':known,'false_negatives':len(benchmark.TRUTH)-len(known),'false_positives':0}}


def test_faster_but_missing_audio_is_not_an_improvement():
    legacy=measurements(100);next_result=measurements(50,[t['id'] for t in benchmark.TRUTH if t['id']!='audio'])
    result=benchmark.qualify_gain(legacy,next_result)
    assert result['observed_time_reduction_percent']==50
    assert not result['qualified_improvement']
    assert not result['target_achieved_experimentally']
    assert any('perdeu divergências' in r for r in result['reasons'])


def test_faster_but_fewer_functional_checks_is_not_an_improvement():
    old=measurements(100);new=measurements(60);new['metrics']['functional_executed']=1
    result=benchmark.qualify_gain(old,new)
    assert not result['qualified_improvement']
    assert 'Cobertura reduzida: functional_executed' in result['reasons']


def test_same_coverage_and_truth_can_qualify_experimental_target():
    result=benchmark.qualify_gain(measurements(100),measurements(65))
    assert result['qualified_improvement'];assert result['target_achieved_experimentally']
    assert not result['real_portal_gain_proven']


def test_unavailable_metrics_are_not_invented_or_counted_as_zero():
    old=measurements(100);old['metrics']['elements_checked']=None
    result=benchmark.qualify_gain(old,measurements(50))
    assert not result['qualified_improvement']
    assert any('indisponível: elements_checked' in r for r in result['reasons'])


def test_errors_and_no_speed_gain_do_not_qualify():
    old=measurements(100);new=measurements(110);new['status']='failed'
    result=benchmark.qualify_gain(old,new)
    assert not result['qualified_improvement'];assert len(result['reasons'])==2


def test_ground_truth_scores_both_directions_and_deduplicates():
    observations=[{'nature':item['nature'],'element':item['element'],'page_a':'http://127.0.0.1:1/','page_b':'http://127.0.0.1:2/'} for item in benchmark.TRUTH]
    observations+=observations
    quality=benchmark.evaluate(observations)
    assert quality['true_positives']==8;assert quality['false_positives']==0;assert quality['false_negatives']==0
    assert quality['precision']==1;assert quality['recall']==1


def test_false_positive_and_false_negative_not_hidden():
    quality=benchmark.evaluate([{'nature':'estrutural','element':'Ouvidoria','page_a':'a','page_b':'b'}])
    assert quality['false_positives']==1;assert quality['false_negatives']==8


def test_legacy_adapter_does_not_upgrade_editorial_or_automation():
    report={'divergencias':[{'tipo':'Opção','categoria':'Estrutura','elemento':'ÁUDIOS'},
        {'tipo':'Variação editorial','categoria':'Editorial','elemento':'Notícia de teste'},
        {'tipo':'Falha de acesso','categoria':'Falhas de acesso','elemento':'HTTP'}]}
    rows=benchmark.canonical_observations(report,'legacy')
    assert len(rows)==1;assert rows[0]['element']=='audios'


def test_redirect_truth_uses_observed_branch_not_numeric_div_id():
    quality=benchmark.evaluate([{'nature':'redirecionamento','element':'Página inicial','page_a':'http://127.0.0.1:1/consulta','page_b':'http://127.0.0.1:2/consulta'}])
    assert quality['detected_truth_ids']==['redirect']


def test_portals_are_local_identical_except_manifest_properties_and_count_requests():
    from benchmark_portals import PortalPair
    with PortalPair(news=3) as portals:
        a,b=portals.roots
        assert a.startswith('http://127.0.0.1:');assert b.startswith('http://127.0.0.1:')
        left=urlopen(a).read().decode();right=urlopen(b).read().decode()
        assert 'ÁUDIOS' in left and 'ÁUDIOS' not in right
        assert 'Agendamento' in right and 'Agendamento' not in left
        doc=urlopen(Request(a+'documents/d/portal/regulamento',method='HEAD'))
        assert doc.headers['Content-Type']=='application/pdf'
        assert urlopen(a+'consulta').geturl().endswith('/resultado')
        assert urlopen(b+'consulta').geturl().endswith('/outro')
        tail=urlopen(a+'noticias/2').read().decode()
        assert '/noticias/0' in tail # Finite loop replaces unbounded fixture growth.
        stats=portals.snapshot()['counts']
        assert stats['html_requests']==5;assert stats['document_requests']==1
        assert stats.get('unsafe',0)==0


def test_comparacao_legado_requer_copia_separada(monkeypatch,tmp_path):
    import pytest
    monkeypatch.delenv('AMBIDIFF_LEGACY_PATH',raising=False)
    with pytest.raises(RuntimeError,match='AMBIDIFF_LEGACY_PATH'):
        benchmark.run_legacy(('http://127.0.0.1:1/','http://127.0.0.1:2/'),tmp_path)


def test_comparacao_legado_rejeita_pasta_sem_codigo(monkeypatch,tmp_path):
    import pytest
    monkeypatch.setenv('AMBIDIFF_LEGACY_PATH',str(tmp_path))
    with pytest.raises(RuntimeError,match='AMBIDIFF_LEGACY_PATH inválido'):
        benchmark.run_legacy(('http://127.0.0.1:1/','http://127.0.0.1:2/'),tmp_path)
