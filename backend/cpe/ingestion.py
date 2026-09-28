"""Bounded archive readers and line-indexed, redacted evidence ingestion."""
import hashlib
import json
import re
import stat
import tarfile
import zipfile
from datetime import datetime, timezone
import yaml
from sqlalchemy import select, delete, insert
from .config import settings
from .db import DB, Upload, File, Event, uid
from .storage import artifact_path, safe_member, redact


def members(path, name):
    if name.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                safe_member(info.filename)
                mode = info.external_attr >> 16
                if info.flag_bits & 1 or stat.S_ISLNK(mode):
                    raise ValueError("Encrypted archives and symbolic links are not supported")
                if info.is_dir():
                    continue
                if mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                    raise ValueError("Unsupported archive entry type")
                with archive.open(info) as stream:
                    yield info.filename, stream
    elif name.lower().endswith((".tar", ".tar.gz", ".tgz")):
        with tarfile.open(path, "r|*") as archive:
            for info in archive:
                safe_member(info.name)
                if info.isdir():
                    continue
                if not info.isfile() or info.issparse():
                    raise ValueError("Links, devices, sparse and special TAR entries are forbidden")
                with archive.extractfile(info) as stream:
                    yield info.name, stream
    else:
        with open(path, "rb") as stream:
            yield name, stream


def infer_roles(path, roles):
    p = path.lower()
    inferred = []
    for needles, role in [(["describe", "description"], "pod_descriptions"),
                          (["snapshot", "pods.json", "nodes.json", "pvs.", "pvcs.", "persistentvolume", "charts"], "cluster_snapshot"),
                          (["services", "svc.", "endpointslice"], "service_inventory"),
                          (["investigation-config", "investigation_config"], "investigation_config"),
                          (["kubernetes/", "current.log", "previous.log"], "kubernetes_pod_logs")]:
        if any(n in p for n in needles):
            inferred.append(role)
    return sorted(set(inferred or roles))


def normalize_timestamp(line):
    match = re.search(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", line)
    if not match:
        return ""
    try:
        return datetime.fromisoformat(match[0].replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="microseconds")
    except ValueError:
        return ""


def severity(line):
    # Prefer explicit fields so message text cannot override a declared severity.
    match = re.search(r"\b(?:level|severity)[\"']?\s*[:=]\s*[\"']?(ERROR|FATAL|CRITICAL|WARN(?:ING)?|INFO|DEBUG|TRACE)\b", line, re.IGNORECASE)
    if not match:
        match = re.search(r"\b(ERROR|FATAL|CRITICAL|WARN(?:ING)?|INFO|DEBUG|TRACE)\b", line, re.IGNORECASE)
    if match:
        level = match[1].upper()
        return {"WARNING": "WARN", "FATAL": "ERROR", "CRITICAL": "ERROR"}.get(level, level)
    if re.search(r"(?:Exception|OOMKilled|CrashLoopBackOff|ImagePullBackOff|FailedMount|FailedScheduling|DiskPressure|MemoryPressure|NotReady)", line):
        return "ERROR"
    return "INFO"


def structured_metadata(path, roles):
    if path.stat().st_size > 10 * 1024**2:
        return {"structured_skipped": "File exceeds 10 MiB structured-parser limit"}
    if not set(roles) & {"cluster_snapshot", "service_inventory", "investigation_config"}:
        return {}
    try:
        text = path.read_text(errors="replace")
        # Reject aliases before construction/serialization, not after expansion.
        if any(isinstance(event, yaml.events.AliasEvent) for event in yaml.parse(text)):
            return {"structured_skipped": "YAML aliases are not supported in captured metadata"}
        value = yaml.safe_load(text)
        if isinstance(value, (dict, list)):
            # Reject alias-expanded documents that could explode persisted metadata.
            packed = json.dumps(value)
            if len(packed) > 10 * 1024**2:
                return {"structured_skipped": "Expanded metadata exceeds limit"}
            return {"structured": value}
    except (ValueError, yaml.YAMLError, RecursionError, TypeError):
        pass
    return {"structured_skipped": "Text input retained with source lines"}


def ingest(upload_id, heartbeat=lambda _: None):
    with DB() as db:
        upload = db.get(Upload, upload_id)
        if not upload or upload.deleted:
            return
        upload.status = "Processing"
        upload.error = ""
        # Deterministic reingestion clears unfinished output. No run can pin it until Ready.
        prior = list(db.scalars(select(File).where(File.upload_id == upload_id)))
        for f in prior:
            db.execute(delete(Event).where(Event.file_id == f.id))
            for kind in ["raw", "redacted"]:
                artifact_path(kind, f.id).unlink(missing_ok=True)
            db.delete(f)
        db.commit()
        case_id, name, roles = upload.case_id, upload.name, upload.roles
    total, count, seen = 0, 0, set()
    try:
        for name, stream in members(artifact_path("uploads", upload_id), name):
            clean = safe_member(name)
            if clean in seen:
                raise ValueError("Duplicate archive path")
            seen.add(clean)
            count += 1
            if count > settings.max_archive_files:
                raise ValueError("Archive file-count limit exceeded")
            file_id = uid()
            digest = hashlib.sha256()
            size = 0
            raw = artifact_path("raw", file_id)
            with raw.open("wb") as output:
                while block := stream.read(1024 * 1024):
                    total += len(block)
                    size += len(block)
                    if total > settings.max_expanded_bytes:
                        raise ValueError("Archive expanded-byte limit exceeded")
                    output.write(block)
                    digest.update(block)
                    if size % (16 * 1024**2) == 0:
                        heartbeat(f"Extracted {total:,} bytes")
            file_roles = infer_roles(clean, roles)
            with DB() as db:
                if db.get(Upload, upload_id).deleted:
                    raw.unlink(missing_ok=True)
                    return
                record = File(id=file_id, case_id=case_id, upload_id=upload_id, path=clean,
                              sha256=digest.hexdigest(), size=size, roles=file_roles)
                db.add(record)
                db.commit()
            batch, pos, number, oversized = [], 0, 0, 0
            nul_bytes = 0
            in_private_key = False
            with raw.open("rb") as source, artifact_path("redacted", file_id).open("w") as redacted:
                while line := source.readline(settings.max_record_bytes + 1):
                    start = pos
                    pos += len(line)
                    number += 1
                    long = len(line) > settings.max_record_bytes
                    if long:
                        oversized += 1
                        while line and not line.endswith(b"\n"):
                            line = source.readline(settings.max_record_bytes + 1)
                            pos += len(line)
                        text = "[OVERSIZED RECORD OMITTED: see coverage limitation]"
                    else:
                        nul_bytes += line.count(b"\x00")
                        # Keep raw bytes and offsets intact; make NUL visible in searchable text.
                        text = line.decode("utf-8", errors="replace").rstrip("\r\n").replace("\x00", "␀")
                    if "-----BEGIN" in text and "PRIVATE KEY-----" in text:
                        in_private_key = True
                    cleaned = "[PRIVATE KEY REDACTED]" if in_private_key else redact(text)
                    if "-----END" in text and "PRIVATE KEY-----" in text:
                        in_private_key = False
                    redacted.write(cleaned + "\n")
                    batch.append(dict(case_id=case_id, file_id=file_id, line=number, byte_start=start,
                                      byte_end=pos, timestamp=normalize_timestamp(text), severity=severity(text), message=cleaned))
                    if len(batch) >= 1000:
                        with DB.begin() as db:
                            db.execute(insert(Event), batch)
                        batch.clear()
                        heartbeat(f"Indexed {clean}: {number:,} lines")
            with DB.begin() as db:
                if batch:
                    db.execute(insert(Event), batch)
                record = db.get(File, file_id)
                record.lines = number
                record.metadata_json = {**structured_metadata(artifact_path("redacted", file_id), file_roles),
                                        "nul_bytes_rendered": nul_bytes, "nul_display": "␀ (U+2400); original bytes preserved",
                                        "oversized_records": oversized, "encoding": "UTF-8 with replacement", "parser": "lines-v1"}
            heartbeat(f"Indexed {count} files, {total:,} extracted bytes")
        with DB.begin() as db:
            upload = db.get(Upload, upload_id)
            if not upload.deleted and upload.status != "Cancelled":
                upload.status = "Ready"
                upload.error = ""
    except Exception as exc:
        with DB.begin() as db:
            upload = db.get(Upload, upload_id)
            if upload.status != "Cancelled":
                upload.status = "Rejected"
            upload.error = (str(exc)[:500] if isinstance(exc, ValueError) else
                            "Archive processing failed (" + type(exc).__name__ + "). Retry from Jobs after the issue is resolved.")
        raise
