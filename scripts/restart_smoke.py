"""Verify a synthetic case and approved report survive an application restart."""
import hashlib
import json
import subprocess
import time
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
env = dict(line.split('=', 1) for line in (root / '.env').read_text().splitlines() if '=' in line)
with httpx.Client(base_url=env.get('CPE_ORIGIN', 'http://localhost:8097'), timeout=30) as client:
    response = client.post('/api/auth/login', json={'email': env['CPE_ADMIN_EMAIL'], 'password': env['CPE_ADMIN_PASSWORD']})
    response.raise_for_status()
    cases = client.get('/api/cases').json()
    case = next(c for c in cases if c['title'].startswith('Synthetic'))
    files_before = client.get(f'/api/cases/{case["id"]}/files').json()
    runs = client.get(f'/api/cases/{case["id"]}/runs').json()
    run = next(r for r in runs if r['approved_at'])
    report_url = f'/api/runs/{run["id"]}/report'
    before = client.get(report_url)
    before.raise_for_status()
    digest = hashlib.sha256(before.content).hexdigest()
    subprocess.run(['docker', 'compose', 'restart', 'api', 'worker', 'web'], cwd=root, check=True)
    for _ in range(60):
        try:
            if client.get('/api/health').status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    response = client.get(f'/api/cases/{case["id"]}/files')
    response.raise_for_status()
    assert response.json() == files_before
    after = client.get(report_url)
    after.raise_for_status()
    assert hashlib.sha256(after.content).hexdigest() == digest
    result = {'session_survived': True, 'file_manifest_unchanged': True,
              'approved_report_sha256_unchanged': True, 'files': len(files_before),
              'scope': 'Application container restart; not database disaster recovery or interrupted-job recovery'}
    (root / 'docs' / 'restart-results.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
