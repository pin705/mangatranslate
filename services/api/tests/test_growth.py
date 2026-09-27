import json

from conftest import new_client, signup
from sqlalchemy import select, text

from mtapi import app_settings
from mtapi import models as m
from mtapi.payments import dev


def _code(db, email: str) -> str:
    db.expire_all()
    for t in db.execute(select(m.Task).where(m.Task.kind == "email.send").order_by(m.Task.id.desc())).scalars():
        if t.payload.get("to") == email and t.payload.get("template") == "login_code":
            return t.payload["ctx"]["code"]
    raise AssertionError("no login code sent")


def test_login_code_creates_account_and_logs_in(client, db):
    email = "otp@example.com"
    assert client.post("/api/v1/auth/login-code/request", json={"email": email}).status_code == 204
    code = _code(db, email)
    wrong = "000000" if code != "000000" else "111111"
    assert client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": wrong}).status_code == 400
    r = client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": code})
    assert r.status_code == 200 and r.json()["email_verified"] and r.json()["credits"] == 20
    assert client.get("/api/v1/me").json()["email"] == email
    # single use
    assert new_client().post("/api/v1/auth/login-code/verify", json={"email": email, "code": code}).status_code == 400
    # a second login by code does not grant the bonus again
    client.post("/api/v1/auth/login-code/request", json={"email": email})
    assert client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": _code(db, email)}).json()["credits"] == 20


def test_login_code_guessing_is_rate_limited(client, db):
    email = "guess@example.com"
    client.post("/api/v1/auth/login-code/request", json={"email": email})
    codes = [client.post("/api/v1/auth/login-code/verify", json={"email": email, "code": f"{i:06d}"}).status_code
             for i in range(9)]
    assert codes[-1] == 429


def _buy(client, db):
    pay = client.post("/api/v1/billing/checkout", json={"product_code": "starter"}).json()
    order = db.execute(text("SELECT order_code, amount FROM payments WHERE id = :id"), {"id": pay["payment_id"]}).one()
    body = json.dumps({"event_id": f"e-{order.order_code}", "order_code": order.order_code, "status": "paid",
                       "amount": order.amount}).encode()
    new_client().post("/api/v1/billing/webhooks/dev", content=body, headers={"x-dev-signature": dev.sign(body)})


def test_referral_rewards_both_once_on_first_purchase(client, db):
    signup(client, db)
    ref = client.get("/api/v1/referral").json()
    assert ref["link"].endswith(f"ref={ref['code']}") and ref["invited"] == 0
    friend = new_client()
    friend.post("/api/v1/auth/register", json={"email": "friend@example.com", "password": "correct horse battery",
                                               "ref": ref["code"].lower()})
    from conftest import last_email_token
    friend.post("/api/v1/auth/verify-email", json={"token": last_email_token(db, "friend@example.com", "verify")})
    assert client.get("/api/v1/referral").json()["invited"] == 1
    assert client.get("/api/v1/credits").json()["balance"] == 20  # sign-up alone earns nothing
    _buy(friend, db)
    _buy(friend, db)  # second purchase: no second reward
    assert client.get("/api/v1/credits").json()["balance"] == 70
    assert friend.get("/api/v1/credits").json()["balance"] == 20 + 100 + 100 + 50
    kinds = [n["kind"] for n in client.get("/api/v1/notifications").json()["items"]]
    assert kinds == ["referral_reward"]


def test_pack_bonus_is_granted(client, db):
    db.execute(text("UPDATE products SET bonus_credits = 30 WHERE code = 'starter'"))
    db.commit()
    signup(client, db)
    assert client.get("/api/v1/products").json()[0]["bonus_credits"] == 30
    _buy(client, db)
    assert client.get("/api/v1/credits").json()["balance"] == 20 + 130


def test_page_cost_scales_with_pixels():
    s = {**app_settings.DEFAULTS, "credit_megapixels": 2.0}
    assert app_settings.page_cost(s, 1, 1200, 1660) == 1       # a normal manga page
    assert app_settings.page_cost(s, 1, 800, 12000) == 5       # a long webtoon strip
    assert app_settings.page_cost(s, 2, 800, 12000) == 10      # clean mode priced at 2 per block
    assert app_settings.page_cost(s, 1, 10, 10) == 1


def test_series_are_private(client, db):
    signup(client, db)
    s = client.post("/api/v1/series", json={"title": "A", "source_lang": "Chinese", "target_lang": "Vietnamese"}).json()
    other = new_client()
    signup(other, db)
    assert other.get(f"/api/v1/series/{s['id']}").status_code == 404
    assert other.patch(f"/api/v1/series/{s['id']}", json={"title": "x"}).status_code == 404
    r = client.patch(f"/api/v1/series/{s['id']}", json={"glossary": [
        {"source": "师姐", "target": "sư tỷ"}, {"source": "师姐", "target": "dup"}]}).json()
    assert r["terms"] == 1
    assert client.post("/api/v1/series", json={"title": "B", "source_lang": "Thai", "target_lang": "Vietnamese"}
                       ).status_code == 400
