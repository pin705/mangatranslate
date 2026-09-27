"""Request/response shapes (see docs/API.md)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from . import models as m
from . import storage

Locale = Literal["vi", "en"]


# --- auth / users ---------------------------------------------------------------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    locale: Locale = "vi"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenIn(BaseModel):
    token: str = Field(max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(min_length=10, max_length=128)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class PasswordIn(BaseModel):
    password: str = Field(max_length=128)


class MePatch(BaseModel):
    locale: Locale | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool
    role: str
    locale: str
    credits: int
    created_at: datetime


class AdminUserOut(UserOut):
    status: str


def user_out(user: m.User, credits: int, admin: bool = False) -> UserOut:
    data = dict(id=user.id, email=user.email, email_verified=bool(user.email_verified_at), role=user.role,
                locale=user.locale, credits=credits, created_at=user.created_at)
    return AdminUserOut(**data, status=user.status) if admin else UserOut(**data)


# --- uploads / jobs -----------------------------------------------------------

class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    content_type: str = Field(max_length=100)


class UploadOut(BaseModel):
    id: uuid.UUID
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str]
    expires_in: int


class GlossaryTerm(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)


class JobIn(BaseModel):
    title: str = Field(default="", max_length=200)
    upload_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    source_lang: str
    target_lang: str
    mode: Literal["clean", "overlay"] = "clean"
    glossary: list[GlossaryTerm] = Field(default_factory=list, max_length=500)


class ErrorOut(BaseModel):
    code: str
    message: str


# Page/job error codes → user-facing messages. Internal detail stays in logs and error_message.
USER_ERRORS = {
    "INSUFFICIENT_CREDITS": "Not enough credits for this chapter. Buy credits and retry.",
    "UPLOAD_INVALID": "Some files are not valid images or archives.",
    "TOO_MANY_PAGES": "This chapter has more pages than allowed.",
    "NO_PAGES": "No images were found in the upload.",
    "ALL_PAGES_FAILED": "Something went wrong processing this chapter. You can retry.",
    "PAGE_FAILED": "Something went wrong processing this page. You can retry it.",
}


def error_out(code: str | None) -> ErrorOut | None:
    if not code:
        return None
    return ErrorOut(code=code, message=USER_ERRORS.get(code, "Something went wrong. You can retry."))


class JobOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    source_lang: str
    target_lang: str
    mode: str
    page_count: int
    pages_done: int
    pages_failed: int
    pages_review: int
    credits_reserved: int
    credits_charged: int
    error: ErrorOut | None
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None


class AdminJobOut(JobOut):
    user_email: str


def job_out(job: m.Job, counts: dict[str, int], user_email: str | None = None) -> JobOut:
    data = dict(
        id=job.id, title=job.title, status=job.status, source_lang=job.source_lang, target_lang=job.target_lang,
        mode=job.mode, page_count=job.page_count, pages_done=counts.get("ready", 0),
        pages_failed=counts.get("failed", 0), pages_review=counts.get("review", 0),
        credits_reserved=job.credits_reserved, credits_charged=job.credits_charged, error=error_out(job.error_code),
        created_at=job.created_at, finished_at=job.finished_at, expires_at=job.expires_at,
    )
    return AdminJobOut(**data, user_email=user_email) if user_email is not None else JobOut(**data)


class RegionStyle(BaseModel):
    font_size: int | None = Field(default=None, ge=6, le=200)
    alignment: Literal["left", "center", "right"] = "center"
    color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    outline: bool = True
    uppercase: bool = False


class Region(BaseModel):
    id: str = Field(max_length=32)
    bbox: list[int] = Field(min_length=4, max_length=4)
    text: str = Field(default="", max_length=2000)
    translation: str = Field(default="", max_length=2000)
    confidence: float | None = None
    style: RegionStyle = Field(default_factory=RegionStyle)

    @field_validator("bbox")
    @classmethod
    def _box(cls, v):
        x1, y1, x2, y2 = v
        if x2 <= x1 or y2 <= y1 or min(v) < 0:
            raise ValueError("bbox must be [x1, y1, x2, y2] with x2 > x1 and y2 > y1")
        return v


class PageOut(BaseModel):
    id: uuid.UUID
    index: int
    status: str
    stage: str
    needs_review: bool
    review_reasons: list[str]
    width: int
    height: int
    source_url: str | None
    output_url: str | None
    error: ErrorOut | None
    updated_at: datetime


class PageDetailOut(PageOut):
    job_id: uuid.UUID
    clean_url: str | None
    regions: list[Region]
    version: int


def page_out(p: m.Page, detail: bool = False) -> PageOut:
    data = dict(
        id=p.id, index=p.index, status=p.status, stage=p.stage, needs_review=p.needs_review,
        review_reasons=p.review_reasons or [], width=p.width, height=p.height,
        source_url=storage.presign_get(p.source_key),
        output_url=storage.presign_get(p.output_key) if p.status == "ready" else None,
        error=error_out(p.error_code), updated_at=p.updated_at,
    )
    if not detail:
        return PageOut(**data)
    return PageDetailOut(**data, job_id=p.job_id, clean_url=storage.presign_get(p.clean_key),
                         regions=[Region.model_validate(r) for r in p.regions or []], version=p.version)


class RegionsIn(BaseModel):
    regions: list[Region] = Field(max_length=300)
    version: int


class RegenerateIn(BaseModel):
    what: Literal["translation", "inpaint", "typeset"]


# --- billing -----------------------------------------------------------------

class ProductOut(BaseModel):
    code: str
    name: str
    credits: int
    price_amount: int
    currency: str


class CheckoutIn(BaseModel):
    product_code: str = Field(max_length=64)


class PaymentOut(BaseModel):
    id: uuid.UUID
    product_code: str
    amount: int
    currency: str
    credits: int
    status: str
    created_at: datetime
    paid_at: datetime | None


class AdminPaymentOut(PaymentOut):
    user_email: str
    provider: str


class TransactionOut(BaseModel):
    id: int
    amount: int
    kind: str
    reason: str | None
    job_id: uuid.UUID | None
    created_at: datetime


# --- admin -----------------------------------------------------------------

class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class CreditAdjustIn(ReasonIn):
    amount: int = Field(ge=-1_000_000, le=1_000_000)

    @field_validator("amount")
    @classmethod
    def _nonzero(cls, v):
        if v == 0:
            raise ValueError("amount must not be 0")
        return v


class RefundIn(ReasonIn):
    revoke_credits: bool = True


class ProviderPatch(BaseModel):
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    model: str | None = Field(default=None, max_length=128)
    input_price_per_1m: float | None = Field(default=None, ge=0)
    output_price_per_1m: float | None = Field(default=None, ge=0)


class ProductIn(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9_-]{2,64}$")
    name: str = Field(min_length=1, max_length=120)
    credits: int = Field(gt=0)
    price_amount: int = Field(gt=0)
    currency: Literal["VND", "USD"] = "VND"
    active: bool = True
    sort_order: int = 0


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    credits: int | None = Field(default=None, gt=0)
    price_amount: int | None = Field(default=None, gt=0)
    active: bool | None = None
    sort_order: int | None = None
