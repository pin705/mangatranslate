import html
import json
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DB

from .. import app_settings, billing, ledger
from .. import models as m
from ..config import get_settings
from ..db import get_db
from ..deps import current_user, verified_user
from ..errors import AppError
from ..schemas import CheckoutIn, PaymentOut, ProductOut, TransactionOut
from ..security import now, rate_limit

router = APIRouter()


@router.get("/products", response_model=list[ProductOut])
def products(db: DB = Depends(get_db)):
    rows = db.execute(select(m.Product).where(m.Product.active).order_by(m.Product.sort_order, m.Product.price_amount)
                      ).scalars().all()
    return [ProductOut.model_validate(p, from_attributes=True) for p in rows]


@router.get("/pricing")
def pricing(db: DB = Depends(get_db)):
    s = app_settings.get_all(db)
    return {
        "credits_per_page": {"clean": s["credits_per_page_clean"], "overlay": s["credits_per_page_overlay"]},
        "signup_bonus": s["signup_bonus"],
        "languages": {"source": app_settings.SOURCE_LANGS, "target": app_settings.TARGET_LANGS},
        "limits": {"max_pages_per_job": s["max_pages_per_job"], "max_upload_mb": get_settings().max_upload_mb,
                   "max_concurrent_jobs": s["max_concurrent_jobs"]},
        "retention_days": s["retention_days"],
    }


@router.get("/credits")
def credits(user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    return {"balance": ledger.balance(db, user.id)}


@router.get("/credits/transactions")
def transactions(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                 user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    where = m.CreditTransaction.user_id == user.id
    total = db.execute(select(func.count()).select_from(m.CreditTransaction).where(where)).scalar_one()
    rows = db.execute(select(m.CreditTransaction).where(where).order_by(m.CreditTransaction.id.desc())
                      .limit(limit).offset(offset)).scalars().all()
    return {"items": [TransactionOut.model_validate(t, from_attributes=True) for t in rows], "total": total}


def payment_out(p: m.Payment, product_code: str) -> PaymentOut:
    return PaymentOut(id=p.id, product_code=product_code, amount=p.amount, currency=p.currency, credits=p.credits,
                      status=p.status, created_at=p.created_at, paid_at=p.paid_at)


@router.post("/billing/checkout", status_code=201)
def checkout(body: CheckoutIn, user: m.User = Depends(verified_user), db: DB = Depends(get_db)):
    rate_limit(f"checkout:{user.id}", 20, 3600)
    payment = billing.create_checkout(db, user, body.product_code)
    return {"payment_id": payment.id, "checkout_url": payment.checkout_url}


@router.get("/billing/payments")
def payments(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
             user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    where = m.Payment.user_id == user.id
    total = db.execute(select(func.count()).select_from(m.Payment).where(where)).scalar_one()
    rows = db.execute(select(m.Payment, m.Product.code).join(m.Product).where(where)
                      .order_by(m.Payment.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [payment_out(p, code) for p, code in rows], "total": total}


@router.get("/billing/payments/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: uuid.UUID, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    row = db.execute(select(m.Payment, m.Product.code).join(m.Product).where(m.Payment.id == payment_id)).first()
    if not row or row[0].user_id != user.id:
        raise AppError(404, "NOT_FOUND", "Payment not found.")
    payment, code = row
    if payment.status == "pending" and (now() - payment.created_at).total_seconds() > 20:
        try:  # at most one provider status check per payment every 10 s
            rate_limit(f"reconcile:{payment.id}", 1, 10)
            billing.reconcile(db, payment)
            db.refresh(payment)
        except AppError:
            pass
    return payment_out(payment, code)


@router.post("/billing/webhooks/{provider}")
async def webhook(provider: str, request: Request, db: DB = Depends(get_db)):
    body = await request.body()
    if len(body) > 64 * 1024:
        raise AppError(413, "PAYLOAD_TOO_LARGE", "Payload too large.")
    billing.process_webhook(db, provider, body, {k.lower(): v for k, v in request.headers.items()})
    return {"success": True}


# --- dev provider checkout page (never mounted in production; see main.py) ----------

dev_router = APIRouter()


@dev_router.get("/billing/dev/checkout/{payment_id}", response_class=HTMLResponse)
def dev_checkout(payment_id: uuid.UUID, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    p = db.get(m.Payment, payment_id)
    if not p or p.provider != "dev" or p.user_id != user.id:
        raise AppError(404, "NOT_FOUND", "Payment not found.")
    pid = html.escape(str(p.id))
    return f"""<!doctype html><meta charset=utf-8><title>Dev checkout</title>
<body style="font-family:system-ui;max-width:28rem;margin:4rem auto">
<h1>Test payment (development only)</h1><p>Order {p.order_code}: {p.amount:,} {html.escape(p.currency)} → {p.credits} credits</p>
<form method=post action="/api/v1/billing/dev/complete/{pid}?result=paid"><button>Simulate successful payment</button></form><br>
<form method=post action="/api/v1/billing/dev/complete/{pid}?result=cancelled"><button>Simulate cancel</button></form></body>"""


@dev_router.post("/billing/dev/complete/{payment_id}", response_class=HTMLResponse)
def dev_complete(payment_id: uuid.UUID, result: str = Query(pattern="^(paid|cancelled)$"),
                 user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    """Plays the provider: builds a signed webhook and feeds it through the normal webhook processing."""
    from ..payments.dev import sign

    p = db.get(m.Payment, payment_id)
    if not p or p.provider != "dev" or p.user_id != user.id:
        raise AppError(404, "NOT_FOUND", "Payment not found.")
    body = json.dumps({"event_id": f"dev-{p.order_code}-{result}", "order_code": p.order_code, "status": result,
                       "amount": p.amount, "provider_ref": p.provider_ref}).encode()
    billing.process_webhook(db, "dev", body, {"x-dev-signature": sign(body)})
    back = html.escape(f"{get_settings().web_url}/billing/return?payment_id={p.id}")
    return f'<!doctype html><meta http-equiv="refresh" content="0;url={back}"><a href="{back}">Continue</a>'

