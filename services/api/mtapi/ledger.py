"""Credit ledger. Every change is an immutable credit_transactions row; credit_wallets.balance is a cache
updated in the same DB transaction under a row lock, so concurrent jobs cannot double-spend.

Callers own the transaction: these functions never commit.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DB

from . import models as m
from .errors import AppError


class InsufficientCredits(AppError):
    def __init__(self):
        super().__init__(402, "INSUFFICIENT_CREDITS", "Not enough credits.")


def _locked_wallet(db: DB, user_id: uuid.UUID) -> m.CreditWallet:
    db.execute(insert(m.CreditWallet).values(user_id=user_id, balance=0).on_conflict_do_nothing())
    return db.execute(select(m.CreditWallet).where(m.CreditWallet.user_id == user_id).with_for_update()).scalar_one()


def apply(
    db: DB, user_id: uuid.UUID, amount: int, kind: str, *, idempotency_key: str | None = None,
    job_id=None, payment_id=None, actor_id=None, reason: str | None = None,
) -> bool:
    """Add `amount` (may be negative). Returns False if `idempotency_key` was already applied (no-op)."""
    if amount == 0:
        return True
    wallet = _locked_wallet(db, user_id)
    if wallet.balance + amount < 0:
        raise InsufficientCredits()
    inserted = db.execute(
        insert(m.CreditTransaction).values(
            user_id=user_id, amount=amount, kind=kind, idempotency_key=idempotency_key,
            job_id=job_id, payment_id=payment_id, actor_id=actor_id, reason=reason,
        ).on_conflict_do_nothing(index_elements=["idempotency_key"]).returning(m.CreditTransaction.id)
    ).scalar_one_or_none()
    if inserted is None:
        return False
    wallet.balance += amount
    wallet.updated_at = func.now()
    return True


def balance(db: DB, user_id: uuid.UUID) -> int:
    return db.execute(select(m.CreditWallet.balance).where(m.CreditWallet.user_id == user_id)).scalar() or 0


def ledger_sum(db: DB, user_id: uuid.UUID) -> int:
    """Source-of-truth balance, used by reconciliation and tests."""
    return db.execute(
        select(func.coalesce(func.sum(m.CreditTransaction.amount), 0)).where(m.CreditTransaction.user_id == user_id)
    ).scalar_one()


def reserve_for_job(db: DB, job: m.Job, credits: int) -> None:
    apply(db, job.user_id, -credits, "reserve", job_id=job.id,
          idempotency_key=f"reserve:{job.id}:{job.generation}", reason=f"{job.page_count} pages")
    job.credits_reserved += credits


def settle_job(db: DB, job: m.Job, used: int) -> None:
    """Charge `used` credits out of the open reservation and release the rest."""
    unused = job.credits_reserved - used
    if unused < 0:
        raise ValueError("settlement exceeds reservation")
    apply(db, job.user_id, unused, "release", job_id=job.id,
          idempotency_key=f"release:{job.id}:{job.generation}", reason="unused reservation")
    job.credits_charged += used
    job.credits_reserved = 0
