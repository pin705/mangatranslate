"""Admin-editable business settings (pricing, limits) stored in app_settings, with code defaults.
Money amounts for products live in the products table; these are per-page rates and limits."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DB

from . import models as m

DEFAULTS: dict[str, int | float] = {
    "credits_per_page_clean": 1,
    "credits_per_page_overlay": 1,
    "signup_bonus": 20,
    "usd_vnd_rate": 26000,
    "max_pages_per_job": 200,
    "max_concurrent_jobs": 3,
    "retention_days": 14,
    "max_monthly_ai_spend_usd": 500,  # hard stop for provider calls; raise deliberately
}

SOURCE_LANGS = ["Chinese", "Korean", "Japanese"]
TARGET_LANGS = ["Vietnamese", "English"]


def get_all(db: DB) -> dict:
    stored = {k: v for k, v in db.execute(select(m.AppSetting.key, m.AppSetting.value)).all()}
    return {k: stored.get(k, default) for k, default in DEFAULTS.items()}


def get(db: DB, key: str):
    return get_all(db)[key]


def update(db: DB, values: dict) -> dict:
    for key, value in values.items():
        if key not in DEFAULTS:
            raise KeyError(key)
        db.execute(insert(m.AppSetting).values(key=key, value=value)
                   .on_conflict_do_update(index_elements=["key"], set_={"value": value}))
    return get_all(db)


def credits_per_page(db: DB, mode: str) -> int:
    return int(get(db, f"credits_per_page_{mode}"))


def audit(db: DB, actor: m.User | None, action: str, target_type: str | None = None, target_id=None,
          ip: str | None = None, **meta) -> None:
    db.add(m.AuditLog(actor_id=actor.id if actor else None, action=action, target_type=target_type,
                      target_id=str(target_id) if target_id else None, meta=meta, ip=ip))
