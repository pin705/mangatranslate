import uuid

import pytest
from conftest import make_admin, new_client, signup
from sqlalchemy import select, text

from mtapi import jobs, ledger
from mtapi import models as m
from mtapi.storage import bucket


def _upload(client, s3, name="p1.png", size=10):
    r = client.post("/api/v1/uploads", json={"filename": name, "size": size, "content_type": "image/png"})
    assert r.status_code == 201, r.text
    body = r.json()
    key = body["upload_url"].split(f"/{bucket()}/")[1].split("?")[0]
    s3.put_object(Bucket=bucket(), Key=key, Body=b"x" * size)
    return body["id"]


def _job(client, s3, **kw):
    payload = {"upload_ids": [_upload(client, s3)], "source_lang": "Chinese", "target_lang": "Vietnamese", **kw}
    return client.post("/api/v1/jobs", json=payload, headers={"Idempotency-Key": kw.pop("key", str(uuid.uuid4()))})


def test_upload_validation(client, db):
    signup(client, db)
    bad = client.post("/api/v1/uploads", json={"filename": "evil.exe", "size": 10, "content_type": "image/png"})
    assert bad.json()["error"]["code"] == "UPLOAD_INVALID"
    big = client.post("/api/v1/uploads", json={"filename": "a.zip", "size": 10**12, "content_type": "application/zip"})
    assert big.json()["error"]["code"] == "LIMIT_EXCEEDED"
    r = client.post("/api/v1/uploads", json={"filename": "../../etc/passwd.png", "size": 5, "content_type": "text/html"})
    key = db.execute(text("SELECT object_key, content_type FROM uploads WHERE id = :id"), {"id": r.json()["id"]}).one()
    assert key.object_key.endswith("/passwd.png") and ".." not in key.object_key and key.content_type == "image/png"


def test_create_job_is_idempotent_and_requires_upload(client, db, s3):
    signup(client, db)
    upload = _upload(client, s3)
    body = {"upload_ids": [upload], "source_lang": "Chinese", "target_lang": "Vietnamese"}
    r1 = client.post("/api/v1/jobs", json=body, headers={"Idempotency-Key": "k1"})
    r2 = client.post("/api/v1/jobs", json=body, headers={"Idempotency-Key": "k1"})
    assert (r1.status_code, r2.status_code) == (201, 200) and r1.json()["id"] == r2.json()["id"]
    assert db.execute(text("SELECT count(*) FROM tasks WHERE kind = 'job.ingest'")).scalar() == 1
    # an upload whose bytes never arrived is rejected
    missing = client.post("/api/v1/uploads", json={"filename": "x.png", "size": 3, "content_type": "image/png"}).json()
    r = client.post("/api/v1/jobs", json={**body, "upload_ids": [missing["id"]]})
    assert r.json()["error"]["code"] == "UPLOAD_MISSING"


def test_users_cannot_see_each_other(client, db, s3):
    signup(client, db)
    job = _job(client, s3).json()
    other = new_client()
    signup(other, db)
    assert other.get(f"/api/v1/jobs/{job['id']}").status_code == 404
    assert other.post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 404
    assert other.get("/api/v1/jobs").json()["total"] == 0
    assert other.get("/api/v1/admin/metrics").status_code == 403


def test_unverified_and_broke_users_cannot_start_jobs(client, db, s3):
    signup(client, db, verify=False)
    r = client.post("/api/v1/uploads", json={"filename": "a.png", "size": 1, "content_type": "image/png"})
    assert r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    other = new_client()
    u = signup(other, db)
    db.execute(text("UPDATE credit_wallets SET balance = 0 WHERE user_id = :u"), {"u": u["id"]})
    db.commit()
    assert _job(other, s3).json()["error"]["code"] == "INSUFFICIENT_CREDITS"


def test_state_machine_rejects_invalid_transitions():
    job = m.Job(status="COMPLETED")
    with pytest.raises(jobs.InvalidTransition):
        jobs.transition(job, "PROCESSING")
    job = m.Job(status="PENDING")
    jobs.transition(job, "INGESTING")
    assert job.status == "INGESTING" and job.started_at


def _seed_job(db, n_pages=4, credits=100):
    user = m.User(email=f"{uuid.uuid4().hex}@x.com", password_hash="x")
    db.add(user)
    db.flush()
    ledger.apply(db, user.id, credits, "admin_grant")
    job = m.Job(user_id=user.id, source_lang="Chinese", target_lang="Vietnamese", status="PROCESSING",
                page_count=n_pages, credits_per_page=1)
    db.add(job)
    db.flush()
    ledger.reserve_for_job(db, job, n_pages)
    for i in range(n_pages):
        db.add(m.Page(job_id=job.id, index=i, source_key=f"k{i}"))
    db.commit()
    return user, job


def _kinds(db, job):
    return sorted(k for (k,) in db.execute(select(m.Task.kind).where(m.Task.job_id == job.id, m.Task.status == "queued")))


def test_pipeline_fan_out_fan_in_and_billing(db):
    user, job = _seed_job(db)
    jobs.advance(db, job)
    db.commit()
    assert _kinds(db, job) == ["page.prepare"] * 4
    jobs.advance(db, job)  # repeated calls do not duplicate work
    db.commit()
    assert _kinds(db, job) == ["page.prepare"] * 4

    pages = db.execute(select(m.Page).where(m.Page.job_id == job.id).order_by(m.Page.index)).scalars().all()
    for p in pages[:3]:
        p.stage = "prepared"
    pages[3].status = "failed"  # this page died permanently
    db.execute(text("UPDATE tasks SET status = 'done'"))
    jobs.advance(db, job)
    db.commit()
    assert job.status == "TRANSLATING" and _kinds(db, job) == ["job.translate"]

    for p in pages[:3]:
        p.stage = "translated"
    db.execute(text("UPDATE tasks SET status = 'done'"))
    jobs.advance(db, job)
    assert job.status == "RENDERING" and _kinds(db, job) == ["page.render"] * 3

    for p in pages[:3]:
        p.stage, p.status = "rendered", "ready"
    db.execute(text("UPDATE tasks SET status = 'done'"))
    jobs.advance(db, job)
    assert job.status == "FINALIZING"
    assert jobs.finalize(db, job) == "PARTIAL"
    db.commit()
    assert (job.credits_charged, job.credits_reserved) == (3, 0)
    assert ledger.balance(db, user.id) == 97 == ledger.ledger_sum(db, user.id)

    # retry only the failed page, resuming from its last stage; it is billed once on success
    jobs.retry(db, job)
    db.commit()
    assert job.status == "PROCESSING" and job.credits_reserved == 1 and ledger.balance(db, user.id) == 96
    pages[3].stage, pages[3].status = "rendered", "ready"
    job.status = "FINALIZING"
    assert jobs.finalize(db, job) == "COMPLETED"
    db.commit()
    assert job.credits_charged == 4 and ledger.balance(db, user.id) == 96 == ledger.ledger_sum(db, user.id)


def test_cancel_releases_unused_credits(db):
    user, job = _seed_job(db, n_pages=5)
    pages = db.execute(select(m.Page).where(m.Page.job_id == job.id)).scalars().all()
    pages[0].status = "ready"
    jobs.cancel(db, job)
    db.commit()
    assert job.status == "CANCELLED" and job.credits_charged == 1 and ledger.balance(db, user.id) == 99


def test_admin_credit_adjustments_are_audited(client, db):
    admin = signup(client, db)
    make_admin(db, admin["id"])
    target = signup(new_client(), db)
    r = client.post(f"/api/v1/admin/users/{target['id']}/credits", json={"amount": 50, "reason": "support"})
    assert r.json()["balance"] == 70
    r = client.post(f"/api/v1/admin/users/{target['id']}/credits", json={"amount": -500, "reason": "abuse"})
    assert r.json()["error"]["code"] == "INSUFFICIENT_CREDITS"
    actions = [a["action"] for a in client.get("/api/v1/admin/audit").json()["items"]]
    assert actions == ["ADMIN_GRANTED_CREDITS"]
    r = client.patch("/api/v1/admin/settings", json={"credits_per_page_clean": 2})
    assert r.json()["credits_per_page_clean"] == 2
    assert client.get("/api/v1/pricing").json()["credits_per_page"]["clean"] == 2


def test_download_name_is_header_safe():
    from mtapi.storage import content_disposition
    value = content_disposition("Chương 1.cbz")
    value.encode("ascii")  # would raise for a raw Vietnamese name
    assert 'filename="Chuong 1.cbz"' in value and "filename*=UTF-8''Ch%C6%B0%C6%A1ng%201.cbz" in value
