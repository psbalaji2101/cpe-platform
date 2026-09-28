"""Audited operator import. Run inside API container with a JSON document on stdin.
Input: {html: string, evidence: {case_id, run_id, revision, evidence: [{file_id, sha256}]}}.
Imports an existing analyst-prepared report; does not generate or approve findings.
"""
import hashlib
import json
import sys
from cpe.db import DB, Run, File, Upload, audit
from cpe.storage import artifact_path

payload = json.load(sys.stdin)
evidence = payload['evidence']
body = payload['html'].encode('utf-8')
with DB.begin() as db:
    run = db.get(Run, evidence['run_id'])
    assert run and run.case_id == evidence['case_id'] and run.revision == evidence['revision']
    assert run.status != 'Invalidated'
    for ref in evidence['evidence']:
        file = db.get(File, ref['file_id'])
        assert file and file.case_id == run.case_id and file.sha256 == ref['sha256']
        upload = db.get(Upload, file.upload_id)
        assert upload and not upload.deleted and upload.id in run.evidence_ids
    meta = dict(case_id=run.case_id, run_id=run.id, revision=run.revision, run_digest=run.digest,
                sha256=hashlib.sha256(body).hexdigest(), source='Analyst-prepared preliminary report', approved=False)
    dest = artifact_path('preliminary-reports', run.id)
    if dest.exists():
        assert dest.read_bytes() == body, 'Immutable supplement already exists with different content'
    dest.write_bytes(body)
    artifact_path('preliminary-manifests', run.id).write_text(json.dumps(meta))
    audit(db, 'system:maintenance', run.case_id, 'preliminary_report_attached', meta)
    print(json.dumps(meta))
