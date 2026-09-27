"""Job lifecycle: explicit state machine plus `advance`, the single place that decides what runs next.

Pipeline (each arrow is a queued task; pages run in parallel, translation runs once per chapter for context):
  job.ingest → page.prepare ×N (detect, OCR, clean) → job.translate → page.render ×N → job.finalize
A page keeps its last completed stage, so retries resume there instead of repeating paid work.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DB

from . import app_settings, ledger, queue, storage
from . import models as m
from .errors import AppError
from .security import now

TERMINAL = {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "EXPIRED"}
TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"INGESTING", "FAILED", "CANCELLED"},
    "INGESTING": {"PROCESSING", "FAILED", "CANCELLED"},
    "PROCESSING": {"TRANSLATING", "RENDERING", "FINALIZING", "FAILED", "CANCELLED"},
    "TRANSLATING": {"RENDERING", "FINALIZING", "FAILED", "CANCELLED"},
    "RENDERING": {"FINALIZING", "FAILED", "CANCELLED"},
    "FINALIZING": {"COMPLETED", "PARTIAL", "FAILED"},
    "COMPLETED": {"EXPIRED"},
    "PARTIAL": {"PROCESSING", "EXPIRED"},  # retry of failed pages
    "FAILED": {"PENDING", "PROCESSING", "EXPIRED"},
    "CANCELLED": {"EXPIRED"},
    "EXPIRED": set(),
}


class InvalidTransition(Exception):
    pass


def transition(job: m.Job, to: str) -> None:
    if job.status == to:
        return
    if to not in TRANSITIONS[job.status]:
        raise InvalidTransition(f"{job.status} -> {to}")
    job.status = to
    if to in ("PROCESSING", "INGESTING") and not job.started_at:
        job.started_at = now()
    if to in TERMINAL:
        job.finished_at = now()


def lock(db: DB, job_id) -> m.Job:
    return db.execute(select(m.Job).where(m.Job.id == job_id).with_for_update()).scalar_one()


def advance(db: DB, job: m.Job) -> None:
    """Enqueue the next step for a job. Caller holds the job row lock and commits. Safe to call repeatedly."""
    if job.status in TERMINAL or job.status in ("PENDING", "INGESTING"):
        return
    gen = job.generation
    live = db.execute(select(m.Page).where(m.Page.job_id == job.id, m.Page.status.in_(("pending", "processing")))
                      .order_by(m.Page.index)).scalars().all()
    by_stage = {s: [p for p in live if p.stage == s] for s in ("none", "prepared", "translated")}

    if by_stage["none"]:
        transition(job, "PROCESSING")
        for p in by_stage["none"]:
            queue.enqueue(db, "page.prepare", job_id=job.id, page_id=p.id, dedupe_key=f"prepare:{p.id}:{gen}",
                          priority=100)
    elif by_stage["prepared"]:
        transition(job, "TRANSLATING")
        queue.enqueue(db, "job.translate", job_id=job.id, dedupe_key=f"translate:{job.id}:{gen}", priority=90)
    elif by_stage["translated"]:
        transition(job, "RENDERING")
        for p in by_stage["translated"]:
            queue.enqueue(db, "page.render", job_id=job.id, page_id=p.id, dedupe_key=f"render:{p.id}:{gen}",
                          priority=80)
    else:
        transition(job, "FINALIZING")
        queue.enqueue(db, "job.finalize", job_id=job.id, dedupe_key=f"finalize:{job.id}:{gen}", priority=70)


def bill_ready_pages(db: DB, job: m.Job) -> int:
    """Charge every rendered, not-yet-billed page and release the rest of the open reservation."""
    pages = db.execute(select(m.Page).where(m.Page.job_id == job.id, m.Page.status == "ready", ~m.Page.billed)
                       .with_for_update()).scalars().all()
    used = min(len(pages) * job.credits_per_page, job.credits_reserved)
    for p in pages:
        p.billed = True
    ledger.settle_job(db, job, used)
    return len(pages)


def finalize(db: DB, job: m.Job) -> str:
    """Settle credits and set the terminal status. Returns the status."""
    bill_ready_pages(db, job)
    counts = dict(db.execute(select(m.Page.status, func.count()).where(m.Page.job_id == job.id)
                             .group_by(m.Page.status)).all())
    ready, failed = counts.get("ready", 0), counts.get("failed", 0)
    status = "COMPLETED" if failed == 0 and ready else ("PARTIAL" if ready else "FAILED")
    transition(job, status)
    if status == "FAILED" and not job.error_code:
        job.error_code = "ALL_PAGES_FAILED"
    job.expires_at = now() + timedelta(days=int(app_settings.get(db, "retention_days")))
    job.archive_built_at = None
    return status


# --- user actions -------------------------------------------------------------

def create(db: DB, user: m.User, *, title: str, upload_ids: list, source_lang: str, target_lang: str, mode: str,
           glossary: list[dict], idempotency_key: str | None) -> tuple[m.Job, bool]:
    """Returns (job, created). Credits are reserved later, by the worker, once the page count is known."""
    if idempotency_key:
        existing = db.execute(select(m.Job).where(m.Job.user_id == user.id, m.Job.idempotency_key == idempotency_key)
                              ).scalar_one_or_none()
        if existing:
            return existing, False
    if source_lang not in app_settings.SOURCE_LANGS or target_lang not in app_settings.TARGET_LANGS:
        raise AppError(400, "VALIDATION_ERROR", "This language pair is not supported.")
    settings = app_settings.get_all(db)
    active = db.execute(select(func.count()).select_from(m.Job).where(
        m.Job.user_id == user.id, m.Job.status.not_in(TERMINAL), m.Job.deleted_at.is_(None))).scalar_one()
    if active >= settings["max_concurrent_jobs"]:
        raise AppError(400, "LIMIT_EXCEEDED", "You have too many chapters processing. Wait for one to finish.")
    if ledger.balance(db, user.id) <= 0:
        raise ledger.InsufficientCredits()

    uploads = db.execute(select(m.Upload).where(m.Upload.id.in_(upload_ids), m.Upload.user_id == user.id)
                         .with_for_update()).scalars().all()
    if len(uploads) != len(set(upload_ids)) or any(u.job_id for u in uploads):
        raise AppError(400, "UPLOAD_MISSING", "Some files were not uploaded. Please upload them again.")
    for u in uploads:
        head = storage.head(u.object_key)
        if not head or head["ContentLength"] != u.size:
            raise AppError(400, "UPLOAD_MISSING", f"“{u.filename}” did not finish uploading. Please try again.")

    job = m.Job(user_id=user.id, title=title or uploads[0].filename.rsplit(".", 1)[0][:200],
                source_lang=source_lang, target_lang=target_lang, mode=mode, glossary=glossary,
                credits_per_page=app_settings.credits_per_page(db, mode), idempotency_key=idempotency_key)
    db.add(job)
    db.flush()
    order = {str(uid): i for i, uid in enumerate(upload_ids)}
    for u in sorted(uploads, key=lambda u: order[str(u.id)]):
        u.job_id = job.id
    queue.enqueue(db, "job.ingest", job_id=job.id, payload={"upload_ids": [str(u) for u in upload_ids]},
                  dedupe_key=f"ingest:{job.id}:0", priority=50)
    return job, True


def cancel(db: DB, job: m.Job) -> None:
    job = lock(db, job.id)
    if job.status in TERMINAL:
        raise AppError(409, "CONFLICT", "This chapter has already finished.")
    queue.cancel_job_tasks(db, job.id)
    if job.credits_reserved:
        bill_ready_pages(db, job)  # pages already delivered are charged; the rest is released
    transition(job, "CANCELLED")


def retry(db: DB, job: m.Job) -> None:
    job = lock(db, job.id)
    if job.status not in ("PARTIAL", "FAILED"):
        raise AppError(409, "CONFLICT", "Only failed chapters can be retried.")
    job.generation += 1
    job.error_code = job.error_message = None
    if job.page_count == 0:  # failed before extraction (e.g. not enough credits): ingest again
        transition(job, "PENDING")
        queue.enqueue(db, "job.ingest", job_id=job.id, dedupe_key=f"ingest:{job.id}:{job.generation}", priority=50)
        return
    failed = db.execute(select(m.Page).where(m.Page.job_id == job.id, m.Page.status == "failed")
                        .with_for_update()).scalars().all()
    if not failed:
        raise AppError(409, "CONFLICT", "There are no failed pages to retry.")
    ledger.reserve_for_job(db, job, len(failed) * job.credits_per_page)
    for p in failed:
        p.status, p.error_code, p.error_message = "pending", None, None
    transition(job, "PROCESSING")
    advance(db, job)


def delete(db: DB, job: m.Job) -> None:
    job = lock(db, job.id)
    if job.status not in TERMINAL:
        cancel(db, job)
    job.deleted_at = now()
    if job.status != "EXPIRED":
        transition(job, "EXPIRED")
    queue.enqueue(db, "job.purge", job_id=job.id, dedupe_key=f"purge:{job.id}")
