"""Task handlers. Each handler is idempotent: it checks the stored stage first, so a re-delivered task (worker crash,
lease expiry) either finishes the step or notices it is already done. Heavy work happens outside DB transactions;
state changes commit in short transactions."""

import io
import logging
import zipfile
from datetime import timedelta

from sqlalchemy import delete, select, text, update

import ai
import ingest
import pipeline
from mtapi import app_settings, emails, jobs, ledger, queue, storage
from mtapi import models as m
from mtapi.config import get_settings
from mtapi.db import session_scope
from mtapi.security import now

log = logging.getLogger("worker.tasks")


class Permanent(Exception):
    """Do not retry (bad input). `code` is a user-facing error code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def _ctx(page: m.Page | None, job: m.Job) -> dict:
    return {"user_id": job.user_id, "job_id": job.id, "page_id": page.id if page else None}


def _load(task) -> tuple[m.Page | None, m.Job]:
    with session_scope() as db:
        page = db.get(m.Page, task.page_id) if task.page_id else None
        job = db.get(m.Job, task.job_id)
        return page, job


def _advance(job_id) -> None:
    with session_scope() as db:
        jobs.advance(db, jobs.lock(db, job_id))


# --- chapter intake ------------------------------------------------------------------------

def job_ingest(task) -> None:
    with session_scope() as db:
        job = jobs.lock(db, task.job_id)
        if job.status not in ("PENDING", "INGESTING"):
            return
        jobs.transition(job, "INGESTING")
        uploads = db.execute(select(m.Upload).where(m.Upload.job_id == job.id).order_by(m.Upload.created_at)
                             ).scalars().all()
        order = {u: i for i, u in enumerate(task.payload.get("upload_ids") or [])}
        uploads = sorted(uploads, key=lambda u: order.get(str(u.id), 0))
        settings = app_settings.get_all(db)
    s = get_settings()
    images: list[ingest.PageImage] = []
    try:
        for u in uploads:
            data = storage.get_bytes(u.object_key, max_bytes=s.max_upload_mb * 1024 * 1024)
            images += ingest.pages_from_upload(u.filename, data, s.max_image_pixels,
                                               settings["max_pages_per_job"] - len(images))
    except ingest.InvalidUpload as e:
        raise Permanent("TOO_MANY_PAGES" if "too many pages" in str(e) else "UPLOAD_INVALID", str(e)) from e
    if not images:
        raise Permanent("NO_PAGES")

    with session_scope() as db:
        job = jobs.lock(db, task.job_id)
        if job.status != "INGESTING":
            return
        job.page_count = len(images)
        try:
            ledger.reserve_for_job(db, job, len(images) * job.credits_per_page)
        except ledger.InsufficientCredits:
            job.page_count = 0
            job.error_code = "INSUFFICIENT_CREDITS"
            jobs.transition(job, "FAILED")
            return
        user_id = job.user_id
    prefix = storage.job_prefix(user_id, task.job_id)
    keys = []
    for i, img in enumerate(images):  # idempotent: same key on re-delivery
        key = f"{prefix}source/{i:04d}.{'jpg' if img.kind == 'jpeg' else img.kind}"
        storage.put_bytes(key, img.data, ingest.IMAGE_TYPES[img.kind])
        keys.append(key)
    with session_scope() as db:
        job = jobs.lock(db, task.job_id)
        if job.status != "INGESTING":
            return
        db.execute(delete(m.Page).where(m.Page.job_id == job.id))
        for i, (img, key) in enumerate(zip(images, keys, strict=True)):
            db.add(m.Page(job_id=job.id, index=i, source_key=key, width=img.width, height=img.height))
        jobs.transition(job, "PROCESSING")
        db.flush()
        jobs.advance(db, job)
    for u in uploads:
        storage.client().delete_object(Bucket=storage.bucket(), Key=u.object_key)


# --- page stages -----------------------------------------------------------------------------

def page_prepare(task) -> None:
    page, job = _load(task)
    if page.stage != "none" or page.status == "failed" or job.status in jobs.TERMINAL:
        return _advance(job.id)
    with session_scope() as db:
        db.execute(update(m.Page).where(m.Page.id == page.id).values(status="processing"))
    image = pipeline.decode(storage.get_bytes(page.source_key))
    blocks = pipeline.detect(image, job.source_lang, job.target_lang)
    if blocks:
        ai.ocr(image, blocks, job.source_lang, _ctx(page, job))
    blocks = pipeline.filter_ocr(blocks, image, job.source_lang)
    cleaned = pipeline.clean(image, blocks, job.mode)
    regions = pipeline.blocks_to_regions(blocks, pipeline.render_boxes(image, cleaned, blocks))
    clean_key = f"{storage.job_prefix(job.user_id, job.id)}intermediate/{page.index:04d}.png"
    storage.put_bytes(clean_key, pipeline.encode_png(cleaned), "image/png")
    with session_scope() as db:
        p = db.execute(select(m.Page).where(m.Page.id == page.id).with_for_update()).scalar_one()
        p.regions, p.clean_key, p.stage = regions, clean_key, "prepared"
        p.review_reasons = [] if regions else ["NO_TEXT_FOUND"]
        p.needs_review = not regions
    _advance(job.id)


def job_translate(task) -> None:
    _, job = _load(task)
    if job.status != "TRANSLATING":
        return _advance(job.id)
    with session_scope() as db:
        pages = db.execute(select(m.Page).where(m.Page.job_id == job.id, m.Page.stage == "prepared",
                                                m.Page.status.in_(("pending", "processing"))).order_by(m.Page.index)
                           ).scalars().all()
        snapshot = [(p.id, p.index, p.regions) for p in pages]
    lines = {f"{idx}:{r['id']}": r["text"] for _, idx, regions in snapshot for r in regions if r.get("text")}
    done, flagged = ai.translate(lines, job.source_lang, job.target_lang, job.glossary or [], _ctx(None, job)) \
        if lines else ({}, set())
    with session_scope() as db:
        for pid, idx, regions in snapshot:
            p = db.execute(select(m.Page).where(m.Page.id == pid).with_for_update()).scalar_one()
            new = []
            for r in regions:
                key = f"{idx}:{r['id']}"
                new.append({**r, "translation": done.get(key, r.get("translation", ""))})
            p.regions = new
            if any(f"{idx}:{r['id']}" in flagged for r in regions):
                p.needs_review = True
                p.review_reasons = sorted(set(p.review_reasons or []) | {"TRANSLATION_UNCERTAIN"})
            p.stage = "translated"
    _advance(job.id)


def _render_page(page: m.Page, job: m.Job) -> tuple[str, list[str]]:
    original = pipeline.decode(storage.get_bytes(page.source_key))
    cleaned = pipeline.decode(storage.get_bytes(page.clean_key)) if page.clean_key else original
    out, overflow = pipeline.render(original, cleaned, page.regions or [], job.source_lang, job.target_lang)
    key = f"{storage.job_prefix(job.user_id, job.id)}output/{page.index:04d}.jpg"
    storage.put_bytes(key, pipeline.encode_jpg(out), "image/jpeg")
    return key, overflow


def _store_render(page_id, key: str, overflow: list[str], expected_version: int | None = None) -> None:
    with session_scope() as db:
        p = db.execute(select(m.Page).where(m.Page.id == page_id).with_for_update()).scalar_one()
        if expected_version is not None and p.version != expected_version:
            return  # a newer edit is queued; its own typeset task will write the output
        reasons = {r for r in p.review_reasons or [] if r != "TEXT_OVERFLOW"} | ({"TEXT_OVERFLOW"} if overflow else set())
        p.output_key, p.stage, p.status = key, "rendered", "ready"
        p.review_reasons, p.needs_review = sorted(reasons), bool(reasons)
        p.error_code = p.error_message = None


def page_render(task) -> None:
    page, job = _load(task)
    if page.status in ("ready", "failed") or job.status in jobs.TERMINAL:
        return _advance(job.id)
    key, overflow = _render_page(page, job)
    _store_render(page.id, key, overflow)
    _advance(job.id)


def page_typeset(task) -> None:
    """Editor save: re-render from stored regions + cleaned image. No AI calls, no charge."""
    page, job = _load(task)
    if page.status != "ready":
        return
    key, overflow = _render_page(page, job)
    _store_render(page.id, key, overflow, expected_version=page.version)


def _regen_done(task, job: m.Job) -> None:
    with session_scope() as db:
        j = jobs.lock(db, job.id)
        j.credits_charged += int(task.payload.get("reserved") or 0)  # the reservation becomes the charge


def page_retranslate(task) -> None:
    page, job = _load(task)
    lines = {r["id"]: r["text"] for r in page.regions or [] if r.get("text")}
    done, flagged = ai.translate(lines, job.source_lang, job.target_lang, job.glossary or [], _ctx(page, job))
    with session_scope() as db:
        p = db.execute(select(m.Page).where(m.Page.id == page.id).with_for_update()).scalar_one()
        p.regions = [{**r, "translation": done.get(r["id"], r.get("translation", ""))} for r in p.regions or []]
        reasons = set(p.review_reasons or []) - {"TRANSLATION_UNCERTAIN"}
        p.review_reasons = sorted(reasons | ({"TRANSLATION_UNCERTAIN"} if flagged else set()))
        page = p
    key, overflow = _render_page(page, job)
    _store_render(page.id, key, overflow)
    _regen_done(task, job)


def page_reinpaint(task) -> None:
    page, job = _load(task)
    original = pipeline.decode(storage.get_bytes(page.source_key))
    blocks = pipeline.regions_to_blocks(page.regions or [], use_render_box=False)
    cleaned = pipeline.clean(original, blocks, "clean")
    storage.put_bytes(page.clean_key, pipeline.encode_png(cleaned), "image/png")
    key, overflow = _render_page(page, job)
    _store_render(page.id, key, overflow)
    _regen_done(task, job)


def job_finalize(task) -> None:
    with session_scope() as db:
        job = jobs.lock(db, task.job_id)
        if job.status != "FINALIZING":
            return
        status = jobs.finalize(db, job)
        user = db.get(m.User, job.user_id)
        counts = dict(db.execute(text("SELECT status, count(*) FROM pages WHERE job_id = :j GROUP BY status"),
                                 {"j": job.id}).all())
        template = "job_failed" if status == "FAILED" else "job_completed"
        queue.enqueue(db, "email.send", user_id=user.id, payload={
            "to": user.email, "template": template, "locale": user.locale,
            "ctx": {"title": job.title, "done": counts.get("ready", 0), "total": job.page_count,
                    "link": f"{get_settings().web_url}/jobs/{job.id}"}})


# --- downloads and data lifecycle --------------------------------------------------------------

def job_archive(task) -> None:
    with session_scope() as db:
        job = db.get(m.Job, task.job_id)
        pages = db.execute(select(m.Page).where(m.Page.job_id == job.id, m.Page.status == "ready")
                           .order_by(m.Page.index)).scalars().all()
        keys = [(p.index, p.output_key) for p in pages]
        started = now()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:  # JPEGs don't compress; CBZ readers prefer stored
        for index, key in keys:
            z.writestr(f"{index + 1:04d}.jpg", storage.get_bytes(key))
    key = f"{storage.job_prefix(job.user_id, job.id)}archive/chapter.zip"
    storage.put_bytes(key, buf.getvalue(), "application/zip")
    with session_scope() as db:
        j = db.get(m.Job, task.job_id)
        j.archive_key, j.archive_built_at = key, started


def job_purge(task) -> None:
    _, job = _load(task)
    storage.delete_prefix(storage.job_prefix(job.user_id, job.id))
    with session_scope() as db:
        db.execute(update(m.Page).where(m.Page.job_id == job.id).values(
            output_key=None, clean_key=None, regions=[]))
        db.execute(update(m.Job).where(m.Job.id == job.id).values(archive_key=None))


def user_purge(task) -> None:
    with session_scope() as db:
        for job in db.execute(select(m.Job).where(m.Job.user_id == task.user_id,
                                                  m.Job.status.not_in(jobs.TERMINAL))).scalars().all():
            jobs.cancel(db, job)
    storage.delete_prefix(f"users/{task.user_id}/")
    storage.delete_prefix(f"uploads/{task.user_id}/")
    with session_scope() as db:
        db.execute(delete(m.Upload).where(m.Upload.user_id == task.user_id))
        db.execute(delete(m.Session).where(m.Session.user_id == task.user_id))
        db.execute(update(m.Page).where(m.Page.job_id.in_(select(m.Job.id).where(m.Job.user_id == task.user_id)))
                   .values(regions=[], output_key=None, clean_key=None))
        db.execute(update(m.Job).where(m.Job.user_id == task.user_id).values(title="", glossary=[], archive_key=None))


def system_cleanup(task) -> None:
    """Hourly: expire jobs past retention, drop stale rows. Bucket lifecycle rules are the backstop."""
    with session_scope() as db:
        expired = db.execute(select(m.Job).where(m.Job.expires_at < text("now()"), m.Job.status.in_(
            ("COMPLETED", "PARTIAL", "FAILED", "CANCELLED")))).scalars().all()
        for job in expired:
            jobs.transition(job, "EXPIRED")
            queue.enqueue(db, "job.purge", job_id=job.id, dedupe_key=f"purge:{job.id}")
        db.execute(text("DELETE FROM rate_limits WHERE window_start < now() - interval '1 day'"))
        db.execute(text("DELETE FROM sessions WHERE expires_at < now()"))
        db.execute(text("DELETE FROM email_tokens WHERE expires_at < now() - interval '7 days'"))
        db.execute(text("DELETE FROM tasks WHERE status IN ('done', 'cancelled') AND updated_at < now() - interval '7 days'"))
        db.execute(text("UPDATE payments SET status = 'cancelled' WHERE status = 'pending' "
                        "AND created_at < now() - interval '1 day'"))
        db.execute(text("DELETE FROM worker_heartbeats WHERE last_seen_at < now() - interval '1 day'"))
        # Jobs that never finished ingesting because their uploads vanished are failed, releasing nothing (none held)
        db.execute(update(m.Job).where(m.Job.status == "PENDING", m.Job.created_at < now() - timedelta(days=2))
                   .values(status="FAILED", error_code="UPLOAD_INVALID", finished_at=now()))
    log.info("cleanup: %d jobs expired", len(expired))


def email_send(task) -> None:
    p = task.payload
    if not p.get("to"):
        return
    emails.send(p["to"], p["template"], p.get("locale", "vi"), **(p.get("ctx") or {}))
    with session_scope() as db:  # the payload may hold a one-time token; don't keep it once delivered
        db.execute(update(m.Task).where(m.Task.id == task.id).values(payload={}))


HANDLERS = {
    "job.ingest": job_ingest, "page.prepare": page_prepare, "job.translate": job_translate,
    "page.render": page_render, "page.typeset": page_typeset, "page.retranslate": page_retranslate,
    "page.reinpaint": page_reinpaint, "job.finalize": job_finalize, "job.archive": job_archive,
    "job.purge": job_purge, "user.purge": user_purge, "system.cleanup": system_cleanup, "email.send": email_send,
}


def on_dead(task, error_code: str) -> None:
    """A task exhausted its retries (or failed permanently): record it where the user and admin can see it."""
    with session_scope() as db:
        if task.kind == "job.ingest":
            job = jobs.lock(db, task.job_id)
            if job.status in ("PENDING", "INGESTING"):
                job.error_code, job.error_message = error_code, task.last_error
                jobs.transition(job, "FAILED")
        elif task.kind in ("page.prepare", "page.render") or (task.kind == "job.translate"):
            job = jobs.lock(db, task.job_id)
            where = [m.Page.id == task.page_id] if task.page_id else [m.Page.job_id == job.id, m.Page.stage == "prepared"]
            db.execute(update(m.Page).where(*where, m.Page.status.in_(("pending", "processing"))).values(
                status="failed", error_code="PAGE_FAILED", error_message=(task.last_error or "")[:2000]))
            db.flush()
            jobs.advance(db, job)
        elif task.kind in ("page.retranslate", "page.reinpaint") and task.payload.get("reserved"):
            job = db.get(m.Job, task.job_id)
            ledger.apply(db, job.user_id, int(task.payload["reserved"]), "release", job_id=job.id,
                         idempotency_key=f"release:{task.payload['reservation']}", reason="regeneration failed")
