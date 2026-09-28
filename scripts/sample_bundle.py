"""Synthetic, labeled two-component incident. Contains no customer data."""
import io
import json
import tarfile
import zipfile
from pathlib import Path

CONFIG = {"schema_version": 1, "cluster_id": "synthetic-demo", "components": [
    {"id": "demo.processor", "namespace": "demo", "pod_names": ["processor-0"], "containers": ["processor"],
     "kubernetes_log_patterns": ["kubernetes/processor-0/*"], "product_log_patterns": ["processor*.log"],
     "service_refs": [{"namespace": "demo", "name": "processor"}]},
    {"id": "demo.storage", "namespace": "demo", "pod_names": ["storage-0"], "containers": ["storage"],
     "kubernetes_log_patterns": ["kubernetes/storage-0/*"], "product_log_patterns": ["storage*.log"],
     "service_refs": [{"namespace": "demo", "name": "storage-api"}]}],
    "archive_path_mappings": [{"nfs_export": "/customer-logs", "archive_prefix": "nfs/"}]}


def bundle_files():
    pods = [{"kind": "Pod", "metadata": {"name": name+"-0", "namespace": "demo", "uid": "synthetic-"+name,
             "labels": {"app": name}}, "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
             "containerStatuses": [{"name": name, "image": "demo/"+name+":1.0", "restartCount": 0, "ready": True, "state": {"running": {}}}]}}
            for name in ["processor", "storage"]]
    describe = "\n".join(f"Name: {name}-0\nNamespace: demo\nContainers:\n  {name}:\n    State: Running\n    Ready: True\n    Mounts:\n      /var/log/product from product-logs (rw)\nVolumes:\n  product-logs:\n    Type: NFS\n    Server: nfs.demo.internal\n    Path: /customer-logs\n" for name in ["processor", "storage"])
    return {
        "pod-descriptions.log": describe,
        "cluster-snapshot.json": json.dumps({"captured_at": "2026-09-25T10:10:00Z", "pods": pods,
            "products": [{"name": "Synthetic demonstration", "version": "1.0", "note": "Not actual OpsB/NOM/AIOM metadata"}]}, indent=2),
        "services.json": json.dumps({"kind": "List", "items": [{"kind": "Service", "metadata": {"name": "storage-api", "namespace": "demo"},
            "spec": {"clusterIP": "10.96.0.20", "ports": [{"port": 8080}], "selector": {"app": "storage"}}}]}, indent=2),
        "kubernetes/processor-0/current.log": "2026-09-25T10:00:00Z INFO processor running; readiness passed\n",
        "kubernetes/storage-0/current.log": "2026-09-25T10:00:00Z INFO storage running; readiness passed\n",
        "nfs/processor.log": "2026-09-25T10:01:00Z INFO request_id=demo-17 submitting batch\n2026-09-25T10:01:01Z ERROR request_id=demo-17 storage-api.demo.svc.cluster.local:8080 returned write failure\n",
        "nfs/storage.log": "2026-09-25T10:01:00Z ERROR request_id=demo-17 no space left on device; write failed for /data/batch\n2026-09-25T10:02:00Z WARN retry queue delayed\n",
        "investigation-config.json": json.dumps(CONFIG, indent=2)
    }


def zip_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in bundle_files().items():
            z.writestr(name, text)
    return buffer.getvalue()


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "samples"
    target.mkdir(exist_ok=True)
    (target / "synthetic-incident.zip").write_bytes(zip_bytes())
    (target / "investigation-config.json").write_text(json.dumps(CONFIG, indent=2))
    for mode, name in [("w", "synthetic-incident.tar"), ("w:gz", "synthetic-incident.tar.gz")]:
        with tarfile.open(target / name, mode) as archive:
            for path, text in bundle_files().items():
                content = text.encode()
                info = tarfile.TarInfo(path)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
    print("Created synthetic ZIP/TAR/TAR.GZ bundles and config in samples/.")
