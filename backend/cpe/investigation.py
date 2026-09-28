"""Server-enforced Kubernetes → mount → product → service traversal."""
import fnmatch
import hashlib
import json
import re
from sqlalchemy import select, func
from .db import DB, Run, Case, Event, Message
from .evidence import active_files, citation, validate_citations
from .providers import synthesize
from .config import settings
from .resolvers import objects, nfs_exports, service_mentioned, resolve_service, verified_pvc_nfs


REQUIRED_ROLES = {"nfs_logs", "pod_descriptions", "cluster_snapshot", "service_inventory", "kubernetes_pod_logs"}
INFRA = re.compile(r"\b(FailedMount|FailedScheduling|OOMKilled|DiskPressure|MemoryPressure|ImagePullBackOff|CrashLoopBackOff|NotReady)\b")


def has_placeholder(config):
    return any(isinstance(c, dict) and c.get("id") == "example.processor" and c.get("namespace") == "example"
               and c.get("pod_names") == ["processor-0"] for c in config.get("components", []))


def validate_config(config):
    if not isinstance(config, dict) or not isinstance(config.get("components"), list):
        raise ValueError("Config must contain a components list")
    if has_placeholder(config):
        raise ValueError("Replace example.processor with the actual component, namespace, pod names and log mappings in Intake.")
    if len(config["components"]) > 200:
        raise ValueError("At most 200 components per config")
    ids = set()
    for c in config["components"]:
        if not isinstance(c, dict) or not c.get("id") or not c.get("namespace"):
            raise ValueError("Every component requires id and namespace")
        if c["id"] in ids:
            raise ValueError("Duplicate component ID")
        ids.add(c["id"])
        for field in ["pod_names", "containers", "kubernetes_log_patterns", "product_log_patterns"]:
            if not isinstance(c.get(field, []), list) or any(not isinstance(v, str) for v in c.get(field, [])):
                raise ValueError(f"{field} must be a list of strings")
        if not c.get("pod_names"):
            raise ValueError("Provide explicit pod_names for this config adapter")
    return config


def readiness(db, case):
    files = active_files(db, case.id)
    present = {role for f in files for role in f.roles}
    issues = ["Missing " + role.replace("_", " ") for role in sorted(REQUIRED_ROLES - present)]
    try:
        validate_config(case.config)
    except ValueError as exc:
        issues.append(str(exc))
    ids = {c.get("id") for c in case.config.get("components", []) if isinstance(c, dict)}
    if not case.components:
        issues.append("Select at least one affected component")
    for c in case.components:
        if c not in ids:
            issues.append("Unmapped affected component: " + c)
    return {"ready": not issues, "issues": issues, "roles": sorted(present), "file_count": len(files), "revision": case.revision}


def digest_run(run):
    return hashlib.sha256(json.dumps({"findings": run.findings, "stages": run.stages, "coverage": run.coverage,
        "summary": run.summary, "revision": run.revision, "config": run.config, "provider": run.provider}, sort_keys=True).encode()).hexdigest()


def pvc_subpath_matches(events, mapping):
    volumes, volume, in_volumes = {}, None, False
    for event in events:
        line = event.message
        if line == "Volumes:":
            in_volumes = True
            continue
        if in_volumes:
            match = re.match(r"^  ([^ :]+):\s*$", line)
            if match:
                volume = match[1]
            elif line and not line[0].isspace():
                in_volumes = False
            elif volume and re.match(r"^\s*ClaimName:", line):
                volumes[volume] = line.split(":", 1)[1].strip()
    for event in events:
        match = re.search(r' from ([^ ]+) \(.*path="([^"]+)"', event.message)
        if match and volumes.get(match[1]) == mapping.get("pvc_claim") and match[2] == mapping.get("mount_subpath"):
            return True
    return False


def investigate(run_id, heartbeat=lambda _: None):
    with DB() as db:
        run = db.get(Run, run_id)
        case = db.get(Case, run.case_id)
        files = active_files(db, case.id, run.evidence_ids)
        config = run.config
        components = {c["id"]: c for c in config.get("components", []) if isinstance(c, dict) and c.get("id")}
        pending = list(run.components)
        case_id, revision, partial, question = case.id, run.revision, run.partial, run.question
        start, end = case.incident_start, case.incident_end
        run.status = "Running"
        db.commit()
    stages, findings, gaps, seen, refs_used = [], [], [], set(), set()
    file_map = {f.id: f for f in files}
    captured = objects(files)
    limit_hits = []
    verified_storage = []

    def events_for(selected, limit=3000, failures_only=False, record_limit=True):
        if not selected:
            return []
        with DB() as db:
            q = select(Event).where(Event.file_id.in_([f.id for f in selected]))
            if failures_only:
                q = q.where(Event.severity.in_(["ERROR", "WARN"]))
            # Include timestamp-unknown records, but disclose their ambiguity.
            if start:
                q = q.where((Event.timestamp >= start) | (Event.timestamp == ""))
            if end:
                q = q.where((Event.timestamp <= end) | (Event.timestamp == ""))
            result = list(db.scalars(q.order_by(Event.id).limit(limit + 1)))
            if len(result) > limit and record_limit:
                limit_hits.append({"files": [f.id for f in selected], "limit": limit, "failures_only": failures_only})
            return result[:limit]

    def refs(events):
        return [citation(e, file_map[e.file_id]) for e in events]

    def stage(component, name, outcome, detail, evidence=None):
        stages.append({"component": component, "stage": name, "outcome": outcome, "detail": detail, "evidence": evidence or []})
        with DB.begin() as db:
            current = db.get(Run, run_id)
            if current.status in {"Invalidated", "Cancelled"}:
                raise ValueError("Evidence revoked; cannot publish stage output")
            current.stages = list(stages)
        heartbeat(component + ": " + name)

    while pending and len(seen) < 30:
        component_id = pending.pop(0)
        if component_id in seen:
            continue
        seen.add(component_id)
        c = components.get(component_id)
        if not c:
            gaps.append("Configuration missing for " + component_id)
            stage(component_id, "Resolve component", "Awaiting input", gaps[-1])
            continue
        patterns = c.get("kubernetes_log_patterns", [])
        kube = [f for f in files if "kubernetes_pod_logs" in f.roles and
                (any(fnmatch.fnmatch(f.path, p) for p in patterns) if patterns else
                 any(p in f.path for p in c.get("pod_names", [])))]
        describes = [f for f in files if "pod_descriptions" in f.roles]
        # Seek each selected pod's description instead of truncating the combined file.
        selected_desc = []
        with DB() as db:
            headers = db.scalars(select(Event).where(Event.file_id.in_([f.id for f in describes]),
                               Event.message.like("Name:%")).order_by(Event.file_id, Event.line)).yield_per(500)
            anchors = [e for e in headers if e.message.split(":", 1)[1].strip() in c.get("pod_names", [])]
            for anchor in anchors:
                next_line = db.scalar(select(func.min(Event.line)).where(Event.file_id == anchor.file_id,
                                      Event.line > anchor.line, Event.message.like("Name:%")))
                q = select(Event).where(Event.file_id == anchor.file_id, Event.line >= anchor.line)
                if next_line is not None:
                    q = q.where(Event.line < next_line)
                block = list(db.scalars(q.order_by(Event.line).limit(3001)))
                namespaces = [e.message.split(":", 1)[1].strip() for e in block if e.message.startswith("Namespace:")]
                if namespaces and namespaces[0] == c["namespace"]:
                    selected_desc.extend(block[:3000])
                    if len(block) > 3000:
                        limit_hits.append({"file": anchor.file_id, "pod": component_id, "limit": 3000})
        runtime = events_for(kube)
        cluster = [f for f in files if "cluster_snapshot" in f.roles]
        infra = [e for e in events_for(kube, failures_only=True) + selected_desc if INFRA.search(e.message)]
        if not runtime or not selected_desc or not cluster:
            issue = f"{component_id}: Kubernetes gate lacks " + ", ".join(
                label for ok,label in [(bool(runtime), "mapped runtime logs"), (bool(selected_desc), "mapped pod description"), (bool(cluster), "cluster snapshot")] if not ok)
            gaps.append(issue)
            stage(component_id, "Kubernetes checks", "Insufficient evidence", issue, refs((runtime + selected_desc)[:2]))
            if not partial:
                continue
        elif infra:
            stage(component_id, "Kubernetes checks", "Issue detected", "Investigating pod failure mechanism; application evidence may explain its cause.", refs(infra[:5]))
            findings.append({"id": "finding-" + str(len(findings)+1), "title": f"{component_id}: Kubernetes failure signal",
                "classification": "Confirmed finding", "explanation": "Captured pod evidence contains a failure signal. This does not establish its initiating cause.",
                "evidence": refs(infra[:5]), "counterevidence": [], "next_checks": ["Correlate termination with resource history and product logs."], "component": component_id})
        else:
            stage(component_id, "Kubernetes checks", "No blocking issue found", "No configured infrastructure signature in retrieved evidence; this is not proof of five-day cluster health.", refs((runtime + selected_desc)[:2]))
        mount_events = [e for e in selected_desc if re.search(r"(/.*\sfrom\s|NFS|Path:|Server:|ClaimName:)", e.message)]
        # Require a configured NFS export to be present in captured volume evidence.
        observed_exports = {e.message.split(":",1)[1].strip() for e in selected_desc if re.match(r"^\s*Path:", e.message)}
        resolved_exports, mount_sources, mount_gaps = nfs_exports(c, captured)
        observed_exports |= resolved_exports
        if mount_sources:
            mount_events += [e for e in events_for([file_map[i] for i in mount_sources]) if any(term in e.message for term in ["mountPath", "claimName", "volumeName", '"path"'])][:10]
        gaps.extend(component_id + ": " + g for g in mount_gaps)
        claims = {e.message.split(":", 1)[1].strip() for e in selected_desc if re.match(r"^\s*ClaimName:", e.message)}
        mappings = [m for m in config.get("archive_path_mappings", []) if
                    m.get("nfs_export") in observed_exports or
                    (m.get("namespace") == c["namespace"] and m.get("pvc_claim") in claims
                     and m.get("mount_subpath") and pvc_subpath_matches(selected_desc, m))]
        for mapping in mappings:
            if not mapping.get("pvc_claim"):
                continue
            verified = verified_pvc_nfs(mapping, captured)
            if verified:
                verified_storage.append({"component": component_id, **verified})
                mount_events += events_for([file_map[i] for i in verified["source_file_ids"]], limit=10, record_limit=False)
            else:
                gaps.append(component_id + ": product files mapped using captured PVC/subpath and configured archive prefix; backing PV/NFS export not verified")
        if not mount_events or not mappings:
            gaps.append(component_id + ": supply mount/PVC/PV evidence and archive_path_mappings")
            stage(component_id, "NFS log discovery", "Awaiting input", gaps[-1], refs(mount_events[:5]))
            continue
        candidates = [f for f in files if "nfs_logs" in f.roles and
            any(fnmatch.fnmatch(f.path, p) or fnmatch.fnmatch(f.path.rsplit("/",1)[-1], p) for p in c.get("product_log_patterns", [])) and
            any(f.path.startswith(m.get("archive_prefix", "\0")) for m in mappings)]
        if not candidates:
            gaps.append(component_id + ": no product logs matched configured patterns and archive prefixes")
            stage(component_id, "NFS log discovery", "Awaiting input", gaps[-1], refs(mount_events[:5]))
            continue
        stage(component_id, "NFS log discovery", "Mapped with config hints", "Matched " + ", ".join(f.path for f in candidates[:15]) + ". Confirm that configured archive prefixes correspond to the captured mount.", refs(mount_events[:5]))
        stages[-1]["file_ids"] = [f.id for f in candidates]
        # Filter the whole indexed corpus first, instead of only scanning the first N log lines.
        errors = events_for(candidates, failures_only=True)
        contexts = []
        with DB() as db:
            for error in errors[:10]:
                contexts.extend(db.scalars(select(Event).where(Event.file_id==error.file_id, Event.line.between(max(1,error.line-3),error.line+3)).order_by(Event.line)))
        stage(component_id, "Product log analysis", "Failures found" if errors else "No signature found", f"Searched the indexed file set for warning/error records; retrieved {len(errors)} bounded matches and {len(contexts)} context lines. Unknown severity patterns may require additional searches.", refs(errors[:10]))
        if errors:
            for e in errors[:10]:
                if e.id in refs_used:
                    continue
                refs_used.add(e.id)
                text = e.message.lower()
                title = "Application failure recorded"
                if "no space left" in text:
                    title = "Storage write failed: no space left on device"
                elif "certificate" in text and ("expired" in text or "verify" in text):
                    title = "TLS certificate validation failed"
                elif "connection refused" in text:
                    title = "Dependency connection refused"
                elif "timeout" in text or "timed out" in text:
                    title = "Dependency request timed out"
                findings.append({"id": "finding-" + str(len(findings)+1), "title": title, "component": component_id,
                    "classification": "Confirmed finding", "explanation": "Observed failure mechanism in uploaded product logs. Its deeper cause remains a hypothesis until independently corroborated.",
                    "evidence": refs([e]), "counterevidence": [], "next_checks": ["Check preceding events, dependency health, and configuration changes within the incident window."]})
        service_files = [f for f in files if "service_inventory" in f.roles]
        services = []
        for f in service_files:
            data = f.metadata_json.get("structured", {})
            if isinstance(data, dict):
                for svc in data.get("items", []):
                    if svc.get("kind") == "Service":
                        services.append((svc, f))
        followed = False
        for svc, sf in services:
            meta, spec = svc.get("metadata", {}), svc.get("spec", {})
            service_name, namespace = meta.get("name", ""), meta.get("namespace", "default")
            if not service_name:
                continue
            hits = [e for e in errors if service_mentioned(e.message, svc, c["namespace"])]
            if not hits:
                continue
            resolution = resolve_service(svc, components, captured)
            targets = resolution["targets"]
            service_lines = events_for([sf])
            mapping_refs = refs([e for e in service_lines if service_name in e.message][:2])
            backend_names = [p for target in targets for p in components[target].get("pod_names", [])]
            mapping_refs += refs([e for e in events_for([file_map[i] for i in resolution["sources"]]) if any(name in e.message for name in backend_names)][:4])
            if len(targets) == 1:
                target = targets[0]
                stage(component_id, "Related service", resolution["status"], f"{service_name}.{namespace} → {target}. {resolution['detail']}. Capture-time mappings may differ from earlier incident state.", refs(hits[:2]) + mapping_refs)
                if target not in seen:
                    pending.append(target)
                followed = True
            else:
                gaps.append(f"Resolve service {service_name}.{namespace} to an unambiguous configured component")
        if errors and not followed:
            stage(component_id, "Related service", "No verified next hop", "No additional uniquely config-mapped service could be followed. This does not rule out external dependencies.")
    if pending:
        gaps.append("Traversal stopped at 30 components; remaining components not assessed")
    if not seen:
        gaps.append("No configured affected component was selected")
    coverage = {"files_available": len(files), "components_visited": sorted(seen), "gaps": gaps,
                "verified_storage": verified_storage, "bounded_retrieval": limit_hits, "unknown_timestamp_policy": "Included without claiming exact chronology",
                "parser": "lines-v1", "engine": "ordered-triage-v1", "root_cause_confirmed": False}
    with DB() as db:
        if db.get(Run, run_id).status in {"Invalidated", "Cancelled"}:
            return
    try:
        summary = ("Investigation incomplete: the selected component could not be fully assessed because evidence or mappings are missing. "
                   "No root-cause or health conclusion is available. Review the missing evidence and correct Intake before rerunning."
                   if gaps and not findings else synthesize(findings, question))
    except Exception:
        summary = "Model synthesis unavailable. Deterministic findings and citations remain available; check model configuration and connectivity."
        coverage["model_error"] = True
    with DB.begin() as db:
        run = db.get(Run, run_id)
        if run.status in {"Invalidated", "Cancelled"}:
            return
        current_case = db.get(Case, case_id)
        db.refresh(current_case, with_for_update=True)
        current_files = active_files(db, case_id, run.evidence_ids)
        if {f.id for f in current_files} != set(file_map):
            run.status = "Invalidated"
            run.findings, run.stages, run.summary = [], [], "Evidence changed or was deleted; rerun required."
            return
        validate_citations(db, case_id, [r for f in findings for r in f["evidence"]], run.evidence_ids)
        run.findings, run.stages, run.coverage, run.summary = findings, stages, coverage, summary
        run.status = "Awaiting Input" if gaps and not partial else "Partial" if gaps or limit_hits else "Findings Ready"
        run.digest = digest_run(run)
        if current_case.revision == revision:
            current_case.status = run.status
        db.add(Message(case_id=case_id, role="assistant", text=summary, run_id=run.id))

        from .preliminary import generate_preliminary
        generate_preliminary(db, run)
