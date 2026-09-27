from alembic import context

from app import models  # noqa: F401 — registers tables on Base.metadata
from app.db import Base, engine

target_metadata = Base.metadata


def run() -> None:
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run()
