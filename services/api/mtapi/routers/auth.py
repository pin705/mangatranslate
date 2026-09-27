from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DB

from .. import app_settings, ledger, queue
from .. import models as m
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..errors import AppError
from ..schemas import (
    EmailIn,
    LoginIn,
    MePatch,
    PasswordChangeIn,
    PasswordIn,
    RegisterIn,
    ResetIn,
    TokenIn,
    UserOut,
    user_out,
)
from ..security import (
    COOKIE,
    clear_session,
    client_ip,
    consume_email_token,
    create_session,
    hash_password,
    issue_email_token,
    now,
    rate_limit,
    revoke_sessions,
    verify_password,
)

router = APIRouter()


def _send_link(db: DB, user: m.User, purpose: str) -> None:
    ttl = timedelta(hours=24) if purpose == "verify" else timedelta(hours=1)
    token = issue_email_token(db, user, purpose, ttl)
    path = "verify-email" if purpose == "verify" else "reset-password"
    queue.enqueue(db, "email.send", user_id=user.id, priority=10, payload={
        "to": user.email, "template": purpose, "locale": user.locale,
        "ctx": {"link": f"{get_settings().web_url}/{path}?token={token}"},
    })


def _out(db: DB, user: m.User) -> UserOut:
    return user_out(user, ledger.balance(db, user.id))


@router.post("/auth/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn, request: Request, response: Response, db: DB = Depends(get_db)):
    rate_limit(f"register:{client_ip(request)}", 5, 3600)
    user = m.User(email=body.email.lower(), password_hash=hash_password(body.password), locale=body.locale)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise AppError(409, "CONFLICT", "An account with this e-mail already exists. Try logging in.") from e
    _send_link(db, user, "verify")
    create_session(db, user, request, response)
    db.commit()
    return _out(db, user)


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: DB = Depends(get_db)):
    email = body.email.lower()
    rate_limit(f"login:ip:{client_ip(request)}", 20, 900)
    rate_limit(f"login:email:{email}", 10, 900)
    user = db.execute(select(m.User).where(m.User.email == email, m.User.status != "deleted")).scalar_one_or_none()
    if not verify_password(user, body.password):
        raise AppError(401, "INVALID_CREDENTIALS", "Wrong e-mail or password.")
    if user.status == "suspended":
        raise AppError(403, "ACCOUNT_SUSPENDED", "Your account is suspended. Contact support.")
    create_session(db, user, request, response)
    db.commit()
    return _out(db, user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: DB = Depends(get_db)):
    clear_session(db, request, response)
    db.commit()


@router.post("/auth/verify-email", response_model=UserOut)
def verify_email(body: TokenIn, request: Request, db: DB = Depends(get_db)):
    rate_limit(f"verify:{client_ip(request)}", 20, 3600)
    user = consume_email_token(db, body.token, "verify")
    if not user.email_verified_at:
        user.email_verified_at = now()
        # Free credits are granted on verification (not signup) to make account farming harder.
        bonus = int(app_settings.get(db, "signup_bonus"))
        if bonus > 0:
            ledger.apply(db, user.id, bonus, "signup_bonus", idempotency_key=f"signup:{user.id}", reason="welcome")
    db.commit()
    return _out(db, user)


@router.post("/auth/resend-verification", status_code=204)
def resend_verification(user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    rate_limit(f"resend:{user.id}", 3, 3600)
    if not user.email_verified_at:
        _send_link(db, user, "verify")
        db.commit()


@router.post("/auth/forgot-password", status_code=204)
def forgot_password(body: EmailIn, request: Request, db: DB = Depends(get_db)):
    rate_limit(f"forgot:ip:{client_ip(request)}", 10, 3600)
    rate_limit(f"forgot:email:{body.email.lower()}", 3, 3600)
    user = db.execute(select(m.User).where(m.User.email == body.email.lower(), m.User.status == "active")
                      ).scalar_one_or_none()
    if user:
        _send_link(db, user, "reset")
        db.commit()


@router.post("/auth/reset-password", status_code=204)
def reset_password(body: ResetIn, request: Request, db: DB = Depends(get_db)):
    rate_limit(f"reset:{client_ip(request)}", 10, 3600)
    user = consume_email_token(db, body.token, "reset")
    user.password_hash = hash_password(body.password)
    user.email_verified_at = user.email_verified_at or now()  # they proved inbox ownership
    revoke_sessions(db, user.id)
    db.commit()


# --- /me ----------------------------------------------------------------------

@router.get("/me", response_model=UserOut)
def me(user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    return _out(db, user)


@router.patch("/me", response_model=UserOut)
def patch_me(body: MePatch, user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    if body.locale:
        user.locale = body.locale
    db.commit()
    return _out(db, user)


@router.post("/me/password", status_code=204)
def change_password(body: PasswordChangeIn, request: Request, user: m.User = Depends(current_user),
                    db: DB = Depends(get_db)):
    rate_limit(f"pwchange:{user.id}", 10, 3600)
    if not verify_password(user, body.current_password):
        raise AppError(401, "INVALID_CREDENTIALS", "Your current password is wrong.")
    user.password_hash = hash_password(body.new_password)
    revoke_sessions(db, user.id, keep_token=request.cookies.get(COOKIE))
    db.commit()


@router.delete("/me", status_code=202)
def delete_me(body: PasswordIn, request: Request, response: Response, user: m.User = Depends(current_user),
              db: DB = Depends(get_db)):
    rate_limit(f"delete:{user.id}", 5, 3600)
    if not verify_password(user, body.password):
        raise AppError(401, "INVALID_CREDENTIALS", "Your password is wrong.")
    email, locale = user.email, user.locale
    # Anonymise now; payments and the credit ledger stay (accounting), linked to an anonymous user row.
    user.status, user.deleted_at = "deleted", now()
    user.email, user.password_hash = f"deleted+{user.id}@invalid", None
    db.execute(update(m.Job).where(m.Job.user_id == user.id, m.Job.deleted_at.is_(None)).values(deleted_at=now()))
    queue.enqueue(db, "user.purge", user_id=user.id, dedupe_key=f"purge-user:{user.id}")
    queue.enqueue(db, "email.send", user_id=user.id,
                  payload={"to": email, "template": "account_deleted", "locale": locale, "ctx": {}})
    revoke_sessions(db, user.id)
    response.delete_cookie(COOKIE, path="/")
    db.commit()
    return {"status": "scheduled"}
