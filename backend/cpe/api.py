import csv
import base64
import hashlib
import io
import json
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from datetime import datetime, timezone
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, or_, delete
from .config import settings
from .db import DB, User, Session, Case, Membership, Upload, File, Event, Job, Run, Message, Knowledge, Audit, audit, serialize
from .security import current_user, authorized_case, require_role, token_hash, hash_password, verify_password
from .storage import artifact_path, sha256_file, redact
from .evidence import active_files, citation, health, validate_citations
from .investigation import readiness, validate_config, digest_run, has_placeholder
from .providers import describe_provider
from .reports import render_report
from .preliminary import load_preliminary, generate_preliminary

app = FastAPI(title="CPE Evidence API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
Actor = Annotated[User, Depends(current_user)]
login_attempts = defaultdict(deque)
ROLES = {"nfs_logs", "pod_descriptions", "cluster_snapshot", "service_inventory", "investigation_config", "kubernetes_pod_logs", "supplemental"}


def canonical_time(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("Timezone required")
        return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except ValueError:
        raise HTTPException(422, "Use an ISO timestamp with timezone")


@app.middleware("http")
async def security_headers(request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin != settings.origin:
            return Response("Untrusted origin", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = secrets.token_hex(8)
    return response


@app.get("/api/health")
def healthcheck():
    with DB() as db:
        db.execute(select(1))
    return {"status": "ok", "version": "0.1.0"}


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=512)


@app.post("/api/auth/login")
def login(body: Login, request: Request, response: Response):
    key = (request.client.host if request.client else "unknown", body.email.lower())
    attempts = login_attempts[key]
    while attempts and attempts[0] < time.time() - 900:
        attempts.popleft()
    if len(attempts) >= 10:
        raise HTTPException(429, "Too many attempts; retry in 15 minutes")
    attempts.append(time.time())
    with DB.begin() as db:
        user = db.scalar(select(User).where(User.email == body.email.lower(), User.enabled == True))
        if not user or not verify_password(body.password, user.password):
            raise HTTPException(401, "Invalid credentials")
        attempts.clear()
        token, csrf = secrets.token_urlsafe(32), secrets.token_hex(24)
        db.add(Session(user_id=user.id, token_hash=token_hash(token), csrf=csrf, expires=time.time()+settings.session_hours*3600))
        audit(db, user.id, "", "login")
        response.set_cookie("cpe_session", token, httponly=True, secure=settings.secure_cookies,
                            samesite="strict", max_age=settings.session_hours*3600, path="/")
        return {"user": {"id": user.id, "email": user.email, "role": user.role}, "csrf": csrf}


@app.get("/api/auth/me")
def me(request: Request, user: Actor):
    return {"user": {"id": user.id, "email": user.email, "role": user.role}, "csrf": getattr(request.state, "csrf", "")}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user: Actor):
    with DB.begin() as db:
        db.execute(delete(Session).where(Session.token_hash == token_hash(request.cookies.get("cpe_session", ""))))
    response.delete_cookie("cpe_session")
    return {"ok": True}


class UserInput(Login):
    role: str = "viewer"


@app.post("/api/admin/users")
def add_user(body: UserInput, user: Actor):
    require_role(user, "admin")
    if body.role not in {"admin", "investigator", "reviewer", "viewer"} or len(body.password) < 12:
        raise HTTPException(422, "Choose a valid role and password of at least 12 characters")
    with DB.begin() as db:
        if db.scalar(select(User).where(User.email == body.email.lower())):
            raise HTTPException(409, "Email already exists")
        new = User(email=body.email.lower(), password=hash_password(body.password), role=body.role)
        db.add(new)
        db.flush()
        audit(db, user.id, "", "user_created", {"user_id": new.id, "role": new.role})
        return {"id": new.id, "email": new.email, "role": new.role}


@app.get("/api/admin/users")
def users(user: Actor):
    require_role(user, "admin")
    with DB() as db:
        return [{"id": u.id, "email": u.email, "role": u.role} for u in db.scalars(select(User))]


class CaseInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    customer: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=10000)
    severity: str = "Medium"
    incident_start: str = ""
    incident_end: str = ""
    timezone: str = "UTC"

    @field_validator("incident_start", "incident_end")
    @classmethod
    def validate_time(cls, value):
        return canonical_time(value)


@app.post("/api/cases", status_code=201)
def create_case(body: CaseInput, user: Actor):
    require_role(user, "investigator", "reviewer")
    with DB.begin() as db:
        case = Case(owner_id=user.id, **body.model_dump())
        db.add(case)
        db.flush()
        audit(db, user.id, case.id, "case_created")
        return serialize(case)


@app.get("/api/cases")
def list_cases(user: Actor):
    with DB() as db:
        q = select(Case)
        if user.role != "admin":
            q = q.where(or_(Case.owner_id == user.id, Case.id.in_(select(Membership.case_id).where(Membership.user_id == user.id))))
        return [serialize(c) for c in db.scalars(q.order_by(Case.created.desc()).limit(500))]


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, user: Actor):
    with DB() as db:
        case = authorized_case(db, user, case_id)
        return {**serialize(case), "readiness": readiness(db, case)}


class Intake(BaseModel):
    revision: int
    config: dict
    components: list[str] = Field(max_length=200)


@app.put("/api/cases/{case_id}/intake")
def save_intake(case_id: str, body: Intake, user: Actor):
    try:
        validate_config(body.config)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if len(json.dumps(body.config)) > 1024*1024:
        raise HTTPException(413, "Configuration too large")
    with DB.begin() as db:
        case = authorized_case(db, user, case_id, True)
        db.refresh(case, with_for_update=True)
        if case.revision != body.revision:
            raise HTTPException(409, "Case changed; reload before saving")
        case.config, case.components = body.config, body.components
        case.revision += 1
        audit(db, user.id, case_id, "intake_updated", {"revision": case.revision})
        return serialize(case)


class MemberInput(BaseModel):
    user_id: str


@app.post("/api/cases/{case_id}/members")
def add_member(case_id: str, body: MemberInput, user: Actor):
    with DB.begin() as db:
        case = authorized_case(db, user, case_id, True)
        if user.role != "admin" and case.owner_id != user.id:
            raise HTTPException(403, "Only case owner or administrator may share a case")
        if not db.get(User, body.user_id):
            raise HTTPException(404, "User not found")
        if not db.scalar(select(Membership).where(Membership.case_id == case_id, Membership.user_id == body.user_id)):
            db.add(Membership(case_id=case_id, user_id=body.user_id))
        audit(db, user.id, case_id, "member_added", {"user_id": body.user_id})
    return {"ok": True}


class UploadInput(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    size: int = Field(gt=0)
    roles: list[str] = Field(min_length=1)


@app.post("/api/cases/{case_id}/uploads", status_code=201)
def create_upload(case_id: str, body: UploadInput, user: Actor):
    if body.size > settings.max_upload_bytes:
        raise HTTPException(413, "Upload exceeds configured byte limit")
    if set(body.roles) - ROLES:
        raise HTTPException(422, "Invalid evidence role")
    with DB.begin() as db:
        authorized_case(db, user, case_id, True)
        upload = Upload(case_id=case_id, **body.model_dump())
        db.add(upload)
        db.flush()
        audit(db, user.id, case_id, "upload_started", {"upload_id": upload.id})
        return {**serialize(upload), "chunk_bytes": settings.chunk_bytes}


@app.put("/api/uploads/{upload_id}/chunk")
async def upload_chunk(upload_id: str, offset: int, request: Request, user: Actor):
    data = bytearray()
    async for block in request.stream():
        data.extend(block)
        if len(data) > settings.chunk_bytes:
            raise HTTPException(413, "Chunk too large")
    if not data:
        raise HTTPException(422, "Empty chunk")
    with DB.begin() as db:
        upload = db.scalar(select(Upload).where(Upload.id == upload_id).with_for_update())
        if not upload or upload.deleted:
            raise HTTPException(404, "Upload unavailable")
        authorized_case(db, user, upload.case_id, True)
        if upload.status != "Uploading" or upload.offset != offset:
            raise HTTPException(409, f"Resume at offset {upload.offset}")
        if offset + len(data) > upload.size:
            raise HTTPException(413, "Chunk exceeds declared size")
        path = artifact_path("uploads", upload_id)
        with path.open("r+b" if path.exists() else "wb") as output:
            output.seek(offset)
            output.write(data)
            output.truncate()
        upload.offset += len(data)
        return {"offset": upload.offset}


@app.post("/api/uploads/{upload_id}/complete", status_code=202)
def complete_upload(upload_id: str, user: Actor):
    with DB.begin() as db:
        upload = db.scalar(select(Upload).where(Upload.id == upload_id).with_for_update())
        if not upload or upload.deleted:
            raise HTTPException(404, "Upload not found")
        case = authorized_case(db, user, upload.case_id, True)
        if upload.status != "Uploading":
            return serialize(upload)
        if upload.offset != upload.size:
            raise HTTPException(409, "Upload is incomplete")
        upload.sha256 = sha256_file(artifact_path("uploads", upload.id))
        upload.status = "Queued"
        db.add(Job(case_id=case.id, kind="ingest", target_id=upload.id))
        case.revision += 1
        audit(db, user.id, case.id, "upload_completed", {"upload_id": upload.id, "sha256": upload.sha256})
        return serialize(upload)


@app.get("/api/cases/{case_id}/uploads")
def uploads(case_id: str, user: Actor):
    with DB() as db:
        authorized_case(db, user, case_id)
        return [serialize(u) for u in db.scalars(select(Upload).where(Upload.case_id == case_id).order_by(Upload.created.desc()))]


@app.get("/api/cases/{case_id}/files")
def files(case_id: str, user: Actor):
    with DB() as db:
        authorized_case(db, user, case_id)
        return [serialize(f) for f in active_files(db, case_id)]


@app.get("/api/cases/{case_id}/dashboard")
def dashboard(case_id: str, user: Actor):
    with DB() as db:
        case = authorized_case(db, user, case_id)
        fs = active_files(db, case_id)
        by_id = {f.id: f for f in fs}
        recent = db.scalars(select(Event).where(Event.file_id.in_(by_id), Event.severity.in_(["ERROR", "WARN"]))
                            .order_by(Event.timestamp.desc(), Event.id.desc()).limit(25))
        return {**health(db, case_id), "recent": [citation(e, by_id[e.file_id]) for e in recent],
                "readiness": readiness(db, case), "file_count": len(fs), "bytes": sum(f.size for f in fs),
                "provider": describe_provider()}


def search_query(db, case_id, q="", file_id="", severity="", start="", end="", after=0):
    start, end = canonical_time(start), canonical_time(end)
    fs = {f.id: f for f in active_files(db, case_id)}
    query = select(Event).where(Event.case_id == case_id, Event.file_id.in_(fs), Event.id > after)
    if file_id:
        query = query.where(Event.file_id == file_id)
    if q:
        query = query.where(Event.message.ilike("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"))
    if severity:
        query = query.where(Event.severity == severity)
    if start:
        query = query.where(Event.timestamp >= start)
    if end:
        query = query.where(Event.timestamp <= end)
    return query.order_by(Event.id), fs


@app.get("/api/cases/{case_id}/search")
def search(case_id: str, user: Actor, q: str = "", file_id: str = "", severity: str = "", start: str = "", end: str = "", after: int = 0, limit: int = 100):
    with DB() as db:
        authorized_case(db, user, case_id)
        limit = min(max(limit, 1), 500)
        query, fs = search_query(db, case_id, q[:500], file_id, severity, start, end, after)
        rows = list(db.scalars(query.limit(limit+1)))
        return {"items": [citation(e, fs[e.file_id]) for e in rows[:limit]], "next": rows[limit-1].id if len(rows) > limit else None}


@app.get("/api/files/{file_id}/content")
def file_content(file_id: str, user: Actor, line: int = 1, limit: int = 100):
    with DB() as db:
        f = db.get(File, file_id)
        if not f:
            raise HTTPException(404, "File not found")
        authorized_case(db, user, f.case_id)
        if f.id not in {x.id for x in active_files(db, f.case_id)}:
            raise HTTPException(410, "Evidence no longer available")
        rows = db.scalars(select(Event).where(Event.file_id == f.id, Event.line >= max(1, line)).order_by(Event.line).limit(min(max(limit,1),500)))
        return {"file": serialize(f), "items": [citation(e, f) for e in rows]}


@app.get("/api/cases/{case_id}/timeline")
def timeline(case_id: str, user: Actor, cursor: str = "", severity: str = "", limit: int = 100):
    with DB() as db:
        authorized_case(db,user,case_id)
        fs={f.id:f for f in active_files(db,case_id)}
        q=select(Event).where(Event.case_id==case_id,Event.file_id.in_(fs),Event.timestamp!="")
        if severity:
            q=q.where(Event.severity==severity)
        if cursor:
            try:
                stamp,identity=json.loads(base64.urlsafe_b64decode(cursor))
                if not isinstance(stamp,str) or not isinstance(identity,int):raise ValueError()
            except Exception:
                raise HTTPException(422,"Invalid timeline cursor")
            q=q.where(or_(Event.timestamp>stamp,(Event.timestamp==stamp)&(Event.id>identity)))
        limit=min(max(limit,1),200)
        rows=list(db.scalars(q.order_by(Event.timestamp,Event.id).limit(limit+1)))
        unknown=db.scalar(select(func.count()).select_from(Event).where(Event.case_id==case_id,Event.file_id.in_(fs),Event.timestamp==""))
        next_cursor=base64.urlsafe_b64encode(json.dumps([rows[limit-1].timestamp,rows[limit-1].id]).encode()).decode() if len(rows)>limit else None
        return {"items":[citation(e,fs[e.file_id]) for e in rows[:limit]],"next":next_cursor,"unknown_timestamp_records":unknown,
                "ordering":"UTC as parsed; no clock-skew correction assumed. Unknown timestamps excluded from chronological order."}


@app.get("/api/cases/{case_id}/compare")
def compare_uploads(case_id:str,left:str,right:str,user:Actor):
    with DB() as db:
        authorized_case(db,user,case_id)
        for upload_id in [left,right]:
            u=db.get(Upload,upload_id)
            if not u or u.case_id!=case_id or u.deleted or u.status!="Ready":
                raise HTTPException(404,"Comparable upload unavailable")
        a={f.path:f for f in active_files(db,case_id,[left])}
        b={f.path:f for f in active_files(db,case_id,[right])}
        return {"left":left,"right":right,"added":sorted(set(b)-set(a)),"removed":sorted(set(a)-set(b)),
                "changed":[{"path":p,"left_file_id":a[p].id,"right_file_id":b[p].id,"left_hash":a[p].sha256,"right_hash":b[p].sha256} for p in sorted(set(a)&set(b)) if a[p].sha256!=b[p].sha256],
                "unchanged":sum(a[p].sha256==b[p].sha256 for p in set(a)&set(b))}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id:str,user:Actor):
    with DB.begin() as db:
        job=db.get(Job,job_id)
        if not job:raise HTTPException(404,"Job not found")
        authorized_case(db,user,job.case_id,True)
        if job.status not in {"Queued","Running"}:raise HTTPException(409,"Job is no longer active")
        job.status="Cancelled"
        if job.kind=="investigate":
            run=db.get(Run,job.target_id)
            if run.status!="Invalidated":run.status="Cancelled"
        else:
            upload=db.get(Upload,job.target_id)
            upload.status="Cancelled"
        audit(db,user.id,job.case_id,"job_cancelled",{"job_id":job.id})
        return {"ok":True}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id:str,user:Actor):
    with DB.begin() as db:
        job=db.get(Job,job_id)
        if not job:raise HTTPException(404,"Job not found")
        authorized_case(db,user,job.case_id,True)
        if job.status!="Failed":raise HTTPException(409,"Only failed jobs can be retried")
        if job.kind=="ingest":
            upload=db.get(Upload,job.target_id)
            if upload.deleted:raise HTTPException(409,"Evidence deleted")
            upload.status="Queued"
            upload.error=""
        else:
            run=db.get(Run,job.target_id)
            if run.status=="Invalidated":raise HTTPException(409,"Evidence invalidated")
            run.status="Queued"
        job.status,job.error,job.progress="Queued","","Retry requested"
        audit(db,user.id,job.case_id,"job_retry_requested",{"job_id":job.id})
        return {"ok":True}


@app.get("/api/cases/{case_id}/export")
def export(case_id: str, user: Actor, q: str = "", severity: str = "", file_id: str = "", start: str = "", end: str = "", format: str = "csv"):
    if format not in {"csv", "jsonl", "txt"}:
        raise HTTPException(422, "Unsupported export format")
    with DB() as db:
        authorized_case(db, user, case_id)
        audit(db, user.id, case_id, "filtered_export")
        db.commit()
    def stream():
        after = 0
        if format == "csv":
            yield "file,line,timestamp,severity,message\r\n"
        while True:
            with DB() as db:
                authorized_case(db, user, case_id)
                query, fs = search_query(db, case_id, q[:500], file_id, severity, start, end, after)
                rows = list(db.scalars(query.limit(500)))
                if not rows:
                    return
                output = io.StringIO()
                writer = csv.writer(output)
                for e in rows:
                    if format == "jsonl":
                        output.write(json.dumps(citation(e, fs[e.file_id])) + "\n")
                        continue
                    if format == "txt":
                        output.write(f"{fs[e.file_id].path}:{e.line} {e.message}\n")
                        continue
                    values = [fs[e.file_id].path, e.line, e.timestamp, e.severity, e.message]
                    writer.writerow(["'" + v if isinstance(v,str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values])
                after = rows[-1].id
                yield output.getvalue()
    return StreamingResponse(stream(), media_type={"csv":"text/csv", "jsonl":"application/x-ndjson", "txt":"text/plain"}[format],
                             headers={"Content-Disposition": f'attachment; filename="evidence.{format}"'})


class InvestigationInput(BaseModel):
    partial: bool = False
    question: str = Field(default="", max_length=10000)
    components: list[str] = Field(default_factory=list, max_length=200)


def enqueue_run(db, case, body):
    if has_placeholder(case.config):
        raise HTTPException(422, "Replace the sample example.processor configuration with the actual affected component in Intake.")
    check = readiness(db, case)
    if not check["ready"] and not body.partial:
        raise HTTPException(422, {"message": "Intake needs attention", "issues": check["issues"]})
    run = Run(case_id=case.id, revision=case.revision, config=case.config,
              components=body.components or case.components, partial=body.partial,
              evidence_ids=sorted({f.upload_id for f in active_files(db, case.id)}), question=redact(body.question), provider=settings.llm_provider)
    db.add(run)
    db.flush()
    db.add(Job(case_id=case.id, kind="investigate", target_id=run.id))
    case.status = "Analyzing"
    return run


@app.post("/api/cases/{case_id}/investigations", status_code=202)
def start_investigation(case_id: str, body: InvestigationInput, user: Actor):
    with DB.begin() as db:
        case = authorized_case(db, user, case_id, True)
        run = enqueue_run(db, case, body)
        audit(db, user.id, case_id, "investigation_started", {"run_id": run.id, "partial": body.partial})
        return serialize(run)


@app.get("/api/cases/{case_id}/runs")
def runs(case_id: str, user: Actor):
    with DB() as db:
        authorized_case(db, user, case_id)
        return [{**serialize(r), "preliminary_report_available": load_preliminary(r) is not None} for r in db.scalars(select(Run).where(Run.case_id == case_id).order_by(Run.created.desc()).limit(100))]


class ChatInput(InvestigationInput):
    intent: str = "explain"


@app.post("/api/cases/{case_id}/chat")
def chat(case_id: str, body: ChatInput, user: Actor):
    with DB.begin() as db:
        case = authorized_case(db, user, case_id, True)
        db.add(Message(case_id=case_id, role="user", text=redact(body.question)))
        if body.intent == "investigate":
            run = enqueue_run(db, case, body)
            text = "Investigation queued. I will follow Kubernetes checks → NFS logs → product failures → related services using this case's pinned evidence."
            run_id = run.id
        else:
            run = db.scalar(select(Run).where(Run.case_id == case_id, Run.status.in_(["Findings Ready", "Partial", "Awaiting Input", "Approved"])).order_by(Run.created.desc()))
            run_id = run.id if run else ""
            if run:
                relevant = [f for f in run.findings if any(word.lower() in json.dumps(f).lower() for word in body.question.split() if len(word)>3)]
                if relevant:
                    text = "\n\n".join(f["title"] + ": " + f["explanation"] + " Evidence: " + ", ".join(r["path"] + ":" + str(r["line"]) for r in f["evidence"]) for f in relevant[:4])
                else:
                    text = run.summary
                text += "\n\nCurrent stage: " + (run.stages[-1]["stage"] if run.stages else "Intake") + ". Gaps: " + ("; ".join(run.coverage.get("gaps", [])) or "No recorded intake gaps; causal confirmation still requires review.")
            else:
                text = "No completed investigation is available. Complete intake and choose Investigate to run the ordered workflow."
        db.add(Message(case_id=case_id, role="assistant", text=text, run_id=run_id))
        return {"text": text, "run_id": run_id}


@app.get("/api/cases/{case_id}/messages")
def messages(case_id: str, user: Actor):
    with DB() as db:
        authorized_case(db, user, case_id)
        return [serialize(m) for m in db.scalars(select(Message).where(Message.case_id == case_id).order_by(Message.created).limit(500))]


class ApprovalInput(BaseModel):
    digest: str


class FindingRevisionInput(BaseModel):
    digest: str
    summary: str = Field(max_length=20000)
    findings: list[dict] = Field(max_length=100)
    review_note: str = Field(min_length=1, max_length=4000)


@app.post("/api/runs/{run_id}/revisions", status_code=201)
def revise_findings(run_id: str, body: FindingRevisionInput, user: Actor):
    require_role(user, "reviewer")
    with DB.begin() as db:
        original = db.get(Run, run_id)
        if not original:
            raise HTTPException(404, "Run not found")
        case = authorized_case(db, user, original.case_id)
        db.refresh(case, with_for_update=True)
        db.refresh(original)
        if original.status not in {"Findings Ready", "Partial", "Awaiting Input", "Approved"} or original.digest != body.digest or original.revision != case.revision:
            raise HTTPException(409, "Original findings are stale or not reviewable")
        expected = {"id", "title", "classification", "explanation", "evidence", "counterevidence", "next_checks", "component"}
        for finding in body.findings:
            if set(finding) != expected or finding["classification"] not in {"Confirmed finding", "Probable cause", "Hypothesis", "Inconclusive"}:
                raise HTTPException(422, "Invalid finding fields or classification")
            if not all(isinstance(finding[k], str) for k in ["id", "title", "classification", "explanation", "component"]) or not all(isinstance(finding[k],list) for k in ["evidence","counterevidence","next_checks"]):
                raise HTTPException(422, "Invalid finding value types")
            if finding["classification"] != "Inconclusive" and not finding["evidence"]:
                raise HTTPException(422, "A supported claim requires source evidence")
            if any(not isinstance(item,str) for item in finding["next_checks"]):
                raise HTTPException(422, "Next checks must be text")
            try:
                validate_citations(db, case.id, finding["evidence"] + finding["counterevidence"], original.evidence_ids)
            except (ValueError, TypeError, AttributeError) as exc:
                raise HTTPException(422, "Invalid or unavailable evidence citation")
        new = Run(case_id=case.id, revision=original.revision, evidence_ids=original.evidence_ids,
            config=original.config, components=original.components, question=original.question, partial=original.partial,
            status="Findings Ready", stages=original.stages, findings=body.findings, provider=original.provider,
            coverage={**original.coverage, "review_parent":original.id,"review_note":redact(body.review_note),"reviewer_id":user.id}, summary=redact(body.summary))
        db.add(new); db.flush()
        new.digest = digest_run(new)
        generate_preliminary(db, new, user.id)
        case.status = "Under Review"
        audit(db,user.id,case.id,"findings_revised",{"parent_run":original.id,"run_id":new.id})
        return serialize(new)


@app.post("/api/runs/{run_id}/approve")
def approve(run_id: str, body: ApprovalInput, user: Actor):
    require_role(user, "reviewer")
    with DB.begin() as db:
        run = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if not run:
            raise HTTPException(404, "Run not found")
        case = authorized_case(db, user, run.case_id)
        db.refresh(case, with_for_update=True)
        if run.status not in {"Findings Ready", "Partial", "Awaiting Input", "Approved"} or case.revision != run.revision:
            raise HTTPException(409, "Run is stale or not reviewable; rerun after evidence changes")
        if run.status != "Approved" and not run.findings and run.coverage.get("gaps"):
            raise HTTPException(409, "Investigation is incomplete and has no findings to approve. Correct Intake and rerun.")
        if body.digest != run.digest or body.digest != digest_run(run):
            raise HTTPException(409, "Review payload changed")
        try:
            validate_citations(db, case.id, [r for f in run.findings for r in f["evidence"]], run.evidence_ids)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if run.status == "Approved":
            return {"report_url": f"/api/runs/{run.id}/report"}
        run.approved_by, run.approved_at = user.id, time.time()
        report = render_report(case, run, user.email)
        artifact_path("reports", run.id).write_text(report)
        run.report_hash = hashlib.sha256(report.encode()).hexdigest()
        run.status, case.status = "Approved", "Approved"
        audit(db, user.id, case.id, "findings_approved", {"run_id": run.id, "digest": run.digest})
        return {"report_url": f"/api/runs/{run.id}/report"}


@app.get("/api/runs/{run_id}/report", response_class=HTMLResponse)
def report(run_id: str, user: Actor):
    with DB() as db:
        run = db.get(Run, run_id)
        if not run:
            raise HTTPException(404, "Report not found")
        authorized_case(db, user, run.case_id)
        if run.status != "Approved":
            raise HTTPException(409, "Report requires current approved evidence")
        return HTMLResponse(artifact_path("reports", run.id).read_text(), headers={"Content-Disposition": f'attachment; filename="case-{run.case_id[:8]}.html"'})


@app.post("/api/runs/{run_id}/preliminary-report")
def create_preliminary_report(run_id: str, user: Actor):
    with DB.begin() as db:
        run = db.get(Run, run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        case = authorized_case(db, user, run.case_id, True)
        db.refresh(case, with_for_update=True)
        db.refresh(run)
        try:
            meta = generate_preliminary(db, run, user.id)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {"report_url": f"/api/runs/{run.id}/preliminary-report", "sha256": meta["sha256"]}


@app.get("/api/runs/{run_id}/preliminary-report", response_class=HTMLResponse)
def preliminary_report(run_id: str, user: Actor, download: bool = True):
    with DB.begin() as db:
        run = db.get(Run, run_id)
        if not run:
            raise HTTPException(404, "Report not found")
        authorized_case(db, user, run.case_id)
        saved = load_preliminary(run)
        if not saved:
            raise HTTPException(404, "Preliminary report unavailable")
        meta, body = saved
        audit(db, user.id, run.case_id, "preliminary_report_downloaded" if download else "preliminary_report_viewed",
              {"run_id": run.id, "sha256": meta["sha256"], "approved": False})
        return HTMLResponse(body, headers={
            "Content-Disposition": ('attachment' if download else 'inline') + f'; filename="preliminary-{run.id[:8]}.html"',
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        })


@app.post("/api/uploads/{upload_id}/deletion-preview")
def deletion_preview(upload_id: str, user: Actor):
    with DB() as db:
        upload = db.get(Upload, upload_id)
        if not upload:
            raise HTTPException(404, "Upload not found")
        case = authorized_case(db, user, upload.case_id, True)
        impacted = [r.id for r in db.scalars(select(Run).where(Run.case_id == case.id)) if upload_id in r.evidence_ids]
        return {"upload_id": upload_id, "revision": case.revision, "affected_runs": impacted, "recovery_days": settings.recovery_days,
                "warning": "Derived findings, conversations and reports will become unavailable immediately. Downloaded exports cannot be recalled."}


class DeleteInput(BaseModel):
    revision: int
    confirm: bool = False


@app.delete("/api/uploads/{upload_id}")
def delete_upload(upload_id: str, body: DeleteInput, user: Actor):
    with DB.begin() as db:
        upload = db.get(Upload, upload_id)
        if not upload:
            raise HTTPException(404, "Upload not found")
        case = authorized_case(db, user, upload.case_id, True)
        db.refresh(case, with_for_update=True)
        if not body.confirm or case.revision != body.revision:
            raise HTTPException(409, "Confirm the current deletion preview")
        upload.deleted, upload.deleted_at = True, time.time()
        for run in db.scalars(select(Run).where(Run.case_id == case.id)):
            if upload.id in run.evidence_ids:
                run.status, run.findings, run.stages, run.summary = "Invalidated", [], [], "Source evidence deleted"
                run.coverage = {}
                artifact_path("reports", run.id).unlink(missing_ok=True)
                artifact_path("preliminary-reports", run.id).unlink(missing_ok=True)
                artifact_path("preliminary-manifests", run.id).unlink(missing_ok=True)
                artifact_path("preliminary-history-v1", run.id).unlink(missing_ok=True)
        # Conservatively remove all conversational excerpts in the case.
        db.execute(delete(Message).where(Message.case_id == case.id))
        case.revision += 1
        case.status = "Collecting Evidence"
        audit(db, user.id, case.id, "archive_deleted", {"upload_id": upload_id})
        return {"ok": True}


@app.get("/api/cases/{case_id}/jobs")
def jobs(case_id: str, user: Actor):
    with DB() as db:
        authorized_case(db, user, case_id)
        return [serialize(j) for j in db.scalars(select(Job).where(Job.case_id == case_id).order_by(Job.created.desc()).limit(100))]


@app.get("/api/settings")
def get_settings(user: Actor):
    return {"llm": describe_provider(), "max_upload_bytes": settings.max_upload_bytes,
            "max_expanded_bytes": settings.max_expanded_bytes, "recovery_days": settings.recovery_days,
            "configuration": "Server environment or Docker secrets; credentials are never returned to the browser."}


class KnowledgeInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    content: dict


@app.get("/api/knowledge")
def knowledge(user: Actor):
    with DB() as db:
        return [serialize(k) for k in db.scalars(select(Knowledge).order_by(Knowledge.created.desc()).limit(100))]


@app.post("/api/knowledge")
def add_knowledge(body: KnowledgeInput, user: Actor):
    require_role(user, "reviewer")
    with DB.begin() as db:
        k = Knowledge(**body.model_dump(), author_id=user.id)
        db.add(k)
        db.flush()
        audit(db, user.id, "", "knowledge_revision_created", {"id": k.id})
        return serialize(k)


@app.get("/api/cases/{case_id}/audit")
def case_audit(case_id: str, user: Actor):
    with DB() as db:
        authorized_case(db, user, case_id)
        return [serialize(a) for a in db.scalars(select(Audit).where(Audit.case_id == case_id).order_by(Audit.created.desc()).limit(200))]
