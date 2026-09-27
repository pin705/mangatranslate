import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from pg import ensure_database_url  # noqa: E402

# --- environment must be set before the app is imported ---------------------------
_base = ensure_database_url()
_dbname = f"mt_test_{os.getpid()}"
os.environ["DATABASE_URL"] = _base.replace("/postgres?", f"/{_dbname}?") if "/postgres?" in _base \
    else _base.rsplit("/", 1)[0] + f"/{_dbname}"
os.environ.update({
    "APP_ENV": "test", "S3_ENDPOINT": "https://s3.us-east-1.amazonaws.com", "S3_ACCESS_KEY": "test", "S3_SECRET_KEY": "test",
    "S3_BUCKET": "test-bucket", "S3_REGION": "us-east-1", "PAYMENT_PROVIDERS": "dev", "EMAIL_PROVIDER": "console",
    "CORS_ORIGINS": "http://localhost:3000",
})

import psycopg  # noqa: E402
from moto import mock_aws  # noqa: E402

_admin_url = _base.replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(_admin_url, autocommit=True) as c:
    c.execute(f'DROP DATABASE IF EXISTS "{_dbname}"')
    c.execute(f'CREATE DATABASE "{_dbname}"')

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

_api_root = Path(__file__).parent.parent
_cfg = Config(str(_api_root / "alembic.ini"))
_cfg.set_main_option("script_location", str(_api_root / "migrations"))
command.upgrade(_cfg, "head")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from mtapi import models as m  # noqa: E402
from mtapi.db import SessionLocal, engine  # noqa: E402

_KEEP = {"alembic_version", "products"}


@pytest.fixture(autouse=True)
def _clean_db():
    with engine.begin() as conn:
        tables = [t for (t,) in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")) if t not in _KEEP]
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(autouse=True)
def s3():
    with mock_aws():
        import boto3

        from mtapi import storage
        storage.client.cache_clear()
        storage.signing_client.cache_clear()
        boto3.client("s3", region_name="us-east-1", endpoint_url="https://s3.us-east-1.amazonaws.com").create_bucket(
            Bucket="test-bucket")
        yield storage.client()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    from mtapi.main import app
    with TestClient(app) as c:
        yield c


def new_client():
    from mtapi.main import app
    return TestClient(app)


def last_email_token(db, email: str, template: str) -> str:
    db.expire_all()
    tasks = db.execute(select(m.Task).where(m.Task.kind == "email.send").order_by(m.Task.id.desc())).scalars()
    for t in tasks:
        if t.payload.get("to") == email and t.payload.get("template") == template:
            return t.payload["ctx"]["link"].split("token=")[1]
    raise AssertionError("no e-mail sent")


def signup(client, db, email: str | None = None, verify: bool = True, password: str = "correct horse battery"):
    email = email or f"u{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    if verify:
        r = client.post("/api/v1/auth/verify-email", json={"token": last_email_token(db, email, "verify")})
        assert r.status_code == 200, r.text
    return r.json()


def make_admin(db, user_id, role="ADMIN"):
    db.execute(text("UPDATE users SET role = :r WHERE id = :id"), {"r": role, "id": user_id})
    db.commit()
