import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import errors, storage
from .config import get_settings
from .db import engine
from .logs import request_id, setup_logging
from .routers import admin, auth, billing, jobs

settings = get_settings()
settings.check()
setup_logging()
log = logging.getLogger("api")

app = FastAPI(
    title="MangaTranslate AI API", version="1.0.0",
    openapi_url=None if settings.is_production else "/api/openapi.json",
    docs_url=None if settings.is_production else "/api/docs", redoc_url=None,
)
errors.install(app)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "Idempotency-Key"])

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def guard(request: Request, call_next):
    rid = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex
    request_id.set(rid)
    started = time.perf_counter()
    # CSRF: a cookie-authenticated unsafe request from a browser always carries Origin; reject foreign origins.
    origin = request.headers.get("origin")
    if (request.method in UNSAFE and origin and origin not in settings.cors_origins
            and not request.url.path.startswith("/api/v1/billing/webhooks/")):
        response = JSONResponse({"error": {"code": "FORBIDDEN", "message": "Cross-site request blocked.",
                                           "details": None}}, status_code=403)
    else:
        response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code,
                               "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                               "user_id": getattr(request.state, "user_id", None)})
    return response


for r in (auth.router, jobs.router, billing.router, admin.router):
    app.include_router(r, prefix="/api/v1")
if "dev" in settings.payment_providers and not settings.is_production:
    app.include_router(billing.dev_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    checks = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        log.exception("readiness: db")
        checks["db"] = "error"
    try:
        storage.ping()
        checks["storage"] = "ok"
    except Exception:
        log.exception("readiness: storage")
        checks["storage"] = "error"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "error", "checks": checks}, status_code=200 if ok else 503)
