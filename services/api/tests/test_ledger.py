import threading
import uuid

import pytest

from app import ledger
from app import models as m
from app.db import SessionLocal


def _user(db) -> uuid.UUID:
    u = m.User(email=f"{uuid.uuid4().hex}@x.com", password_hash="x")
    db.add(u)
    db.commit()
    return u.id


def test_concurrent_reservations_never_overspend(db):
    uid = _user(db)
    ledger.apply(db, uid, 100, "admin_grant", reason="seed")
    db.commit()
    ok, failed = [], []

    def spend(i):
        with SessionLocal() as s:
            try:
                ledger.apply(s, uid, -10, "reserve", idempotency_key=f"t{i}")
                s.commit()
                ok.append(i)
            except ledger.InsufficientCredits:
                s.rollback()
                failed.append(i)

    threads = [threading.Thread(target=spend, args=(i,)) for i in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ok) == 10 and len(failed) == 15
    db.expire_all()
    assert ledger.balance(db, uid) == 0 == ledger.ledger_sum(db, uid)


def test_idempotency_key_applies_once(db):
    uid = _user(db)
    assert ledger.apply(db, uid, 50, "purchase", idempotency_key="purchase:1")
    assert not ledger.apply(db, uid, 50, "purchase", idempotency_key="purchase:1")
    db.commit()
    assert ledger.balance(db, uid) == 50 == ledger.ledger_sum(db, uid)


def test_cannot_go_negative(db):
    uid = _user(db)
    ledger.apply(db, uid, 5, "admin_grant")
    with pytest.raises(ledger.InsufficientCredits):
        ledger.apply(db, uid, -6, "admin_revoke")


def test_reserve_and_settle(db):
    uid = _user(db)
    ledger.apply(db, uid, 40, "purchase")
    job = m.Job(user_id=uid, source_lang="Chinese", target_lang="Vietnamese", page_count=10, credits_per_page=2)
    db.add(job)
    db.flush()
    ledger.reserve_for_job(db, job, 20)
    assert ledger.balance(db, uid) == 20
    ledger.settle_job(db, job, used=14)  # 7 pages rendered
    db.commit()
    assert ledger.balance(db, uid) == 26 == ledger.ledger_sum(db, uid)
    assert (job.credits_charged, job.credits_reserved) == (14, 0)
    with pytest.raises(ValueError):
        ledger.settle_job(db, job, used=1)  # nothing left to settle
