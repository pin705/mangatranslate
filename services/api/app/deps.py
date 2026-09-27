from fastapi import Depends, Request
from sqlalchemy.orm import Session as DB

from . import models as m
from .db import get_db
from .errors import AppError
from .security import session_user


def current_user(request: Request, db: DB = Depends(get_db)) -> m.User:
    user = session_user(db, request)
    if not user:
        raise AppError(401, "UNAUTHENTICATED", "Please log in.")
    if user.status == "suspended":
        raise AppError(403, "ACCOUNT_SUSPENDED", "Your account is suspended. Contact support.")
    request.state.user_id = str(user.id)
    return user


def verified_user(user: m.User = Depends(current_user)) -> m.User:
    if not user.email_verified_at:
        raise AppError(403, "EMAIL_NOT_VERIFIED", "Please verify your e-mail address first.")
    return user


def admin_user(user: m.User = Depends(current_user)) -> m.User:
    if user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise AppError(403, "FORBIDDEN", "You do not have access to this page.")
    return user
