import logging
import time
import shutil
from sqlalchemy import select, or_, delete
from .db import DB, Job, Upload, File, Event, Run
from .config import settings
from .ingestion import ingest
from .investigation import investigate
from .storage import artifact_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cpe.worker")


def process_once():
    with DB.begin() as db:
        job = db.scalar(select(Job).where(or_(Job.status == "Queued", (Job.status == "Running") & (Job.lease_until < time.time())))
                        .order_by(Job.created).with_for_update(skip_locked=True).limit(1))
        if not job:
            return False
        job.status = "Running"
        job.lease_until = time.time() + 300
        job.attempts += 1
        job_id, kind, target = job.id, job.kind, job.target_id
    def heartbeat(message):
        with DB.begin() as db:
            j = db.get(Job, job_id)
            if j.status == "Cancelled":
                raise ValueError("Job cancelled")
            j.progress = message[:500]
            j.lease_until = time.time() + 300
    try:
        {"ingest": ingest, "investigate": investigate}[kind](target, heartbeat)
        with DB.begin() as db:
            j = db.get(Job, job_id)
            if j.status != "Cancelled":
                j.status, j.progress = "Completed", "Completed"
    except Exception as exc:
        log.error("job_failed id=%s kind=%s error_type=%s", job_id, kind, type(exc).__name__)
        with DB.begin() as db:
            j = db.get(Job, job_id)
            if j.status == "Cancelled":
                return True
            j.status, j.error = "Failed", "Processing failed: " + type(exc).__name__ + ". Inspect input validation and retry."
            if kind == "investigate":
                run = db.get(Run, target)
                if run.status != "Invalidated":
                    run.status = "Failed"
    return True


def purge_due():
    with DB.begin() as db:
        uploads = list(db.scalars(select(Upload).where(Upload.deleted == True, Upload.status != "Purged",
                        Upload.deleted_at < time.time() - settings.recovery_days * 86400)))
        for u in uploads:
            for f in db.scalars(select(File).where(File.upload_id == u.id)):
                db.execute(delete(Event).where(Event.file_id == f.id))
                for kind in ("raw", "redacted"):
                    artifact_path(kind, f.id).unlink(missing_ok=True)
                f.metadata_json = {}
                f.path = "[purged]"
            artifact_path("uploads", u.id).unlink(missing_ok=True)
            u.status = "Purged"


if __name__ == "__main__":
    log.info("worker_started provider=%s", settings.llm_provider)
    while True:
        try:
            purge_due()
            if not process_once():
                time.sleep(1)
        except Exception as exc:
            log.error("worker_loop error_type=%s", type(exc).__name__)
            time.sleep(3)
