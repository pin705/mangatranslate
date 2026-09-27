from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select, update
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
    LoginCodeIn,
    LoginCodeRequestIn,
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
    consume_login_code,
    create_session,
    hash_password,
    issue_email_token,
    issue_login_code,
    new_referral_code,
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


def _new_user(db: DB, email: str, locale: str, ref: str | None, password: str | None = None) -> m.User:
    referrer = db.execute(select(m.User).where(m.User.referral_code == ref.strip().upper())).scalar_one_or_none() \
        if ref else None
    user = m.User(email=email, password_hash=hash_password(password) if password else None, locale=locale,
                  referral_code=new_referral_code(), referred_by=referrer.id if referrer else None)
    db.add(user)
    db.flush()
    return user


def _mark_verified(db: DB, user: m.User) -> None:
    """E-mail ownership proven. Free credits are granted here, not at signup, to make account farming harder."""
    if user.email_verified_at:
        return
    user.email_verified_at = now()
    bonus = int(app_settings.get(db, "signup_bonus"))
    if bonus > 0:
        ledger.apply(db, user.id, bonus, "signup_bonus", idempotency_key=f"signup:{user.id}", reason="welcome")


@router.post("/auth/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn, request: Request, response: Response, db: DB = Depends(get_db)):
    rate_limit(f"register:{client_ip(request)}", 5, 3600)
    try:
        user = _new_user(db, body.email.lower(), body.locale, body.ref, body.password)
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


@router.post("/auth/login-code/request", status_code=204)
def request_login_code(body: LoginCodeRequestIn, request: Request, db: DB = Depends(get_db)):
    """Passwordless login. Unknown e-mails get an account once the code is confirmed."""
    email = body.email.lower()
    rate_limit(f"code:ip:{client_ip(request)}", 10, 3600)
    rate_limit(f"code:email:{email}", 5, 3600)
    user = db.execute(select(m.User).where(m.User.email == email)).scalar_one_or_none()
    if user and user.status != "active":
        return  # suspended/deleted: say nothing
    user = user or _new_user(db, email, body.locale, body.ref)
    code = issue_login_code(db, user)
    queue.enqueue(db, "email.send", user_id=user.id, priority=5, payload={
        "to": user.email, "template": "login_code", "locale": user.locale, "ctx": {"code": code}})
    db.commit()


@router.post("/auth/login-code/verify", response_model=UserOut)
def verify_login_code(body: LoginCodeIn, request: Request, response: Response, db: DB = Depends(get_db)):
    email = body.email.lower()
    rate_limit(f"codeverify:ip:{client_ip(request)}", 30, 900)
    rate_limit(f"codeverify:email:{email}", 8, 900)  # 8 guesses per code lifetime out of 10^6
    user = db.execute(select(m.User).where(m.User.email == email, m.User.status == "active")).scalar_one_or_none()
    if not user:
        raise AppError(400, "INVALID_TOKEN", "This code is wrong or has expired.")
    consume_login_code(db, user, body.code)
    _mark_verified(db, user)
    create_session(db, user, request, response)
    db.commit()
    return _out(db, user)


@router.get("/referral")
def referral(user: m.User = Depends(current_user), db: DB = Depends(get_db)):
    if not user.referral_code:
        user.referral_code = new_referral_code()
        db.commit()
    invited = db.execute(select(func.count()).select_from(m.User).where(m.User.referred_by == user.id)).scalar_one()
    rewarded = db.execute(select(func.count()).select_from(m.CreditTransaction).where(
        m.CreditTransaction.user_id == user.id, m.CreditTransaction.kind == "referral")).scalar_one()
    bonus = int(app_settings.get(db, "referral_bonus"))
    return {"code": user.referral_code, "link": f"{get_settings().web_url}/register?ref={user.referral_code}",
            "invited": invited, "rewarded": rewarded, "reward_credits": bonus}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: DB = Depends(get_db)):
    clear_session(db, request, response)
    db.commit()


@router.post("/auth/verify-email", response_model=UserOut)
def verify_email(body: TokenIn, request: Request, db: DB = Depends(get_db)):
    rate_limit(f"verify:{client_ip(request)}", 20, 3600)
    user = consume_email_token(db, body.token, "verify")
    _mark_verified(db, user)
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
