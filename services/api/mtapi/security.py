import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request, Response
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session as DB

from . import models as m
from .config import get_settings
from .db import engine
from .errors import AppError

COOKIE = "mt_session"
_hasher = PasswordHasher()  # argon2id with library defaults (RFC 9106 low-memory profile)
# Verified against when the e-mail is unknown, so login timing does not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash(secrets.token_hex(16))


def now() -> datetime:
    return datetime.now(UTC)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(user: m.User | None, password: str) -> bool:
    try:
        return _hasher.verify(user.password_hash if user and user.password_hash else _DUMMY_HASH, password) and bool(user)
    except (VerifyMismatchError, InvalidHashError):
        return False


def client_ip(request: Request) -> str:
    # Cloudflare sets CF-Connecting-IP and overwrites client-supplied values; X-Forwarded-For is spoofable.
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")


# --- sessions ---------------------------------------------------------------

def create_session(db: DB, user: m.User, request: Request, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    settings = get_settings()
    db.add(m.Session(
        id=sha256(token), user_id=user.id, expires_at=now() + timedelta(days=settings.session_days),
        ip=client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:512],
    ))
    response.set_cookie(
        COOKIE, token, max_age=settings.session_days * 86400, httponly=True,
        secure=settings.is_production, samesite="lax", path="/",
    )


def clear_session(db: DB, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.execute(delete(m.Session).where(m.Session.id == sha256(token)))
    response.delete_cookie(COOKIE, path="/")


def session_user(db: DB, request: Request) -> m.User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = db.execute(
        select(m.Session, m.User).join(m.User, m.User.id == m.Session.user_id).where(m.Session.id == sha256(token))
    ).first()
    if not row:
        return None
    session, user = row
    if session.expires_at <= now() or user.status == "deleted":
        return None
    # Sliding expiry, written at most once an hour.
    if now() - session.last_seen_at > timedelta(hours=1):
        session.last_seen_at = now()
        session.expires_at = now() + timedelta(days=get_settings().session_days)
        db.commit()
    return user


def revoke_sessions(db: DB, user_id, keep_token: str | None = None) -> None:
    q = delete(m.Session).where(m.Session.user_id == user_id)
    if keep_token:
        q = q.where(m.Session.id != sha256(keep_token))
    db.execute(q)


# --- one-time e-mail tokens (verification, password reset) -----------------

def issue_email_token(db: DB, user: m.User, purpose: str, ttl: timedelta) -> str:
    token = secrets.token_urlsafe(32)
    # Only the newest token of a purpose stays valid.
    db.execute(update(m.EmailToken).where(
        m.EmailToken.user_id == user.id, m.EmailToken.purpose == purpose, m.EmailToken.used_at.is_(None)
    ).values(used_at=now()))
    db.add(m.EmailToken(id=sha256(token), user_id=user.id, purpose=purpose, expires_at=now() + ttl))
    return token


def consume_email_token(db: DB, token: str, purpose: str) -> m.User:
    row = db.execute(
        select(m.EmailToken).where(m.EmailToken.id == sha256(token), m.EmailToken.purpose == purpose).with_for_update()
    ).scalar_one_or_none()
    if not row or row.used_at or row.expires_at <= now():
        raise AppError(400, "INVALID_TOKEN", "This link is invalid or has expired.")
    row.used_at = now()
    user = db.get(m.User, row.user_id)
    if not user or user.status == "deleted":
        raise AppError(400, "INVALID_TOKEN", "This link is invalid or has expired.")
    return user


def issue_login_code(db: DB, user: m.User) -> str:
    """6-digit one-time code for passwordless login, valid 10 minutes. Guessing is bounded by rate limits."""
    code = f"{secrets.randbelow(10**6):06d}"
    db.execute(update(m.EmailToken).where(
        m.EmailToken.user_id == user.id, m.EmailToken.purpose == "login", m.EmailToken.used_at.is_(None)
    ).values(used_at=now()))
    db.add(m.EmailToken(id=sha256(f"login:{user.id}:{code}"), user_id=user.id, purpose="login",
                        expires_at=now() + timedelta(minutes=10)))
    return code


def consume_login_code(db: DB, user: m.User, code: str) -> None:
    row = db.execute(select(m.EmailToken).where(m.EmailToken.id == sha256(f"login:{user.id}:{code}"),
                                                m.EmailToken.purpose == "login").with_for_update()).scalar_one_or_none()
    if not row or row.used_at or row.expires_at <= now():
        raise AppError(400, "INVALID_TOKEN", "This code is wrong or has expired.")
    row.used_at = now()


def new_referral_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
    return "".join(secrets.choice(alphabet) for _ in range(8))


# --- rate limiting -----------------------------------------------------------

def rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """Fixed-window counter in Postgres, committed in its own transaction so failed requests still count.

    ponytail: one row per key and a DB round-trip per call; move to Redis if request volume makes this hot.
    """
    with engine.begin() as conn:
        count = conn.execute(text("""
            INSERT INTO rate_limits (key, window_start, count) VALUES (:k, now(), 1)
            ON CONFLICT (key) DO UPDATE SET
              count = CASE WHEN rate_limits.window_start < now() - make_interval(secs => :w)
                           THEN 1 ELSE rate_limits.count + 1 END,
              window_start = CASE WHEN rate_limits.window_start < now() - make_interval(secs => :w)
                           THEN now() ELSE rate_limits.window_start END
            RETURNING count
        """), {"k": key[:255], "w": window_seconds}).scalar_one()
    if count > limit:
        raise AppError(429, "RATE_LIMITED", "Too many attempts. Please wait a moment and try again.")
