import json

from conftest import make_admin, new_client, signup
from sqlalchemy import text

from app.payments import dev, payos


def _checkout(client):
    r = client.post("/api/v1/billing/checkout", json={"product_code": "starter"})
    assert r.status_code == 201, r.text
    return r.json()


def _order(db, payment_id):
    return db.execute(text("SELECT order_code, amount FROM payments WHERE id = :id"), {"id": payment_id}).one()


def _dev_webhook(client, order_code, amount, status="paid", event_id=None, sig=None):
    body = json.dumps({"event_id": event_id or f"e-{order_code}-{status}", "order_code": order_code, "status": status,
                       "amount": amount}).encode()
    return client.post("/api/v1/billing/webhooks/dev", content=body,
                       headers={"x-dev-signature": sig or dev.sign(body), "content-type": "application/json"})


def test_products_and_pricing_public(client):
    assert [p["code"] for p in client.get("/api/v1/products").json()] == ["starter", "pro", "power"]
    assert client.get("/api/v1/pricing").json()["credits_per_page"] == {"clean": 1, "overlay": 1}


def test_webhook_grants_credits_once(client, db):
    signup(client, db)
    pay = _checkout(client)
    code, amount = _order(db, pay["payment_id"])
    assert client.get("/api/v1/credits").json()["balance"] == 20
    hook = new_client()  # the provider has no session
    assert _dev_webhook(hook, code, amount).status_code == 200
    assert _dev_webhook(hook, code, amount).status_code == 200  # duplicate delivery
    assert _dev_webhook(hook, code, amount, event_id="another-id").status_code == 200  # replay under a new id
    assert client.get("/api/v1/credits").json()["balance"] == 120
    assert client.get(f"/api/v1/billing/payments/{pay['payment_id']}").json()["status"] == "paid"
    kinds = [t["kind"] for t in client.get("/api/v1/credits/transactions").json()["items"]]
    assert kinds.count("purchase") == 1


def test_bad_signature_and_amount_mismatch_grant_nothing(client, db):
    signup(client, db)
    code, amount = _order(db, _checkout(client)["payment_id"])
    hook = new_client()
    assert _dev_webhook(hook, code, amount, sig="0" * 64).status_code == 400
    assert _dev_webhook(hook, code, amount - 1).status_code == 200
    assert client.get("/api/v1/credits").json()["balance"] == 20
    err = db.execute(text("SELECT error FROM payment_events")).scalar()
    assert "amount mismatch" in err


def test_frontend_cannot_fake_success(client, db):
    signup(client, db)
    pay = _checkout(client)
    # visiting the return URL does not change anything
    assert client.get(f"/api/v1/billing/payments/{pay['payment_id']}").json()["status"] == "pending"
    assert client.get("/api/v1/credits").json()["balance"] == 20


def test_unverified_user_cannot_buy(client, db):
    signup(client, db, verify=False)
    r = client.post("/api/v1/billing/checkout", json={"product_code": "starter"})
    assert r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"


def test_refund_revokes_available_credits_and_audits(client, db):
    user = signup(client, db)
    pay = _checkout(client)
    code, amount = _order(db, pay["payment_id"])
    _dev_webhook(new_client(), code, amount)
    admin_client = new_client()
    admin = signup(admin_client, db)
    make_admin(db, admin["id"])
    r = admin_client.post(f"/api/v1/admin/payments/{pay['payment_id']}/refund",
                          json={"reason": "customer request", "revoke_credits": True})
    assert r.status_code == 200 and r.json()["status"] == "refunded"
    assert client.get("/api/v1/credits").json()["balance"] == 20
    assert db.execute(text("SELECT action FROM audit_logs")).scalar() == "ADMIN_REFUNDED_PAYMENT"
    assert db.execute(text("SELECT count(*) FROM credit_transactions WHERE user_id = :u AND kind = 'refund'"),
                      {"u": user["id"]}).scalar() == 1


def test_payos_signature_roundtrip(monkeypatch):
    monkeypatch.setattr(payos, "get_settings", lambda: type("S", (), dict(
        payos_client_id="c", payos_api_key="k", payos_checksum_key="secret", payos_base_url="https://x"))())
    provider = payos.PayOS()
    data = {"orderCode": 123, "amount": 49000, "description": "MANGATL", "accountNumber": "1",
            "reference": "TF1", "transactionDateTime": "2026-01-01 10:00:00", "currency": "VND",
            "paymentLinkId": "abc", "code": "00", "desc": "success", "counterAccountName": None}
    body = json.dumps({"code": "00", "desc": "success", "success": True, "data": data,
                       "signature": payos.sign(data, "secret")}).encode()
    event = provider.parse_webhook(body, {})
    assert (event.status, event.order_code, event.amount) == ("paid", 123, 49000)
    # null values sign as empty strings, keys are sorted
    assert payos._query_string({"b": None, "a": 1}) == "a=1&b="
    tampered = body.replace(b"49000", b"99000")
    try:
        provider.parse_webhook(tampered, {})
        raise AssertionError("tampered webhook accepted")
    except payos.InvalidSignature:
        pass
