"""Database schema. Enumerations are plain strings guarded by CHECK constraints (cheap to extend in migrations)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

ROLES = ("USER", "ADMIN", "SUPER_ADMIN")
USER_STATUSES = ("active", "suspended", "deleted")
JOB_STATUSES = (
    "PENDING", "INGESTING", "PROCESSING", "TRANSLATING", "RENDERING", "FINALIZING",
    "COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "EXPIRED",
)
PAGE_STATUSES = ("pending", "processing", "ready", "failed")
PAGE_STAGES = ("none", "prepared", "translated", "rendered")
TASK_STATUSES = ("queued", "running", "done", "failed", "cancelled")
CREDIT_KINDS = ("signup_bonus", "purchase", "reserve", "release", "refund", "admin_grant", "admin_revoke", "referral")
PAYMENT_STATUSES = ("pending", "paid", "cancelled", "failed", "refunded")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


def _uuid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES)), CheckConstraint(_in("status", USER_STATUSES)))

    id: Mapped[uuid.UUID] = _uuid()
    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lower-cased
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[str] = mapped_column(String(16), default="USER")
    status: Mapped[str] = mapped_column(String(16), default="active")
    locale: Mapped[str] = mapped_column(String(8), default="vi")
    referral_code: Mapped[str | None] = mapped_column(String(16), unique=True)
    referred_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(token); the token only lives in the cookie
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class EmailToken(Base):
    __tablename__ = "email_tokens"
    __table_args__ = (CheckConstraint(_in("purpose", ("verify", "reset", "login"))),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(token)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class RateLimit(Base):
    __tablename__ = "rate_limits"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(Integer)


class CreditWallet(Base):
    """Cached balance. The ledger (credit_transactions) is the source of truth; both change in one transaction."""

    __tablename__ = "credit_wallets"
    __table_args__ = (CheckConstraint("balance >= 0", name="balance_not_negative"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    __table_args__ = (CheckConstraint(_in("kind", CREDIT_KINDS)), CheckConstraint("amount <> 0"))

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = _created()


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = _uuid()
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    credits: Mapped[int] = mapped_column(Integer)
    bonus_credits: Mapped[int] = mapped_column(Integer, default=0)  # promotional extra, granted with the pack
    price_amount: Mapped[int] = mapped_column(BigInteger)  # smallest currency unit (VND has no minor unit)
    currency: Mapped[str] = mapped_column(String(3), default="VND")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint(_in("status", PAYMENT_STATUSES)),)

    id: Mapped[uuid.UUID] = _uuid()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    provider: Mapped[str] = mapped_column(String(32))
    order_code: Mapped[int] = mapped_column(BigInteger, unique=True)  # our reference sent to the provider
    provider_ref: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    credits: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    checkout_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentEvent(Base):
    """Every webhook we receive, stored before processing. (provider, event_id) makes processing idempotent."""

    __tablename__ = "payment_events"
    __table_args__ = (UniqueConstraint("provider", "event_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSONB)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = _created()


class Series(Base):
    """A manga/manhwa/manhua series. Its glossary keeps names and terms consistent across chapters; terms the
    translator discovers are added with auto=true and can be edited by the user."""

    __tablename__ = "series"
    __table_args__ = (Index("ix_series_user", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = _uuid()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    source_lang: Mapped[str] = mapped_column(String(32))
    target_lang: Mapped[str] = mapped_column(String(32))
    glossary: Mapped[list] = mapped_column(JSONB, default=list)  # [{source, target, auto}]
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShareLink(Base):
    """Unlisted, expiring, revocable read-only link to a finished chapter. Only sha256(token) is stored."""

    __tablename__ = "share_links"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hint: Mapped[str] = mapped_column(String(8))  # first characters, to show which link is active
    folder: Mapped[str] = mapped_column(String(32))  # shares/{folder}/: snapshot copies, so public URLs reveal no IDs
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    views: Mapped[int] = mapped_column(Integer, default=0)


class Notification(Base):
    """In-app notification. `kind` + `data` are rendered (and localized) by the web app."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # job_completed | job_failed | payment_succeeded | payment_failed | credits_low | referral_reward
    kind: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = _uuid()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    object_key: Mapped[str] = mapped_column(String(512))
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(100))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUSES)),
        CheckConstraint(_in("mode", ("clean", "overlay"))),
        UniqueConstraint("user_id", "idempotency_key"),
        Index("ix_jobs_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    source_lang: Mapped[str] = mapped_column(String(32))
    target_lang: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16), default="clean")
    glossary: Mapped[list] = mapped_column(JSONB, default=list)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    credits_per_page: Mapped[int] = mapped_column(Integer, default=1)  # price snapshot at reservation
    credits_reserved: Mapped[int] = mapped_column(Integer, default=0)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0)
    generation: Mapped[int] = mapped_column(Integer, default=0)  # bumped on retry; keys stage fan-in tasks
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)  # internal detail, never shown to users
    archive_key: Mapped[str | None] = mapped_column(String(512))
    archive_built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        CheckConstraint(_in("status", PAGE_STATUSES)),
        CheckConstraint(_in("stage", PAGE_STAGES)),
        UniqueConstraint("job_id", "index"),
    )

    id: Mapped[uuid.UUID] = _uuid()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    stage: Mapped[str] = mapped_column(String(16), default="none")
    source_key: Mapped[str] = mapped_column(String(512))
    clean_key: Mapped[str | None] = mapped_column(String(512))
    output_key: Mapped[str | None] = mapped_column(String(512))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    # Detected regions with OCR text, translation and style — the editor's document (see docs/API.md "Region")
    regions: Mapped[list] = mapped_column(JSONB, default=list)
    credits: Mapped[int] = mapped_column(Integer, default=0)  # price of this page, from its pixel area (set at ingest)
    billed: Mapped[bool] = mapped_column(Boolean, default=False)  # charged once, at the first successful render
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Task(Base):
    """Postgres work queue: workers claim rows with FOR UPDATE SKIP LOCKED and hold a lease (locked_until)."""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(_in("status", TASK_STATUSES)),
        Index("ix_tasks_claim", "status", "priority", "run_after"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    queue: Mapped[str] = mapped_column(String(32), default="default")  # "default" (CPU) or "gpu"
    status: Mapped[str] = mapped_column(String(16), default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower runs first
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_by: Mapped[str | None] = mapped_column(String(128))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Provider(Base):
    """AI provider registry. Secrets stay in the environment; rows reference them by variable name."""

    __tablename__ = "providers"
    __table_args__ = (CheckConstraint(_in("kind", ("ocr", "translation"))), UniqueConstraint("kind", "name"))

    id: Mapped[uuid.UUID] = _uuid()
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64))
    base_url: Mapped[str] = mapped_column(String(512))
    model: Mapped[str] = mapped_column(String(128))
    api_key_env: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower is tried first
    input_price_per_1m: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    output_price_per_1m: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class ProviderUsage(Base):
    __tablename__ = "provider_usage"
    __table_args__ = (Index("ix_provider_usage_created", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pages.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(32))  # ocr | translation
    input_units: Mapped[int] = mapped_column(Integer, default=0)
    output_units: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False)  # provider may have billed a failed call
    created_at: Mapped[datetime] = _created()


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    queues: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime] = _created()
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    current_task_id: Mapped[int | None] = mapped_column(BigInteger)
    tasks_done: Mapped[int] = mapped_column(Integer, default=0)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | int | str | float] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()
