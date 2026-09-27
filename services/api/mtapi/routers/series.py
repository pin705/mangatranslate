import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DB

from .. import app_settings
from .. import models as m
from ..db import get_db
from ..deps import current_user
from ..errors import AppError
from ..schemas import SeriesIn, SeriesOut, SeriesPatch, job_out
from ..security import now
from .jobs import page_counts

router = APIRouter()


def own_series(db: DB, user: m.User, series_id: uuid.UUID) -> m.Series:
    s = db.get(m.Series, series_id)
    if not s or s.user_id != user.id or s.deleted_at:
        raise AppError(404, "NOT_FOUND", "Series not found.")
    return s


def series_out(s: m.Series, chapters: int) -> SeriesOut:
    return SeriesOut(id=s.id, title=s.title, source_lang=s.source_lang, target_lang=s.target_lang, chapters=chapters,
                     terms=len(s.glossary or []), created_at=s.created_at, updated_at=s.updated_at)


def _chapter_counts(db: DB, ids: list) -> dict:
    return dict(db.execute(select(m.Job.series_id, func.count()).where(
        m.Job.series_id.in_(ids), m.Job.deleted_at.is_(None)).group_by(m.Job.series_id)).all())


@router.get("/series")
def list_series(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    where = (m.Series.user_id == user.id, m.Series.deleted_at.is_(None))
    total = db.execute(select(func.count()).select_from(m.Series).where(*where)).scalar_one()
    rows = db.execute(select(m.Series).where(*where).order_by(m.Series.updated_at.desc()).limit(limit).offset(offset)
                      ).scalars().all()
    counts = _chapter_counts(db, [s.id for s in rows])
    return {"items": [series_out(s, counts.get(s.id, 0)) for s in rows], "total": total}


@router.post("/series", status_code=201, response_model=SeriesOut)
def create_series(body: SeriesIn, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    if body.source_lang not in app_settings.SOURCE_LANGS or body.target_lang not in app_settings.TARGET_LANGS:
        raise AppError(400, "VALIDATION_ERROR", "This language pair is not supported.")
    count = db.execute(select(func.count()).select_from(m.Series).where(
        m.Series.user_id == user.id, m.Series.deleted_at.is_(None))).scalar_one()
    if count >= 500:
        raise AppError(400, "LIMIT_EXCEEDED", "You have reached the maximum number of series.")
    s = m.Series(user_id=user.id, title=body.title.strip(), source_lang=body.source_lang, target_lang=body.target_lang,
                 glossary=[])
    db.add(s)
    db.commit()
    return series_out(s, 0)


@router.get("/series/{series_id}")
def get_series(series_id: uuid.UUID, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    s = own_series(db, user, series_id)
    chapters = db.execute(select(m.Job).where(m.Job.series_id == s.id, m.Job.deleted_at.is_(None))
                          .order_by(m.Job.created_at)).scalars().all()
    counts = page_counts(db, [j.id for j in chapters])
    return {**series_out(s, len(chapters)).model_dump(), "glossary": s.glossary or [],
            "chapters": [job_out(j, counts[j.id]) for j in chapters]}


@router.patch("/series/{series_id}", response_model=SeriesOut)
def patch_series(series_id: uuid.UUID, body: SeriesPatch, user: m.User = Depends(current_user),
                 db: DB = Depends(get_db)):
    s = db.execute(select(m.Series).where(m.Series.id == series_id).with_for_update()).scalar_one_or_none()
    if not s or s.user_id != user.id or s.deleted_at:
        raise AppError(404, "NOT_FOUND", "Series not found.")
    if body.title is not None:
        s.title = body.title.strip()
    if body.glossary is not None:
        seen, terms = set(), []
        for t in body.glossary:  # one entry per source term; the first wins
            key = t.source.strip()
            if key and key not in seen:
                seen.add(key)
                terms.append({"source": key, "target": t.target.strip(), "auto": t.auto})
        s.glossary = terms
    db.commit()
    return series_out(s, _chapter_counts(db, [s.id]).get(s.id, 0))


@router.delete("/series/{series_id}", status_code=204)
def delete_series(series_id: uuid.UUID, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    s = own_series(db, user, series_id)
    s.deleted_at = now()
    db.execute(update(m.Job).where(m.Job.series_id == s.id).values(series_id=None))  # chapters stay
    db.commit()


# --- notifications ------------------------------------------------------------------

@router.get("/notifications")
def notifications(limit: int = Query(20, ge=1, le=100), user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    rows = db.execute(select(m.Notification).where(m.Notification.user_id == user.id)
                      .order_by(m.Notification.id.desc()).limit(limit)).scalars().all()
    unread = db.execute(select(func.count()).select_from(m.Notification).where(
        m.Notification.user_id == user.id, m.Notification.read_at.is_(None))).scalar_one()
    return {"items": [{"id": n.id, "kind": n.kind, "data": n.data, "read": n.read_at is not None,
                       "created_at": n.created_at} for n in rows], "unread": unread}


class ReadIn(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=200)
    all: bool = False


@router.post("/notifications/read", status_code=204)
def mark_read(body: ReadIn, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    q = update(m.Notification).where(m.Notification.user_id == user.id, m.Notification.read_at.is_(None))
    if not body.all:
        q = q.where(m.Notification.id.in_(body.ids))
    db.execute(q.values(read_at=now()))
    db.commit()
