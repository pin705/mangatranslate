"""Postgres-backed task queue shared by the API (enqueue) and workers (claim/complete).

Why Postgres and not Redis+Celery: job state already lives in Postgres, so enqueueing a task and changing job
state commit atomically (no lost or phantom tasks), and FOR UPDATE SKIP LOCKED gives safe concurrent claiming.
Retry with exponential backoff, dead-lettering (status=failed after max_attempts), leases for crash recovery,
cancellation, priorities, per-queue routing (cpu/gpu) and dedupe keys are all columns on `tasks`.
ponytail: fine for thousands of tasks/minute; move to a dedicated broker if throughput outgrows that.
"""

from datetime import timedelta

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DB

from . import models as m

LEASE = timedelta(minutes=10)


def enqueue(db: DB, kind: str, *, job_id=None, page_id=None, user_id=None, payload: dict | None = None,
            priority: int = 100, queue: str = "default", dedupe_key: str | None = None,
            max_attempts: int = 3, delay_seconds: int = 0) -> None:
    """Add a task in the caller's transaction. A repeated dedupe_key is silently ignored."""
    stmt = insert(m.Task).values(
        kind=kind, job_id=job_id, page_id=page_id, user_id=user_id, payload=payload or {}, priority=priority,
        queue=queue, dedupe_key=dedupe_key, max_attempts=max_attempts,
        run_after=text(f"now() + interval '{int(delay_seconds)} seconds'"),
    )
    db.execute(stmt.on_conflict_do_nothing(index_elements=["dedupe_key"]) if dedupe_key else stmt)


def claim(db: DB, worker_id: str, queues: list[str]) -> m.Task | None:
    """Take the next runnable task. Also reclaims tasks whose lease expired (worker crashed)."""
    task = db.execute(
        select(m.Task).where(
            m.Task.queue.in_(queues),
            ((m.Task.status == "queued") & (m.Task.run_after <= text("now()")))
            | ((m.Task.status == "running") & (m.Task.locked_until < text("now()"))),
        ).order_by(m.Task.priority, m.Task.run_after).limit(1).with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if not task:
        return None
    task.status = "running"
    task.attempts += 1
    task.locked_by = worker_id
    task.locked_until = text(f"now() + interval '{int(LEASE.total_seconds())} seconds'")
    db.commit()
    db.refresh(task)
    return task


def extend_lease(db: DB, task_id: int, worker_id: str) -> None:
    db.execute(update(m.Task).where(m.Task.id == task_id, m.Task.locked_by == worker_id).values(
        locked_until=text(f"now() + interval '{int(LEASE.total_seconds())} seconds'")))
    db.commit()


def complete(db: DB, task: m.Task) -> None:
    task.status, task.locked_until, task.last_error = "done", None, None


def fail(db: DB, task: m.Task, error: str) -> bool:
    """Record a failure. Returns True if the task will be retried, False if it is now dead."""
    task.last_error = error[:4000]
    task.locked_until = None
    if task.attempts < task.max_attempts:
        task.status = "queued"
        task.run_after = text(f"now() + interval '{30 * 4 ** (task.attempts - 1)} seconds'")  # 30s, 2m, 8m…
        return True
    task.status = "failed"
    return False


def cancel_job_tasks(db: DB, job_id) -> None:
    db.execute(update(m.Task).where(m.Task.job_id == job_id, m.Task.status == "queued").values(status="cancelled"))


def depth(db: DB) -> dict[str, int]:
    rows = db.execute(text("SELECT queue, count(*) FROM tasks WHERE status = 'queued' GROUP BY queue")).all()
    return {q: n for q, n in rows}
