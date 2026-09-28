import io
import json
import tarfile
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from cpe.api import app
from cpe.config import settings
from cpe.db import DB, Event, Run, Upload
from cpe.worker import process_once
from cpe.storage import redact
from sample_bundle import CONFIG, zip_bytes, bundle_files


def create(client, title="Synthetic case"):
    r = client.post("/api/cases", json={"title":title,"customer":"Test customer"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def put_upload(client, case, data, name="bundle.zip", roles=None):
    u = client.post(f"/api/cases/{case}/uploads", json={"name":name,"size":len(data),"roles":roles or ["nfs_logs"]}).json()
    split = len(data)//2
    assert client.put(f'/api/uploads/{u["id"]}/chunk?offset=0', content=data[:split]).status_code == 200
    assert client.put(f'/api/uploads/{u["id"]}/chunk?offset=0', content=data[:split]).status_code == 409
    assert client.put(f'/api/uploads/{u["id"]}/chunk?offset={split}', content=data[split:]).status_code == 200
    assert client.post(f'/api/uploads/{u["id"]}/complete').status_code == 202
    process_once()
    return u["id"]


def prepare(client):
    case = create(client)
    upload = put_upload(client, case, zip_bytes())
    info = client.get(f"/api/cases/{case}").json()
    r=client.put(f"/api/cases/{case}/intake",json={"revision":info["revision"],"config":CONFIG,"components":["demo.processor"]})
    assert r.status_code == 200, r.text
    return case, upload


def run_case(client, case):
    r = client.post(f"/api/cases/{case}/investigations", json={})
    assert r.status_code == 202, r.text
    process_once()
    return client.get(f"/api/cases/{case}/runs").json()[0]


def test_end_to_end_citations_gate_report_and_delete(client):
    case, upload = prepare(client)
    dashboard = client.get(f"/api/cases/{case}/dashboard").json()
    assert dashboard["total"] == 2
    assert dashboard["counts"]["Healthy"] == 2
    run = run_case(client, case)
    assert run["status"] == "Findings Ready", run
    stages = run["stages"]
    assert stages[0]["stage"] == "Kubernetes checks"
    assert any(s["component"] == "demo.storage" for s in stages)
    assert any("no space" in f["title"].lower() for f in run["findings"])
    for f in run["findings"]:
        for ref in f["evidence"]:
            content = client.get(f'/api/files/{ref["file_id"]}/content?line={ref["line"]}&limit=1').json()
            assert content["items"][0]["excerpt"] == ref["excerpt"]
    assert client.get(f'/api/runs/{run["id"]}/report').status_code == 409
    assert client.post(f'/api/runs/{run["id"]}/approve',json={"digest":"wrong"}).status_code == 409
    assert client.post(f'/api/runs/{run["id"]}/approve',json={"digest":run["digest"]}).status_code == 200
    report=client.get(f'/api/runs/{run["id"]}/report')
    assert "no space left" in report.text and "<script" not in report.text
    preview=client.post(f"/api/uploads/{upload}/deletion-preview").json()
    assert client.request("DELETE",f"/api/uploads/{upload}",json={"revision":preview["revision"],"confirm":True}).status_code == 200
    assert client.get(f'/api/runs/{run["id"]}/report').status_code == 409
    assert client.get(f"/api/cases/{case}/search").json()["items"] == []
    assert client.get(f"/api/cases/{case}/runs").json()[0]["findings"] == []


@pytest.mark.parametrize("format", ["tar", "tar.gz"])
def test_tar_formats(client, format):
    b=io.BytesIO()
    with tarfile.open(fileobj=b,mode="w:gz" if format.endswith("gz") else "w") as archive:
        content=b"2026-09-25T10:00:00Z ERROR diagnostic example\n"
        info=tarfile.TarInfo("product.log");info.size=len(content)
        archive.addfile(info,io.BytesIO(content))
    case=create(client)
    put_upload(client,case,b.getvalue(),"logs."+format)
    assert len(client.get(f"/api/cases/{case}/search").json()["items"]) == 1


@pytest.mark.parametrize("name", ["../escape.log", "/absolute.log", "a/../../escape", "C:\\escape"])
def test_zip_traversal_rejected(client,name):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w") as z:z.writestr(name,"unsafe")
    case=create(client);put_upload(client,case,b.getvalue())
    uploads=client.get(f"/api/cases/{case}/uploads").json()
    assert uploads[0]["status"] == "Rejected"
    assert client.get(f"/api/cases/{case}/files").json() == []


def test_tar_symlink_rejected(client):
    b=io.BytesIO()
    with tarfile.open(fileobj=b,mode="w") as a:
        info=tarfile.TarInfo("link");info.type=tarfile.SYMTYPE;info.linkname="/etc/passwd";a.addfile(info)
    case=create(client);put_upload(client,case,b.getvalue(),"bad.tar")
    assert client.get(f"/api/cases/{case}/uploads").json()[0]["status"] == "Rejected"


def test_expansion_limit(client, monkeypatch):
    monkeypatch.setattr(settings,"max_expanded_bytes",10)
    case=create(client);put_upload(client,case,zip_bytes())
    assert client.get(f"/api/cases/{case}/uploads").json()[0]["status"] == "Rejected"


def test_case_isolation_role_csrf_origin(client):
    case, _=prepare(client)
    user=client.post("/api/admin/users",json={"email":"viewer@example.test","password":"Secure-test-password-123","role":"viewer"}).json()
    with TestClient(app) as outsider:
        result=outsider.post("/api/auth/login",json={"email":"viewer@example.test","password":"Secure-test-password-123"})
        outsider.headers["X-CSRF-Token"]=result.json()["csrf"]
        assert outsider.get(f"/api/cases/{case}").status_code == 404
        assert outsider.get(f"/api/cases/{case}/search").status_code == 404
        assert outsider.post("/api/cases",json={"title":"x","customer":"y"}).status_code == 403
        client.post(f"/api/cases/{case}/members",json={"user_id":user["id"]})
        assert outsider.get(f"/api/cases/{case}").status_code == 200
        assert outsider.post(f"/api/cases/{case}/investigations",json={"partial":True}).status_code == 403
    token=client.headers.pop("X-CSRF-Token")
    assert client.post("/api/cases",json={"title":"x","customer":"y"}).status_code == 403
    client.headers["X-CSRF-Token"]=token
    assert client.post("/api/cases",json={"title":"x","customer":"y"},headers={"Origin":"https://evil.example"}).status_code == 403


def test_incomplete_intake_stops_and_partial_stays_unknown(client):
    case=create(client)
    assert client.post(f"/api/cases/{case}/investigations",json={}).status_code == 422
    assert client.post(f"/api/cases/{case}/investigations",json={"partial":True}).status_code == 202
    process_once()
    assert client.get(f"/api/cases/{case}/dashboard").json()["total"] == 0


def test_stale_approval_and_config_concurrency(client):
    case,_=prepare(client);run=run_case(client,case)
    body={"revision":run["revision"],"config":CONFIG,"components":["demo.processor"]}
    assert client.put(f"/api/cases/{case}/intake",json=body).status_code == 200
    assert client.put(f"/api/cases/{case}/intake",json=body).status_code == 409
    assert client.post(f'/api/runs/{run["id"]}/approve',json={"digest":run["digest"]}).status_code == 409


def test_chat_uses_ordered_workflow(client):
    case,_=prepare(client)
    response=client.post(f"/api/cases/{case}/chat",json={"intent":"investigate","question":"Why did storage fail?"})
    assert response.status_code == 200
    process_once()
    run=client.get(f"/api/cases/{case}/runs").json()[0]
    assert run["stages"][0]["stage"] == "Kubernetes checks"
    response=client.post(f"/api/cases/{case}/chat",json={"intent":"explain","question":"storage"})
    assert "Evidence:" in response.json()["text"]


def test_secrets_redacted(client):
    case=create(client)
    put_upload(client,case,b'password=verysecret\nAuthorization: Bearer mysecret\n',"product.log")
    text=json.dumps(client.get(f"/api/cases/{case}/search").json())
    assert "verysecret" not in text and "mysecret" not in text


def test_csv_formula_neutralized(client):
    case=create(client)
    put_upload(client,case,b'=HYPERLINK("bad")\n',"product.log")
    assert "'=HYPERLINK" in client.get(f"/api/cases/{case}/export").text


def test_pagination_no_duplicate_events(client):
    case,_=prepare(client)
    a=client.get(f"/api/cases/{case}/search?limit=3").json()
    b=client.get(f'/api/cases/{case}/search?limit=3&after={a["next"]}').json()
    assert not set(e["event_id"] for e in a["items"]) & set(e["event_id"] for e in b["items"])


def test_reviewer_revision_preserves_original_and_requires_approval(client):
    case,_=prepare(client);original=run_case(client,case)
    client.post(f'/api/runs/{original["id"]}/approve',json={"digest":original["digest"]})
    r=client.post(f'/api/runs/{original["id"]}/revisions',json={"digest":original["digest"],"findings":original["findings"],"summary":"Reviewed observations; deeper cause remains unconfirmed.","review_note":"Clarified uncertainty"})
    assert r.status_code==201,r.text
    revised=r.json()
    assert revised["id"]!=original["id"] and revised["digest"]!=original["digest"]
    assert client.get(f'/api/runs/{revised["id"]}/report').status_code==409
    assert client.get(f'/api/runs/{original["id"]}/report').status_code==200


def test_time_range_export_consistency(client):
    case,_=prepare(client)
    params={"start":"2026-09-25T10:01:00Z","end":"2026-09-25T10:01:00Z"}
    items=client.get(f"/api/cases/{case}/search",params=params).json()["items"]
    assert items and all("10:01:00" in e["timestamp"] for e in items)
    data=client.get(f"/api/cases/{case}/export",params={**params,"format":"jsonl"}).text
    exported=[json.loads(line) for line in data.splitlines()]
    assert [e["event_id"] for e in items]==[e["event_id"] for e in exported]


def test_errors_after_first_3000_lines_are_found(client):
    files=bundle_files()
    files['nfs/storage.log']='2026-09-25T10:00:00Z INFO ordinary event\n'*3500 + files['nfs/storage.log']
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for name,content in files.items():z.writestr(name,content)
    case=create(client);put_upload(client,case,b.getvalue())
    c=client.get(f'/api/cases/{case}').json()
    client.put(f'/api/cases/{case}/intake',json={'revision':c['revision'],'config':CONFIG,'components':['demo.processor']})
    run=run_case(client,case)
    assert any('no space' in f['title'].lower() for f in run['findings'])


def test_cancelled_job_does_not_run(client):
    case,_=prepare(client)
    client.post(f'/api/cases/{case}/investigations',json={})
    job=client.get(f'/api/cases/{case}/jobs').json()[0]
    assert client.post(f'/api/jobs/{job["id"]}/cancel').status_code==200
    assert not process_once()
    assert client.get(f'/api/cases/{case}/runs').json()[0]['status']=='Cancelled'


def test_timeline_and_archive_comparison(client):
    case,first=prepare(client)
    second=put_upload(client,case,zip_bytes())
    comparison=client.get(f'/api/cases/{case}/compare',params={'left':first,'right':second}).json()
    assert comparison['unchanged']==8 and not comparison['changed']
    first_page=client.get(f'/api/cases/{case}/timeline?limit=2').json()
    second_page=client.get(f'/api/cases/{case}/timeline',params={'cursor':first_page['next'],'limit':2}).json()
    ids=[e['event_id'] for e in first_page['items']+second_page['items']]
    assert len(ids)==len(set(ids))
