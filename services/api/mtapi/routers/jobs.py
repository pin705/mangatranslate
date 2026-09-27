import re
import uuid

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DB

from .. import app_settings, jobs, ledger, queue, storage
from .. import models as m
from ..config import get_settings
from ..db import get_db
from ..deps import current_user, verified_user
from ..errors import AppError
from ..schemas import (
    JobIn,
    JobOut,
    PageDetailOut,
    PageOut,
    RegenerateIn,
    RegionsIn,
    UploadIn,
    UploadOut,
    job_out,
    page_out,
)
from ..security import rate_limit

router = APIRouter()

ALLOWED = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
           ".zip": "application/zip", ".cbz": "application/zip"}


def safe_filename(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^\w.\- ]", "_", base, flags=re.UNICODE).strip(" .")[:120]
    return base or "file"


# --- uploads ----------------------------------------------------------------------

@router.post("/uploads", status_code=201, response_model=UploadOut)
def create_upload(body: UploadIn, user: m.User = Depends(verified_user), db: DB = Depends(get_db)):
    rate_limit(f"upload:{user.id}", 600, 3600)
    name = safe_filename(body.filename)
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in ALLOWED:
        raise AppError(400, "UPLOAD_INVALID", "Only PNG, JPG, WebP, ZIP and CBZ files are supported.")
    if body.size > get_settings().max_upload_mb * 1024 * 1024:
        raise AppError(400, "LIMIT_EXCEEDED", f"Files must be smaller than {get_settings().max_upload_mb} MB.")
    content_type = ALLOWED[ext]  # never trust the client's MIME type; bytes are checked again by the worker
    upload_id = uuid.uuid4()
    key = f"users/{user.id}/uploads/{upload_id}/{name}"
    db.add(m.Upload(id=upload_id, user_id=user.id, object_key=key, filename=name, size=body.size,
                    content_type=content_type))
    db.commit()
    return UploadOut(id=upload_id, upload_url=storage.presign_put(key, body.size, content_type),
                     headers={"Content-Type": content_type}, expires_in=900)


# --- jobs ---------------------------------------------------------------------------

def page_counts(db: DB, job_ids: list) -> dict:
    counts: dict = {jid: {} for jid in job_ids}
    for jid, status, n in db.execute(select(m.Page.job_id, m.Page.status, func.count()).where(
            m.Page.job_id.in_(job_ids)).group_by(m.Page.job_id, m.Page.status)).all():
        counts[jid][status] = n
    for jid, n in db.execute(select(m.Page.job_id, func.count()).where(
            m.Page.job_id.in_(job_ids), m.Page.needs_review, m.Page.status == "ready").group_by(m.Page.job_id)).all():
        counts[jid]["review"] = n
    return counts


def own_job(db: DB, user: m.User, job_id: uuid.UUID) -> m.Job:
    job = db.get(m.Job, job_id)
    if not job or job.user_id != user.id or job.deleted_at:
        raise AppError(404, "NOT_FOUND", "Chapter not found.")
    return job


def one(db: DB, job: m.Job) -> JobOut:
    return job_out(job, page_counts(db, [job.id])[job.id])


@router.post("/jobs", status_code=201, response_model=JobOut)
def create_job(body: JobIn, response: Response, user: m.User = Depends(verified_user), db: DB = Depends(get_db),
               idempotency_key: str | None = Header(default=None, max_length=100)):
    rate_limit(f"jobs:{user.id}", 60, 3600)
    job, created = jobs.create(
        db, user, title=body.title.strip(), upload_ids=body.upload_ids, source_lang=body.source_lang,
        target_lang=body.target_lang, mode=body.mode, glossary=[g.model_dump() for g in body.glossary],
        idempotency_key=idempotency_key,
    )
    db.commit()
    if not created:
        response.status_code = 200
    return one(db, job)


@router.get("/jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
              user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    where = (m.Job.user_id == user.id, m.Job.deleted_at.is_(None))
    total = db.execute(select(func.count()).select_from(m.Job).where(*where)).scalar_one()
    items = db.execute(select(m.Job).where(*where).order_by(m.Job.created_at.desc()).limit(limit).offset(offset)
                       ).scalars().all()
    counts = page_counts(db, [j.id for j in items])
    return {"items": [job_out(j, counts[j.id]) for j in items], "total": total}


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    return one(db, own_job(db, user, job_id))


@router.get("/jobs/{job_id}/pages", response_model=list[PageOut])
def job_pages(job_id: uuid.UUID, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    job = own_job(db, user, job_id)
    pages = db.execute(select(m.Page).where(m.Page.job_id == job.id).order_by(m.Page.index)).scalars().all()
    return [page_out(p) for p in pages]


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    job = own_job(db, user, job_id)
    jobs.cancel(db, job)
    db.commit()
    return one(db, job)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: uuid.UUID, user: m.User = Depends(verified_user), db: DB = Depends(get_db)):
    rate_limit(f"retry:{user.id}", 60, 3600)
    job = own_job(db, user, job_id)
    jobs.retry(db, job)
    db.commit()
    return one(db, job)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: uuid.UUID, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    job = own_job(db, user, job_id)
    jobs.delete(db, job)
    db.commit()


@router.get("/jobs/{job_id}/download")
def download(job_id: uuid.UUID, response: Response, format: str = Query("zip", pattern="^(zip|cbz)$"),
             user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    job = own_job(db, user, job_id)
    if job.status not in ("COMPLETED", "PARTIAL"):
        raise AppError(409, "CONFLICT", "The chapter is not ready yet.")
    latest_edit = db.execute(select(func.max(m.Page.updated_at)).where(m.Page.job_id == job.id)).scalar()
    fresh = job.archive_key and job.archive_built_at and (not latest_edit or job.archive_built_at >= latest_edit)
    if fresh:
        name = safe_filename(job.title or "chapter") + "." + format
        return {"status": "ready", "url": storage.presign_get(job.archive_key, download_name=name)}
    queue.enqueue(db, "job.archive", job_id=job.id, priority=20,
                  dedupe_key=f"archive:{job.id}:{latest_edit.timestamp() if latest_edit else 0}")
    db.commit()
    response.status_code = 202
    return {"status": "preparing"}


# --- editor ------------------------------------------------------------------------

def own_page(db: DB, user: m.User, page_id: uuid.UUID, lock: bool = False) -> tuple[m.Page, m.Job]:
    q = select(m.Page).where(m.Page.id == page_id)
    page = db.execute(q.with_for_update() if lock else q).scalar_one_or_none()
    if not page:
        raise AppError(404, "NOT_FOUND", "Page not found.")
    return page, own_job(db, user, page.job_id)


@router.get("/pages/{page_id}", response_model=PageDetailOut)
def get_page(page_id: uuid.UUID, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    page, _ = own_page(db, user, page_id)
    return page_out(page, detail=True)


@router.put("/pages/{page_id}/regions", status_code=202, response_model=PageDetailOut)
def save_regions(page_id: uuid.UUID, body: RegionsIn, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    rate_limit(f"editor:{user.id}", 600, 3600)
    page, _ = own_page(db, user, page_id, lock=True)
    if page.status != "ready":
        raise AppError(409, "CONFLICT", "This page is still processing.")
    if page.version != body.version:
        raise AppError(409, "CONFLICT", "This page changed since you opened it. Reload to continue.")
    for r in body.regions:
        r.bbox = [min(r.bbox[0], page.width - 1), min(r.bbox[1], page.height - 1),
                  min(r.bbox[2], page.width), min(r.bbox[3], page.height)]
    internal = {r.get("id"): r.get("engine") for r in page.regions or [] if r.get("engine")}
    page.regions = [{**r.model_dump(), **({"engine": internal[r.id]} if r.id in internal else {})}
                    for r in body.regions]
    page.version += 1
    # Typesetting-only change: re-render from the stored cleaned image; no OCR/translation/inpainting, no charge.
    queue.enqueue(db, "page.typeset", job_id=page.job_id, page_id=page.id, priority=10,
                  dedupe_key=f"typeset:{page.id}:{page.version}")
    db.commit()
    return page_out(page, detail=True)


@router.post("/pages/{page_id}/regenerate", status_code=202, response_model=PageDetailOut)
def regenerate(page_id: uuid.UUID, body: RegenerateIn, user: m.User = Depends(verified_user),
               db: DB = Depends(get_db)):
    rate_limit(f"regen:{user.id}", 120, 3600)
    page, job = own_page(db, user, page_id, lock=True)
    if page.status != "ready":
        raise AppError(409, "CONFLICT", "This page is still processing.")
    page.version += 1
    kind = {"translation": "page.retranslate", "inpaint": "page.reinpaint", "typeset": "page.typeset"}[body.what]
    queue_name = get_settings().model_queue if body.what == "inpaint" else "default"
    payload = {}
    if body.what != "typeset":
        cost = app_settings.credits_per_page(db, job.mode)
        key = f"regen:{page.id}:{page.version}"
        ledger.apply(db, user.id, -cost, "reserve", job_id=job.id, idempotency_key=key, reason=f"regenerate {body.what}")
        payload = {"reserved": cost, "reservation": key}
    queue.enqueue(db, kind, job_id=job.id, page_id=page.id, payload=payload, priority=10, queue=queue_name,
                  dedupe_key=f"{kind}:{page.id}:{page.version}")
    db.commit()
    return page_out(page, detail=True)
