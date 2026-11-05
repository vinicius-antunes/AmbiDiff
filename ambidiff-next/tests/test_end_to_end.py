"""API -> worker real -> Chromium -> SQLite -> exportação, somente loopback."""
import time
from benchmark_portals import PortalPair
from ambidiff_next.web import create_app


def test_real_worker_maps_components_preserves_audio_and_exports(tmp_path):
    with PortalPair(news=3) as portals:
        app=create_app(tmp_path);client=app.test_client()
        headers={'X-Next-Token':app.extensions['next_token']}
        result=client.post('/api/runs',headers=headers,json={'name':'Portal fictício','roots':list(portals.roots),'labels':['PRD','HOMOL']})
        assert result.status_code==202
        rid=result.json['id'];deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            report=client.get(f'/api/runs/{rid}').json
            if not report['worker_active']:break
            time.sleep(.1)
        else:raise AssertionError('Worker local não encerrou em 90s; diagnóstico preservado em tmp_path')
        assert report['run']['status'] in ('completed','partial')
        assert report['run']['metrics']['page_pairs_compared']>0
        assert report['run']['metrics']['visual_compared']>0
        assert report['run']['metrics']['functional_executed']>0
        assert any(f['element']=='ÁUDIOS' for f in report['findings'])
        assert any(f['nature']=='funcional' and f['element']=='Detalhes do serviço' for f in report['findings'])
        assert any(f['nature']=='redirecionamento' for f in report['findings'])
        assert any(t['state']=='sampled' for t in report['tasks'])
        counts=portals.snapshot()['counts']
        assert counts.get('POST',0)==0 and counts.get('destructive',0)==0
        exported=client.get(f'/api/runs/{rid}/export?format=json&scope=all')
        assert exported.status_code==200
        assert exported.json['occurrences']==report['occurrences']
