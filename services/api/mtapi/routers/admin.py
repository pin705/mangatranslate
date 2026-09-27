import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DB

from .. import app_settings, billing, jobs, ledger
from .. import models as m
from ..app_settings import audit
from ..db import get_db
from ..deps import admin_user
from ..errors import AppError
from ..schemas import (
    AdminPaymentOut,
    CreditAdjustIn,
    ProductIn,
    ProductPatch,
    ProviderPatch,
    ReasonIn,
    RefundIn,
    TransactionOut,
    job_out,
    user_out,
)
from ..security import client_ip, revoke_sessions
from .jobs import page_counts

router = APIRouter(prefix="/admin", dependencies=[Depends(admin_user)])


def _user(db: DB, user_id: uuid.UUID) -> m.User:
    user = db.get(m.User, user_id)
    if not user:
        raise AppError(404, "NOT_FOUND", "User not found.")
    return user


@router.get("/metrics")
def metrics(db: DB = Depends(get_db)):
    q = lambda sql: db.execute(text(sql)).scalar() or 0  # noqa: E731
    rate = Decimal(str(app_settings.get(db, "usd_vnd_rate")))
    revenue = dict(db.execute(text(
        "SELECT currency, sum(amount) FROM payments WHERE status = 'paid' GROUP BY currency")).all())
    refunds = dict(db.execute(text(
        "SELECT currency, sum(amount) FROM payments WHERE status = 'refunded' GROUP BY currency")).all())
    ai_cost = Decimal(q("SELECT sum(cost_usd) FROM provider_usage"))
    revenue_usd = Decimal(revenue.get("VND", 0)) / rate + Decimal(revenue.get("USD", 0))
    pages = q("SELECT count(*) FROM pages WHERE billed")
    return {
        "users": q("SELECT count(*) FROM users WHERE status <> 'deleted'"),
        "active_users_30d": q("SELECT count(DISTINCT user_id) FROM jobs WHERE created_at > now() - interval '30 days'"),
        "jobs_by_status": dict(db.execute(text("SELECT status, count(*) FROM jobs GROUP BY status")).all()),
        "pages_processed": pages,
        "revenue": {k: int(v) for k, v in revenue.items()},
        "refunds": {k: int(v) for k, v in refunds.items()},
        "ai_cost_usd": float(ai_cost),
        "gross_margin_usd": float(revenue_usd - ai_cost),
        "avg_cost_per_page_usd": float(ai_cost / pages) if pages else 0.0,
        "avg_processing_seconds": float(q("SELECT avg(extract(epoch FROM finished_at - started_at)) FROM jobs "
                                          "WHERE status IN ('COMPLETED','PARTIAL') AND started_at IS NOT NULL")),
        "failed_jobs_30d": q("SELECT count(*) FROM jobs WHERE status = 'FAILED' AND created_at > now() - interval '30 days'"),
        "queue_depth": q("SELECT count(*) FROM tasks WHERE status = 'queued'"),
        "dead_tasks": q("SELECT count(*) FROM tasks WHERE status = 'failed'"),
    }


@router.get("/costs")
def costs(days: int = Query(30, ge=1, le=365), db: DB = Depends(get_db)):
    rows = db.execute(text("""
        WITH d AS (SELECT generate_series(current_date - (:days - 1), current_date, interval '1 day')::date AS day)
        SELECT d.day,
          (SELECT count(*) FROM pages p JOIN jobs j ON j.id = p.job_id
            WHERE p.billed AND j.finished_at::date = d.day) AS pages,
          (SELECT coalesce(sum(cost_usd), 0) FROM provider_usage u WHERE u.created_at::date = d.day) AS ai_cost_usd,
          (SELECT coalesce(sum(amount), 0) FROM payments y
            WHERE y.status = 'paid' AND y.currency = 'VND' AND y.paid_at::date = d.day) AS revenue_vnd
        FROM d ORDER BY d.day
    """), {"days": days}).all()
    return [{"date": r.day.isoformat(), "pages": r.pages, "ai_cost_usd": float(r.ai_cost_usd),
             "revenue_vnd": int(r.revenue_vnd)} for r in rows]


# --- users ---------------------------------------------------------------------

@router.get("/users")
def users(q: str = "", limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: DB = Depends(get_db)):
    where = [m.User.status != "deleted"]
    if q:
        where.append(or_(m.User.email.ilike(f"%{q.strip().lower()}%"), cast(m.User.id, String) == q.strip()))
    total = db.execute(select(func.count()).select_from(m.User).where(*where)).scalar_one()
    rows = db.execute(select(m.User, func.coalesce(m.CreditWallet.balance, 0))
                      .outerjoin(m.CreditWallet, m.CreditWallet.user_id == m.User.id).where(*where)
                      .order_by(m.User.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [user_out(u, bal, admin=True) for u, bal in rows], "total": total}


@router.get("/users/{user_id}")
def user_detail(user_id: uuid.UUID, db: DB = Depends(get_db)):
    user = _user(db, user_id)
    recent = db.execute(select(m.Job).where(m.Job.user_id == user.id).order_by(m.Job.created_at.desc()).limit(20)
                        ).scalars().all()
    counts = page_counts(db, [j.id for j in recent])
    txs = db.execute(select(m.CreditTransaction).where(m.CreditTransaction.user_id == user.id)
                     .order_by(m.CreditTransaction.id.desc()).limit(50)).scalars().all()
    return {"user": user_out(user, ledger.balance(db, user.id), admin=True),
            "jobs": [job_out(j, counts[j.id]) for j in recent],
            "transactions": [TransactionOut.model_validate(t, from_attributes=True) for t in txs],
            "ledger_balance": ledger.ledger_sum(db, user.id)}


@router.post("/users/{user_id}/suspend")
def suspend(user_id: uuid.UUID, body: ReasonIn, request: Request, admin: m.User = Depends(admin_user),
            db: DB = Depends(get_db)):
    user = _user(db, user_id)
    if user.role != "USER" and admin.role != "SUPER_ADMIN":
        raise AppError(403, "FORBIDDEN", "Only a super admin can suspend an admin.")
    if user.id == admin.id:
        raise AppError(400, "VALIDATION_ERROR", "You cannot suspend yourself.")
    user.status = "suspended"
    revoke_sessions(db, user.id)
    audit(db, admin, "ADMIN_SUSPENDED_USER", "user", user.id, client_ip(request), reason=body.reason)
    db.commit()
    return user_out(user, ledger.balance(db, user.id), admin=True)


@router.post("/users/{user_id}/restore")
def restore(user_id: uuid.UUID, body: ReasonIn, request: Request, admin: m.User = Depends(admin_user),
            db: DB = Depends(get_db)):
    user = _user(db, user_id)
    if user.status != "suspended":
        raise AppError(409, "CONFLICT", "This user is not suspended.")
    user.status = "active"
    audit(db, admin, "ADMIN_RESTORED_USER", "user", user.id, client_ip(request), reason=body.reason)
    db.commit()
    return user_out(user, ledger.balance(db, user.id), admin=True)


@router.post("/users/{user_id}/credits")
def adjust_credits(user_id: uuid.UUID, body: CreditAdjustIn, request: Request, admin: m.User = Depends(admin_user),
                   db: DB = Depends(get_db)):
    user = _user(db, user_id)
    kind = "admin_grant" if body.amount > 0 else "admin_revoke"
    ledger.apply(db, user.id, body.amount, kind, actor_id=admin.id, reason=body.reason)
    audit(db, admin, "ADMIN_GRANTED_CREDITS" if body.amount > 0 else "ADMIN_REVOKED_CREDITS", "user", user.id,
          client_ip(request), amount=body.amount, reason=body.reason)
    db.commit()
    return {"balance": ledger.balance(db, user.id)}


# --- jobs ---------------------------------------------------------------------

@router.get("/jobs")
def admin_jobs(status: str | None = None, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
               db: DB = Depends(get_db)):
    where = [m.Job.status == status] if status else []
    total = db.execute(select(func.count()).select_from(m.Job).where(*where)).scalar_one()
    rows = db.execute(select(m.Job, m.User.email).join(m.User, m.User.id == m.Job.user_id).where(*where)
                      .order_by(m.Job.created_at.desc()).limit(limit).offset(offset)).all()
    counts = page_counts(db, [j.id for j, _ in rows])
    return {"items": [job_out(j, counts[j.id], user_email=e) for j, e in rows], "total": total}


def _job(db: DB, job_id: uuid.UUID) -> m.Job:
    job = db.get(m.Job, job_id)
    if not job:
        raise AppError(404, "NOT_FOUND", "Job not found.")
    return job


@router.post("/jobs/{job_id}/cancel")
def admin_cancel(job_id: uuid.UUID, request: Request, admin: m.User = Depends(admin_user), db: DB = Depends(get_db)):
    job = _job(db, job_id)
    jobs.cancel(db, job)
    audit(db, admin, "ADMIN_CANCELLED_JOB", "job", job.id, client_ip(request))
    db.commit()
    return job_out(job, page_counts(db, [job.id])[job.id])


@router.post("/jobs/{job_id}/retry")
def admin_retry(job_id: uuid.UUID, request: Request, admin: m.User = Depends(admin_user), db: DB = Depends(get_db)):
    job = _job(db, job_id)
    jobs.retry(db, job)
    audit(db, admin, "ADMIN_RETRIED_JOB", "job", job.id, client_ip(request))
    db.commit()
    return job_out(job, page_counts(db, [job.id])[job.id])


@router.post("/jobs/{job_id}/takedown")
def admin_takedown(job_id: uuid.UUID, body: ReasonIn, request: Request, admin: m.User = Depends(admin_user),
                   db: DB = Depends(get_db)):
    """Copyright/abuse removal: cancels processing and deletes every stored file of the job."""
    job = _job(db, job_id)
    jobs.delete(db, job)
    audit(db, admin, "ADMIN_TAKEDOWN_JOB", "job", job.id, client_ip(request), reason=body.reason, user_id=str(job.user_id))
    db.commit()
    return {"status": job.status}


# --- payments -------------------------------------------------------------------

@router.get("/payments")
def admin_payments(status: str | None = None, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                   db: DB = Depends(get_db)):
    where = [m.Payment.status == status] if status else []
    total = db.execute(select(func.count()).select_from(m.Payment).where(*where)).scalar_one()
    rows = db.execute(select(m.Payment, m.Product.code, m.User.email).join(m.Product)
                      .join(m.User, m.User.id == m.Payment.user_id).where(*where)
                      .order_by(m.Payment.created_at.desc()).limit(limit).offset(offset)).all()
    items = [AdminPaymentOut(id=p.id, product_code=code, amount=p.amount, currency=p.currency, credits=p.credits,
                             status=p.status, created_at=p.created_at, paid_at=p.paid_at, user_email=email,
                             provider=p.provider) for p, code, email in rows]
    return {"items": items, "total": total}


@router.post("/payments/{payment_id}/refund")
def admin_refund(payment_id: uuid.UUID, body: RefundIn, request: Request, admin: m.User = Depends(admin_user),
                 db: DB = Depends(get_db)):
    payment = db.get(m.Payment, payment_id)
    if not payment:
        raise AppError(404, "NOT_FOUND", "Payment not found.")
    billing.refund(db, admin, payment, body.reason, body.revoke_credits, client_ip(request))
    return {"status": payment.status}


# --- providers / settings / products ------------------------------------------

def _provider_out(p: m.Provider) -> dict:
    return {"id": p.id, "kind": p.kind, "name": p.name, "base_url": p.base_url, "model": p.model,
            "enabled": p.enabled, "priority": p.priority, "input_price_per_1m": float(p.input_price_per_1m),
            "output_price_per_1m": float(p.output_price_per_1m), "healthy": p.consecutive_failures < 3,
            "last_error": p.last_error}


@router.get("/providers")
def providers(db: DB = Depends(get_db)):
    return [_provider_out(p) for p in db.execute(select(m.Provider).order_by(m.Provider.kind, m.Provider.priority)
                                                 ).scalars()]


@router.patch("/providers/{provider_id}")
def patch_provider(provider_id: uuid.UUID, body: ProviderPatch, request: Request, admin: m.User = Depends(admin_user),
                   db: DB = Depends(get_db)):
    p = db.get(m.Provider, provider_id)
    if not p:
        raise AppError(404, "NOT_FOUND", "Provider not found.")
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(p, k, v)
    if changes.get("enabled"):
        p.consecutive_failures = 0
    action = "ADMIN_DISABLED_PROVIDER" if changes.get("enabled") is False else "ADMIN_CHANGED_PROVIDER"
    audit(db, admin, action, "provider", p.id, client_ip(request), **changes)
    db.commit()
    return _provider_out(p)


@router.get("/settings")
def get_settings_(db: DB = Depends(get_db)):
    return app_settings.get_all(db)


@router.patch("/settings")
def patch_settings(body: dict, request: Request, admin: m.User = Depends(admin_user), db: DB = Depends(get_db)):
    bad = [k for k, v in body.items() if k not in app_settings.DEFAULTS or not isinstance(v, int | float) or v < 0]
    if bad:
        raise AppError(422, "VALIDATION_ERROR", "Unknown or invalid settings.", [{"field": k} for k in bad])
    before = app_settings.get_all(db)
    after = app_settings.update(db, body)
    audit(db, admin, "ADMIN_CHANGED_SETTINGS", "settings", None, client_ip(request),
          changes={k: [before[k], after[k]] for k in body})
    db.commit()
    return after


def _product_out(p: m.Product) -> dict:
    return {"id": p.id, "code": p.code, "name": p.name, "credits": p.credits, "price_amount": p.price_amount,
            "currency": p.currency, "active": p.active, "sort_order": p.sort_order}


@router.get("/products")
def admin_products(db: DB = Depends(get_db)):
    return [_product_out(p) for p in db.execute(select(m.Product).order_by(m.Product.sort_order)).scalars()]


@router.post("/products", status_code=201)
def create_product(body: ProductIn, request: Request, admin: m.User = Depends(admin_user), db: DB = Depends(get_db)):
    p = m.Product(**body.model_dump())
    db.add(p)
    try:
        db.flush()
    except IntegrityError as e:
        raise AppError(409, "CONFLICT", "A product with this code already exists.") from e
    audit(db, admin, "ADMIN_CHANGED_PRICE", "product", p.id, client_ip(request), created=body.model_dump())
    db.commit()
    return _product_out(p)


@router.patch("/products/{product_id}")
def patch_product(product_id: uuid.UUID, body: ProductPatch, request: Request, admin: m.User = Depends(admin_user),
                  db: DB = Depends(get_db)):
    p = db.get(m.Product, product_id)
    if not p:
        raise AppError(404, "NOT_FOUND", "Product not found.")
    changes = body.model_dump(exclude_none=True)
    before = {k: getattr(p, k) for k in changes}
    for k, v in changes.items():
        setattr(p, k, v)
    audit(db, admin, "ADMIN_CHANGED_PRICE", "product", p.id, client_ip(request), before=before, after=changes)
    db.commit()
    return _product_out(p)


@router.get("/audit")
def audit_log(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: DB = Depends(get_db)):
    total = db.execute(select(func.count()).select_from(m.AuditLog)).scalar_one()
    rows = db.execute(select(m.AuditLog, m.User.email).outerjoin(m.User, m.User.id == m.AuditLog.actor_id)
                      .order_by(m.AuditLog.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [{"id": a.id, "actor_email": e, "action": a.action, "target_type": a.target_type,
                       "target_id": a.target_id, "metadata": a.meta, "ip": a.ip, "created_at": a.created_at}
                      for a, e in rows], "total": total}

