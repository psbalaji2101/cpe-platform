import hashlib
import json
from fastapi.testclient import TestClient
from cpe.api import app
from cpe.db import DB, Run
from cpe.storage import artifact_path
from test_platform import create


def test_preliminary_preview_download_integrity_and_invalidation(client):
    case = create(client)
    with DB.begin() as db:
        run = Run(case_id=case, revision=1, evidence_ids=[], config={}, components=[], status='Partial', digest='saved-digest')
        db.add(run)
        db.flush()
        identity = run.id
    body = b'<!doctype html><html><body>Preliminary: hypothesis, not confirmed</body></html>'
    artifact_path('preliminary-reports', identity).write_bytes(body)
    artifact_path('preliminary-manifests', identity).write_text(json.dumps(dict(case_id=case, run_id=identity, revision=1, run_digest='saved-digest', sha256=hashlib.sha256(body).hexdigest())))
    url = f'/api/runs/{identity}/preliminary-report'
    assert client.get(f'/api/cases/{case}/runs').json()[0]['preliminary_report_available']
    preview = client.get(url+'?download=false')
    download = client.get(url)
    assert preview.content == download.content == body
    assert preview.headers['content-disposition'].startswith('inline')
    assert download.headers['content-disposition'].startswith('attachment')
    assert 'sandbox' in download.headers['content-security-policy']
    with TestClient(app) as anonymous:
        assert anonymous.get(url).status_code == 401
    artifact_path('preliminary-reports', identity).write_bytes(body+b'tampered')
    assert client.get(url).status_code == 404
    artifact_path('preliminary-reports', identity).write_bytes(body)
    with DB.begin() as db:
        db.get(Run, identity).status = 'Invalidated'
    assert client.get(url).status_code == 404
    assert not client.get(f'/api/cases/{case}/runs').json()[0]['preliminary_report_available']


def test_automatic_report_and_source_deletion(client):
    from test_platform import prepare, run_case
    case, upload = prepare(client)
    run = run_case(client, case)
    assert run['preliminary_report_available']
    url = f'/api/runs/{run["id"]}/preliminary-report'
    report = client.get(url)
    assert report.status_code == 200
    assert 'Ranked hypotheses' in report.text
    assert run['id'] in report.text
    assert 'deterministic evidence-review-v1' in report.text
    first = report.content
    assert client.post(url, json={}).status_code == 200
    assert client.get(url).content == first
    case_data = client.get(f'/api/cases/{case}').json()
    assert client.request('DELETE', f'/api/uploads/{upload}', json={'revision':case_data['revision'], 'confirm':True}).status_code == 200
    assert client.get(url).status_code == 404


def test_report_reads_info_counters_only_from_pinned_reached_files(client):
    from cpe.db import File, Event, Upload
    from cpe.evidence import citation
    case = create(client, '<script>unsafe</script>')
    with DB.begin() as db:
        u = Upload(case_id=case, name='captured.zip', roles=['nfs_logs'], size=10, status='Ready')
        db.add(u); db.flush()
        f = File(case_id=case, upload_id=u.id, path='product.log', sha256='a'*64, size=10, lines=3, roles=['nfs_logs'])
        db.add(f); db.flush()
        events=[]
        for line,text in enumerate(['ERROR certificate /cert/server.crt: no such file', 'INFO Statistics Metric Data [requests=103, failed requests= 7] failed_requests(status_code_500)=7', 'INFO Metric Data [requests=134, failed requests= 0] successfully authenticated'],1):
            e=Event(case_id=case,file_id=f.id,line=line,byte_start=line,byte_end=line+1,timestamp='',severity='INFO',message=text)
            db.add(e); events.append(e)
        db.flush()
        ref=citation(events[0],f)
        run=Run(case_id=case,revision=1,evidence_ids=[u.id],config={},components=['test'],status='Findings Ready',digest='test',stages=[dict(component='test',stage='Product log analysis',outcome='Failures found',detail='Captured product file',evidence=[ref])])
        db.add(run); db.flush(); rid=run.id
        # Unpinned sibling upload in the same case must not be read.
        other=Upload(case_id=case,name='later.zip',roles=['nfs_logs'],size=10,status='Ready')
        db.add(other); db.flush()
        f2=File(case_id=case,upload_id=other.id,path='later.log',sha256='b'*64,size=10,lines=1,roles=['nfs_logs'])
        db.add(f2); db.flush()
        db.add(Event(case_id=case,file_id=f2.id,line=1,byte_start=0,byte_end=1,timestamp='',severity='ERROR',message='EXCLUDED_LATER_EVIDENCE'))
    url=f'/api/runs/{rid}/preliminary-report'
    assert client.post(url,json={}).status_code==200
    report=client.get(url).text
    assert '7 failed of 103' in report and '0 failed of 134' in report
    assert 'Transient application processing' in report
    assert 'EXCLUDED_LATER_EVIDENCE' not in report
    assert '<script>unsafe</script>' not in report
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in report
    import re
    anchors=set(re.findall(r'id="(e\d+)"',report))
    assert set(re.findall(r'href="#(e\d+)"',report)) <= anchors


def test_mapped_file_without_error_citations_is_reviewed(client):
    from test_platform import prepare, run_case
    from cpe.preliminary import generate_preliminary
    from cpe.storage import artifact_path
    from cpe.db import File, Event
    case, upload = prepare(client)
    run = run_case(client, case)
    with DB.begin() as db:
        current = db.get(Run, run['id'])
        file = File(case_id=case, upload_id=upload, path='mapped/newer.log', sha256='c'*64, size=100, lines=1, roles=['nfs_logs'])
        db.add(file); db.flush()
        db.add(Event(case_id=case, file_id=file.id, line=1, byte_start=0, byte_end=100, timestamp='', severity='INFO', message='Metric Data [requests=103, failed requests= 7] failed_requests(status_code_500)=7'))
        db.flush()
        current.stages = current.stages + [dict(component='demo.processor',stage='NFS log discovery',outcome='Mapped with config hints',detail='Matched mapped/newer.log. Confirm that configured archive prefixes correspond to the captured mount.',evidence=[])]
        artifact_path('preliminary-reports', current.id).unlink()
        generate_preliminary(db, current)
    assert '7 failed of 103' in client.get(f'/api/runs/{run["id"]}/preliminary-report').text
