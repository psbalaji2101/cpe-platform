import pytest
from cpe.db import DB,Case
from cpe.worker import process_once
from test_platform import create


def test_incomplete_run_does_not_claim_completed_analysis_or_allow_approval(client):
    case=create(client)
    response=client.post(f'/api/cases/{case}/investigations',json={'partial':True})
    assert response.status_code==202
    process_once()
    run=client.get(f'/api/cases/{case}/runs').json()[0]
    assert run['summary'].startswith('Investigation incomplete:')
    assert 'No supported failure signature' not in run['summary']
    assert client.post(f'/api/runs/{run["id"]}/approve',json={'digest':run['digest']}).status_code==409


def test_saved_placeholder_cannot_start_even_partial_run(client):
    case=create(client)
    with DB.begin() as db:
        c=db.get(Case,case)
        c.config={'components':[{'id':'example.processor','namespace':'example','pod_names':['processor-0']}]}
        c.components=['example.processor']
    for partial in [True,False]:
        response=client.post(f'/api/cases/{case}/investigations',json={'partial':partial})
        assert response.status_code==422
        assert 'actual affected component' in response.text


@pytest.mark.parametrize("verified_storage", [False, True])
def test_late_pod_description_and_pvc_subpath_mapping(client, verified_storage):
    import io,zipfile,json
    from test_platform import put_upload
    case=create(client)
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        z.writestr('describe.log','unrelated line\n'*4000+'Name: target-0\nNamespace: actual\nMounts:\n  /logs from log-volume (rw,path="product/")\nVolumes:\n  log-volume:\n    ClaimName: product-logs\n')
        z.writestr('kubernetes/target-0.log','2026-09-25T10:00:00Z INFO started\n')
        z.writestr('snapshot.json','{"items": []}')
        if verified_storage:
            z.writestr('pvcs.json',json.dumps(json.loads('{"kind":"PersistentVolumeClaim","metadata":{"name":"product-logs","namespace":"actual","uid":"claim-1"},"spec":{"volumeName":"pv-1"}}'),indent=2))
            z.writestr('pvs.json',json.dumps(json.loads('{"kind":"PersistentVolume","metadata":{"name":"pv-1"},"spec":{"claimRef":{"name":"product-logs","namespace":"actual","uid":"claim-1"},"nfs":{"server":"nfs.internal","path":"/logs"}}}'),indent=2))
        z.writestr('archive/product/application.log','2026-09-25T10:00:00Z ERROR no space left on device\n')
    put_upload(client,case,b.getvalue())
    with DB.begin() as db:
        c=db.get(Case,case)
        c.config={'components':[{'id':'actual.product','namespace':'actual','pod_names':['target-0'],
            'kubernetes_log_patterns':['kubernetes/target-0.log'],'product_log_patterns':['application.log']}],
            'archive_path_mappings':[{'namespace':'actual','pvc_claim':'product-logs','mount_subpath':'product/','archive_prefix':'archive/product/'}]}
        c.components=['actual.product']
    response=client.post(f'/api/cases/{case}/investigations',json={'partial':True})
    assert response.status_code==202
    process_once()
    run=client.get(f'/api/cases/{case}/runs').json()[0]
    assert any(s['stage']=='Product log analysis' for s in run['stages'])
    assert any('no space' in f['title'].lower() for f in run['findings'])
    assert any('backing PV/NFS export not verified' in g for g in run['coverage']['gaps']) is (not verified_storage)
    assert bool(run['coverage']['verified_storage']) is verified_storage
    if verified_storage:
        assert run['status'] == 'Findings Ready'
        assert not run['coverage']['bounded_retrieval']


def test_pvc_mapping_does_not_mix_mounts_from_another_volume():
    from types import SimpleNamespace
    from cpe.investigation import pvc_subpath_matches
    events=[SimpleNamespace(message=s) for s in [
        '  /logs from other (rw,path="product/")', 'Volumes:',
        '  target:', '    ClaimName: product-logs',
        '  other:', '    ClaimName: different-logs']]
    assert not pvc_subpath_matches(events,{'pvc_claim':'product-logs','mount_subpath':'product/'})


def test_lowercase_structured_severity_takes_precedence():
    from cpe.ingestion import severity
    assert severity('time="2026-09-26T22:18:36Z" level=error msg="certificate unavailable"') == 'ERROR'
    assert severity('{"level":"warning", "message":"retry"}') == 'WARN'
    assert severity('error counter level=info msg="no failure"') == 'INFO'
    assert severity('level=critical msg="failure"') == 'ERROR'
    assert severity('warning failed') == 'WARN'
