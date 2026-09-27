"""In-app notifications. The web app renders and localizes them from `kind` + `data`."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DB

from . import app_settings, ledger
from . import models as m


def notify(db: DB, user_id, kind: str, dedupe_key: str | None = None, **data) -> None:
    stmt = insert(m.Notification).values(user_id=user_id, kind=kind, data=data, dedupe_key=dedupe_key)
    db.execute(stmt.on_conflict_do_nothing(index_elements=["dedupe_key"]) if dedupe_key else stmt)


def credits_low(db: DB, user_id) -> None:
    """At most one "credits low" notice per user per day, only when the balance drops under the threshold."""
    balance = ledger.balance(db, user_id)
    if balance < int(app_settings.get(db, "credits_low_threshold")):
        from datetime import UTC, datetime
        notify(db, user_id, "credits_low", dedupe_key=f"credits_low:{user_id}:{datetime.now(UTC):%Y%m%d}",
               balance=balance)
