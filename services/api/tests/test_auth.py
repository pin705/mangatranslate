from conftest import last_email_token, new_client, signup
from sqlalchemy import text


def test_register_verify_grants_bonus_once(client, db):
    email = "a@example.com"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "correct horse battery"})
    assert r.status_code == 201 and r.json()["email_verified"] is False and r.json()["credits"] == 0
    token = last_email_token(db, email, "verify")
    r = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.json()["email_verified"] is True and r.json()["credits"] == 20
    # token is single-use
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).json()["error"]["code"] == "INVALID_TOKEN"
    assert client.get("/api/v1/me").json()["credits"] == 20


def test_duplicate_email_and_weak_password(client):
    assert client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422
    client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "correct horse battery"})
    r = new_client().post("/api/v1/auth/register", json={"email": "B@example.com", "password": "correct horse battery"})
    assert r.status_code == 409


def test_login_logout_and_wrong_password(client, db):
    signup(client, db, "c@example.com")
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/me").status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "c@example.com", "password": "wrong password!!"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = client.post("/api/v1/auth/login", json={"email": "C@example.com", "password": "correct horse battery"})
    assert r.status_code == 200 and "mt_session" in r.cookies
    assert "httponly" in r.headers["set-cookie"].lower()


def test_login_rate_limited(client, db):
    signup(client, db, "d@example.com")
    codes = [client.post("/api/v1/auth/login", json={"email": "d@example.com", "password": "nope nope nope"}).status_code
             for _ in range(11)]
    assert codes[-1] == 429 and codes[0] == 401


def test_password_reset_revokes_sessions(client, db):
    signup(client, db, "e@example.com")
    other = new_client()
    other.post("/api/v1/auth/login", json={"email": "e@example.com", "password": "correct horse battery"})
    assert other.get("/api/v1/me").status_code == 200
    assert new_client().post("/api/v1/auth/forgot-password", json={"email": "e@example.com"}).status_code == 204
    assert new_client().post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}).status_code == 204
    token = last_email_token(db, "e@example.com", "reset")
    assert new_client().post("/api/v1/auth/reset-password",
                             json={"token": token, "password": "a brand new password"}).status_code == 204
    assert other.get("/api/v1/me").status_code == 401
    r = new_client().post("/api/v1/auth/login", json={"email": "e@example.com", "password": "a brand new password"})
    assert r.status_code == 200


def test_suspended_user_blocked(client, db):
    user = signup(client, db, "f@example.com")
    db.execute(text("UPDATE users SET status = 'suspended' WHERE id = :id"), {"id": user["id"]})
    db.commit()
    assert client.get("/api/v1/me").json()["error"]["code"] == "ACCOUNT_SUSPENDED"


def test_cross_site_post_blocked(client, db):
    signup(client, db, "g@example.com")
    r = client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"}).status_code == 204


def test_delete_account_anonymises(client, db):
    user = signup(client, db, "h@example.com")
    assert client.request("DELETE", "/api/v1/me", json={"password": "correct horse battery"}).status_code == 202
    assert client.get("/api/v1/me").status_code == 401
    row = db.execute(text("SELECT email, status FROM users WHERE id = :id"), {"id": user["id"]}).one()
    assert row.status == "deleted" and row.email.endswith("@invalid")
    # the ledger survives for accounting
    assert db.execute(text("SELECT count(*) FROM credit_transactions WHERE user_id = :id"),
                      {"id": user["id"]}).scalar() == 1


def test_errors_have_consistent_shape(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 401 and set(r.json()["error"]) == {"code", "message", "details"}
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
