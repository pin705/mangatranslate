"""End-to-end: API + queue + worker + storage + the real detection/inpainting/typesetting models.

Only the two remote AI calls (vision OCR, translation) go to a local OpenAI-compatible stub, because CI has no
provider credentials. Everything else — upload via signed URL, ingest, credit reservation, fan-out/fan-in,
rendering, billing, editor re-typeset, ZIP download — runs for real.
Run: .venv/bin/pytest tests/test_e2e.py -q   (first run downloads model weights)
"""

import io
import json
import os
import socket
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parents[1]
API = WORKER.parent / "api"
SAMPLE = WORKER.parents[1] / "samples" / "cn" / "input"
sys.path[:0] = [str(WORKER), str(API), str(API / "tests")]


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class StubAI(BaseHTTPRequestHandler):
    calls: list[str] = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        content = body["messages"][-1]["content"]
        if isinstance(content, list):  # vision OCR contact sheet
            StubAI.calls.append("ocr")
            reply = json.dumps([{"id": i, "text": f"测试文本{i}"} for i in range(1, 60)])
        else:
            StubAI.calls.append("translate")
            lines = json.loads(content)["lines"]
            reply = json.dumps({"translations": {x["id"]: f"Xin chào sư tỷ ({x['id']})" for x in lines}})
        out = json.dumps({"choices": [{"message": {"content": reply}}],
                          "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture(scope="module")
def stack():
    if not SAMPLE.exists():
        pytest.skip("sample pages not downloaded (see scripts/try_samples.sh)")
    from moto.server import ThreadedMotoServer
    from pg import ensure_database_url

    s3_port, ai_port = _port(), _port()
    moto = ThreadedMotoServer(ip_address="127.0.0.1", port=s3_port)
    moto.start()
    ai = ThreadingHTTPServer(("127.0.0.1", ai_port), StubAI)
    threading.Thread(target=ai.serve_forever, daemon=True).start()

    base = ensure_database_url()
    db_name = f"mt_e2e_{os.getpid()}"
    import psycopg
    with psycopg.connect(base.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        c.execute(f'CREATE DATABASE "{db_name}"')
    os.environ.update({
        "DATABASE_URL": base.replace("/postgres?", f"/{db_name}?") if "/postgres?" in base
        else base.rsplit("/", 1)[0] + f"/{db_name}", "APP_ENV": "test",
        "S3_ENDPOINT": f"http://127.0.0.1:{s3_port}", "S3_ACCESS_KEY": "test", "S3_SECRET_KEY": "test",
        "S3_BUCKET": "e2e", "S3_REGION": "us-east-1", "PAYMENT_PROVIDERS": "dev",
        "OPENAI_BASE_URL": f"http://127.0.0.1:{ai_port}/v1", "OCR_BASE_URL": f"http://127.0.0.1:{ai_port}/v1",
        "OPENAI_API_KEY": "stub", "DASHSCOPE_API_KEY": "stub", "CORS_ORIGINS": "http://localhost:3000",
    })
    import boto3
    boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], region_name="us-east-1",
                 aws_access_key_id="test", aws_secret_access_key="test").create_bucket(Bucket="e2e")

    from alembic import command
    from alembic.config import Config
    cfg = Config(str(API / "alembic.ini"))
    cfg.set_main_option("script_location", str(API / "migrations"))
    command.upgrade(cfg, "head")

    import ai as ai_mod
    ai_mod.seed_providers()
    from fastapi.testclient import TestClient

    from mtapi.main import app
    yield TestClient(app)
    moto.stop()
    ai.shutdown()


def drain(max_tasks: int = 200) -> list[str]:
    """Run queued tasks in-process until the queue is empty (a real worker does the same in a loop)."""
    import runner
    from mtapi import queue
    from mtapi.db import SessionLocal

    kinds = []
    for _ in range(max_tasks):
        with SessionLocal() as db:
            task = queue.claim(db, "test-worker", ["default", "gpu"])
        if not task:
            return kinds
        kinds.append(task.kind)
        runner.run_one(task, "test-worker")
    raise AssertionError("queue did not drain")


def test_full_chapter(stack):
    import requests
    from sqlalchemy import text

    from mtapi.db import SessionLocal

    client = stack
    email = "reader@example.com"
    assert client.post("/api/v1/auth/register", json={"email": email, "password": "correct horse battery"}).status_code == 201
    with SessionLocal() as db:
        link = db.execute(text("SELECT payload->'ctx'->>'link' FROM tasks WHERE kind = 'email.send'")).scalar()
    assert client.post("/api/v1/auth/verify-email", json={"token": link.split("token=")[1]}).status_code == 200

    # upload two pages as one CBZ through the signed URL, exactly like the browser
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("E06P02.jpg", "E06P03.jpg"):
            z.write(SAMPLE / name, f"chapter/{name}")
    data = buf.getvalue()
    up = client.post("/api/v1/uploads", json={"filename": "ch1.cbz", "size": len(data), "content_type": "x"}).json()
    assert requests.put(up["upload_url"], data=data, headers=up["headers"], timeout=30).status_code == 200

    job = client.post("/api/v1/jobs", headers={"Idempotency-Key": "e2e-1"}, json={
        "upload_ids": [up["id"]], "source_lang": "Chinese", "target_lang": "Vietnamese",
        "glossary": [{"source": "师姐", "target": "sư tỷ"}]}).json()
    kinds = drain()
    assert kinds.count("page.prepare") == 2 and kinds.count("job.translate") == 1 and kinds.count("page.render") == 2
    job = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert job["status"] == "COMPLETED", job
    assert (job["page_count"], job["pages_done"], job["credits_charged"], job["credits_reserved"]) == (2, 2, 2, 0)
    assert client.get("/api/v1/credits").json()["balance"] == 18
    assert StubAI.calls.count("translate") == 1  # one call for the whole chapter (shared context)

    pages = client.get(f"/api/v1/jobs/{job['id']}/pages").json()
    assert all(p["status"] == "ready" and p["output_url"] for p in pages)
    out = requests.get(pages[0]["output_url"], timeout=30)
    assert out.status_code == 200 and out.content[:3] == b"\xff\xd8\xff"

    detail = client.get(f"/api/v1/pages/{pages[0]['id']}").json()
    assert detail["regions"] and all(r["translation"].startswith("Xin chào") for r in detail["regions"])
    assert "engine" not in detail["regions"][0]  # internals stay server-side

    with SessionLocal() as db:
        cost = db.execute(text("SELECT count(*), sum(cost_usd) FROM provider_usage")).one()
    assert cost[0] >= 3 and cost[1] > 0  # usage and cost recorded per call

    # editor: typesetting-only change re-renders without AI calls or charges
    calls_before = len(StubAI.calls)
    regions = detail["regions"]
    regions[0]["translation"] = "Đã sửa tay"
    regions[0]["style"]["font_size"] = 20
    r = client.put(f"/api/v1/pages/{detail['id']}/regions", json={"regions": regions, "version": detail["version"]})
    assert r.status_code == 202
    stale = client.put(f"/api/v1/pages/{detail['id']}/regions", json={"regions": regions, "version": detail["version"]})
    assert stale.status_code == 409
    before = client.get(f"/api/v1/pages/{detail['id']}").json()["updated_at"]
    assert drain() == ["page.typeset"]
    assert client.get(f"/api/v1/pages/{detail['id']}").json()["updated_at"] != before  # clients can see the re-render
    assert len(StubAI.calls) == calls_before and client.get("/api/v1/credits").json()["balance"] == 18
    edited = client.get(f"/api/v1/pages/{detail['id']}").json()
    assert edited["regions"][0]["translation"] == "Đã sửa tay"

    # download: prepared asynchronously, then a signed URL to a valid archive
    assert client.get(f"/api/v1/jobs/{job['id']}/download?format=cbz").status_code == 202
    assert "job.archive" in drain()
    dl = client.get(f"/api/v1/jobs/{job['id']}/download?format=cbz").json()
    archive = zipfile.ZipFile(io.BytesIO(requests.get(dl["url"], timeout=30).content))
    assert archive.namelist() == ["0001.jpg", "0002.jpg"]


def test_bad_upload_fails_without_charge(stack):
    import requests

    client = stack
    client.post("/api/v1/auth/login", json={"email": "reader@example.com", "password": "correct horse battery"})
    before = client.get("/api/v1/credits").json()["balance"]
    data = b"GIF89a" + b"\0" * 100
    up = client.post("/api/v1/uploads", json={"filename": "x.png", "size": len(data), "content_type": "image/png"}).json()
    requests.put(up["upload_url"], data=data, headers=up["headers"], timeout=30)
    job = client.post("/api/v1/jobs", json={"upload_ids": [up["id"]], "source_lang": "Korean",
                                            "target_lang": "English"}).json()
    drain()
    job = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert job["status"] == "FAILED" and job["error"]["code"] == "UPLOAD_INVALID"
    assert "Traceback" not in job["error"]["message"]
    assert client.get("/api/v1/credits").json()["balance"] == before
