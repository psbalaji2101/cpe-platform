"""Synthetic upload/indexing benchmark; not representative customer qualification."""
import json
import argparse
import tempfile
import time
import zipfile
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--mib',type=int,default=64)
parser.add_argument('--line-bytes',type=int,default=512)
args=parser.parse_args()
if not 1 <= args.mib <= 6144 or not 128 <= args.line_bytes <= 16384:
    raise SystemExit('Supported benchmark range: 1–6144 MiB, 128–16384 bytes per line')
env=dict(line.split('=',1) for line in (root/'.env').read_text().splitlines() if '=' in line)
with tempfile.TemporaryDirectory(prefix='cpe-benchmark-') as directory:
    bundle=Path(directory)/f'synthetic-{args.mib}MiB.zip'
    prefix='2026-09-25T10:00:00Z INFO synthetic benchmark event '
    line=(prefix+ 'x'*(args.line_bytes-len(prefix)-1)+'\n').encode()
    count=(args.mib*1024*1024)//len(line)
    with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_STORED) as archive:
        with archive.open('synthetic-benchmark.log','w',force_zip64=True) as output:
            for i in range(count):output.write(line)
    with httpx.Client(base_url=env.get('CPE_ORIGIN','http://localhost:8097'),timeout=120) as client:
        login=client.post('/api/auth/login',json={'email':env['CPE_ADMIN_EMAIL'],'password':env['CPE_ADMIN_PASSWORD']});login.raise_for_status()
        client.headers['X-CSRF-Token']=login.json()['csrf']
        response=client.post('/api/cases',json={'title':f'Benchmark · synthetic {args.mib} MiB','customer':'Synthetic performance test — no customer data'});response.raise_for_status();case=response.json()['id']
        response=client.post(f'/api/cases/{case}/uploads',json={'name':bundle.name,'size':bundle.stat().st_size,'roles':['nfs_logs']});response.raise_for_status();upload=response.json()
        start=time.perf_counter();offset=0
        with bundle.open('rb') as stream:
            while chunk:=stream.read(upload['chunk_bytes']):
                r=client.put(f'/api/uploads/{upload["id"]}/chunk?offset={offset}',content=chunk);r.raise_for_status();offset=r.json()['offset']
        client.post(f'/api/uploads/{upload["id"]}/complete').raise_for_status()
        upload_seconds=time.perf_counter()-start
        while time.perf_counter()-start<3600:
            status=client.get(f'/api/cases/{case}/uploads').json()[0]
            if status['status'] in ['Ready','Rejected']:break
            time.sleep(2)
        assert status['status']=='Ready',status.get('error','Timeout')
        total_seconds=time.perf_counter()-start
        files=client.get(f'/api/cases/{case}/files').json()
        assert sum(f['lines'] for f in files)==count
        before=time.perf_counter();r=client.get(f'/api/files/{files[0]["id"]}/content',params={'line':count-10,'limit':10});r.raise_for_status();window_seconds=time.perf_counter()-before
        assert len(r.json()['items'])==10
        result={'archive_bytes':bundle.stat().st_size,'expanded_bytes':count*len(line),'records':count,'record_bytes':len(line),'upload_seconds':round(upload_seconds,3),'ingestion_total_seconds':round(total_seconds,3),'tail_window_seconds':round(window_seconds,4),'archive':'ZIP_STORED','case_id':case,'scope':f'{args.mib} MiB synthetic single-file upload/index test. Repetitive synthetic records are not representative customer diagnostics or model analysis.'}
        (root/'docs'/f'ingestion-benchmark-{args.mib}MiB.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
