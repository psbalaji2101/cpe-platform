from collections import Counter
from sqlalchemy import select
from .db import File, Event, Upload


def active_files(db, case_id, upload_ids=None):
    query = select(File).join(Upload, Upload.id == File.upload_id).where(
        File.case_id == case_id, Upload.deleted == False, Upload.status == "Ready")
    if upload_ids is not None:
        query = query.where(Upload.id.in_(upload_ids))
    return list(db.scalars(query))


def citation(event, file):
    return {"event_id": event.id, "file_id": file.id, "upload_id": file.upload_id, "path": file.path,
            "sha256": file.sha256, "line": event.line, "byte_start": event.byte_start, "byte_end": event.byte_end,
            "timestamp": event.timestamp, "severity": event.severity, "excerpt": event.message}


def health(db, case_id):
    pods, products, capture = {}, [], []
    for f in active_files(db, case_id):
        data = f.metadata_json.get("structured", {})
        if not isinstance(data, dict):
            continue
        products.extend(data.get("products", []) if isinstance(data.get("products"), list) else [])
        if data.get("captured_at"):
            capture.append(data["captured_at"])
        items = data.get("items", data.get("pods", []))
        if data.get("kind") == "Pod":
            items = [data]
        for pod in items if isinstance(items, list) else []:
            if not isinstance(pod, dict) or (pod.get("kind") not in ("Pod", None)):
                continue
            m, s = pod.get("metadata", {}), pod.get("status", {})
            if not m.get("uid") or not ("phase" in s):
                continue
            phase = s.get("phase", "Unknown")
            containers = s.get("containerStatuses", [])
            all_containers = containers + s.get("initContainerStatuses", [])
            reasons = [v.get("reason") for c in all_containers for k,v in c.get("state", {}).items()
                       if k in {"waiting", "terminated"} and v.get("reason") not in (None, "Completed")]
            ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in s.get("conditions", []))
            state = "Failed" if phase == "Failed" else "Completed" if phase == "Succeeded" else "Degraded" if reasons else "Pending" if phase == "Pending" else "Healthy" if phase == "Running" and ready else "Unknown"
            row = {"uid": m["uid"], "name": m.get("name"), "namespace": m.get("namespace"), "state": state,
                   "phase": phase, "reasons": reasons, "restarts": sum(c.get("restartCount", 0) for c in all_containers),
                   "containers": all_containers, "file_id": f.id, "versions": [c.get("image") for c in containers]}
            key = (m.get("namespace"), m["uid"])
            if key in pods and pods[key]["state"] != state:
                row["state"] = "Unknown"
                row["reasons"] = ["Conflicting snapshots: select evidence and compare versions"]
            pods[key] = row
    counts = Counter(p["state"] for p in pods.values())
    return {"pods": list(pods.values()), "counts": dict(counts), "total": len(pods), "products": products,
            "capture_times": sorted(set(capture)), "scope": "Observed uploaded pod UIDs; not live cluster health"}


def validate_citations(db, case_id, refs, upload_ids):
    files = {f.id: f for f in active_files(db, case_id, upload_ids)}
    for ref in refs:
        e = db.get(Event, ref.get("event_id"))
        if not e or e.file_id not in files or e.case_id != case_id:
            raise ValueError("Evidence unavailable or outside the investigation scope")
        f = files[e.file_id]
        expected = citation(e, f)
        if any(ref.get(k) != expected[k] for k in ("file_id", "sha256", "line", "excerpt", "upload_id")):
            raise ValueError("Citation does not match source")
