"""Smoke/concurrency check against the deployed API. Never prints credentials."""
import concurrent.futures
import json
import time
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
env=dict(line.split('=',1) for line in (root/'.env').read_text().splitlines() if '=' in line)
base=env.get('CPE_ORIGIN','http://localhost:8097')


def worker(_):
    elapsed=[]
    with httpx.Client(base_url=base,timeout=30) as client:
        r=client.post('/api/auth/login',json={'email':env['CPE_ADMIN_EMAIL'],'password':env['CPE_ADMIN_PASSWORD']})
        r.raise_for_status()
        client.headers['X-CSRF-Token']=r.json()['csrf']
        cases=client.get('/api/cases').json()
        case=next(c for c in cases if c['title'].startswith('Synthetic'))
        for endpoint in [f'/api/cases/{case["id"]}/dashboard',f'/api/cases/{case["id"]}/search?q=ERROR']*10:
            start=time.perf_counter();response=client.get(endpoint);response.raise_for_status();elapsed.append(time.perf_counter()-start)
        client.post('/api/auth/logout').raise_for_status()
    return elapsed


with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    groups=list(pool.map(worker,range(5)))
timings=sorted(x for group in groups for x in group)
result={'clients':5,'requests':len(timings),'errors':0,'p50_seconds':round(timings[len(timings)//2],4),
        'p95_seconds':round(timings[int(len(timings)*.95)-1],4),'scope':'Small synthetic dataset; not a 6 GB scale benchmark'}
(root/'docs'/'concurrency-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
