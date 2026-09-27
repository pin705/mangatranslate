"""Checkout, webhook processing and refunds. Credits are granted in exactly one place (`handle_event`), inside the
same DB transaction that stores the provider event, guarded by unique (provider, event_id) and a per-payment
ledger idempotency key — duplicate or replayed webhooks cannot grant twice."""

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DB

from . import app_settings, ledger, queue
from . import models as m
from .app_settings import audit
from .config import get_settings
from .errors import AppError
from .notify import notify
from .payments import default_provider, get_provider
from .payments.base import InvalidSignature, ManualRefundRequired, ProviderEvent
from .security import now

log = logging.getLogger("billing")


def create_checkout(db: DB, user: m.User, product_code: str) -> m.Payment:
    product = db.execute(select(m.Product).where(m.Product.code == product_code, m.Product.active)).scalar_one_or_none()
    if not product:
        raise AppError(404, "NOT_FOUND", "This plan is not available.")
    provider = default_provider()
    for _ in range(5):
        payment = m.Payment(user_id=user.id, product_id=product.id, provider=provider.name,
                            order_code=10**12 + secrets.randbelow(9 * 10**12), amount=product.price_amount,
                            currency=product.currency, credits=product.credits + (product.bonus_credits or 0))
        try:
            with db.begin_nested():
                db.add(payment)
                db.flush()
            break
        except IntegrityError:  # order_code collision, pick another
            continue
    else:
        raise AppError(500, "INTERNAL_ERROR", "Could not create the order. Please try again.")
    web = get_settings().web_url
    try:
        checkout = provider.create_checkout(payment, product, f"{web}/billing/return?payment_id={payment.id}",
                                            f"{web}/billing/return?payment_id={payment.id}&cancelled=1")
    except Exception as e:
        log.exception("checkout creation failed")
        raise AppError(502, "PAYMENT_PROVIDER_ERROR", "The payment provider is unavailable. Please try again.") from e
    payment.checkout_url, payment.provider_ref = checkout.checkout_url, checkout.provider_ref
    db.commit()
    return payment


def handle_event(db: DB, provider: str, event: ProviderEvent) -> None:
    """Apply a verified provider event. Idempotent. Caller commits."""
    stored = db.execute(
        insert(m.PaymentEvent).values(provider=provider, event_id=event.event_id, payload=event.raw)
        .on_conflict_do_nothing(index_elements=["provider", "event_id"]).returning(m.PaymentEvent.id)
    ).scalar_one_or_none()
    if stored is None:
        return  # already processed (duplicate delivery / replay)
    row = db.get(m.PaymentEvent, stored)
    payment = db.execute(
        select(m.Payment).where(m.Payment.order_code == event.order_code, m.Payment.provider == provider).with_for_update()
    ).scalar_one_or_none()
    row.processed_at = now()
    if not payment:
        row.error = "unknown order"  # e.g. the provider's webhook test ping
        return
    row.payment_id = payment.id
    user = db.get(m.User, payment.user_id)

    if event.status == "paid":
        if payment.status != "pending":
            row.error = f"payment already {payment.status}"
            return
        if event.amount is not None and event.amount != payment.amount:
            row.error = f"amount mismatch: got {event.amount}, expected {payment.amount}"
            log.error("payment %s %s", payment.id, row.error)
            return
        payment.status, payment.paid_at = "paid", now()
        payment.provider_ref = event.provider_ref or payment.provider_ref
        ledger.apply(db, payment.user_id, payment.credits, "purchase", payment_id=payment.id,
                     idempotency_key=f"purchase:{payment.id}", reason=f"order {payment.order_code}")
        product = db.get(m.Product, payment.product_id)
        notify(db, user.id, "payment_succeeded", dedupe_key=f"paid:{payment.id}", credits=payment.credits,
               amount=payment.amount, currency=payment.currency, payment_id=str(payment.id))
        _referral_reward(db, user, payment)
        queue.enqueue(db, "email.send", user_id=user.id, payload={"to": user.email, "template": "payment_receipt",
                      "locale": user.locale, "ctx": {"amount": f"{payment.amount:,}", "currency": payment.currency,
                      "product": product.name, "credits": payment.credits, "order_code": payment.order_code}})
    elif event.status in ("cancelled", "failed") and payment.status == "pending":
        payment.status = event.status
        if event.status == "failed":
            notify(db, user.id, "payment_failed", dedupe_key=f"failed:{payment.id}", payment_id=str(payment.id))
            queue.enqueue(db, "email.send", user_id=user.id, payload={"to": user.email, "template": "payment_failed",
                          "locale": user.locale, "ctx": {"order_code": payment.order_code,
                                                         "link": f"{get_settings().web_url}/billing"}})


def _referral_reward(db: DB, user: m.User, payment: m.Payment) -> None:
    """First paid purchase of an invited user rewards both sides once. Paid-only, so fake sign-ups earn nothing."""
    if not user.referred_by:
        return
    earlier = db.execute(select(m.Payment.id).where(m.Payment.user_id == user.id, m.Payment.status.in_(
        ("paid", "refunded")), m.Payment.id != payment.id).limit(1)).first()
    referrer = db.get(m.User, user.referred_by)
    if earlier or not referrer or referrer.status != "active":
        return
    bonus = int(app_settings.get(db, "referral_bonus"))
    if bonus <= 0:
        return
    for who, key in ((referrer, f"referral:referrer:{user.id}"), (user, f"referral:referee:{user.id}")):
        if ledger.apply(db, who.id, bonus, "referral", payment_id=payment.id, idempotency_key=key, reason="referral"):
            notify(db, who.id, "referral_reward", dedupe_key=key, credits=bonus)


def process_webhook(db: DB, provider_name: str, body: bytes, headers: dict[str, str]) -> None:
    provider = get_provider(provider_name)
    try:
        event = provider.parse_webhook(body, headers)
    except (InvalidSignature, ValueError, KeyError) as e:
        log.warning("rejected %s webhook: %s", provider_name, type(e).__name__)
        raise AppError(400, "INVALID_SIGNATURE", "Invalid webhook.") from e
    handle_event(db, provider_name, event)
    db.commit()


def reconcile(db: DB, payment: m.Payment) -> None:
    """Ask the provider for the status of a pending payment (covers lost webhooks)."""
    try:
        event = get_provider(payment.provider).fetch_status(payment)
    except Exception:
        log.warning("status check failed for payment %s", payment.id, exc_info=True)
        return
    if event.status != "pending":
        handle_event(db, payment.provider, event)
        db.commit()


def refund(db: DB, admin: m.User, payment: m.Payment, reason: str, revoke_credits: bool, ip: str) -> None:
    payment = db.execute(select(m.Payment).where(m.Payment.id == payment.id).with_for_update()).scalar_one()
    if payment.status != "paid":
        raise AppError(409, "CONFLICT", "Only paid payments can be refunded.")
    try:
        get_provider(payment.provider).refund(payment)
    except ManualRefundRequired:
        pass  # money is returned out-of-band (bank transfer); we record it here
    revoked = 0
    if revoke_credits:
        revoked = min(payment.credits, ledger.balance(db, payment.user_id))
        ledger.apply(db, payment.user_id, -revoked, "refund", payment_id=payment.id, actor_id=admin.id,
                     idempotency_key=f"refund:{payment.id}", reason=reason)
    payment.status, payment.refunded_at = "refunded", now()
    audit(db, admin, "ADMIN_REFUNDED_PAYMENT", "payment", payment.id, ip, reason=reason,
          credits_revoked=revoked, credits_short=payment.credits - revoked if revoke_credits else 0)
    db.commit()
