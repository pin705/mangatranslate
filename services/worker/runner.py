"""Worker process: claims tasks from the Postgres queue and runs them.

  WORKER_QUEUES=default     CPU worker (ingest, translate, render, finalize, e-mail, cleanup)
  WORKER_QUEUES=gpu         model worker (page.prepare / page.reinpaint when MODEL_QUEUE=gpu), USE_GPU=true
  WORKER_QUEUES=default,gpu one process doing everything (single-machine setups)

Scale by running more processes/containers; claiming uses FOR UPDATE SKIP LOCKED so they never collide.
Crash safety: a claimed task holds a 10-minute lease that a background thread renews; if the process dies the
lease lapses and another worker re-runs the task, and handlers resume from the stored stage.
"""

import logging
import os
import signal
import socket
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, os.environ.get("API_PATH", str(Path(__file__).resolve().parents[1] / "api")))

from mtapi import models as m  # noqa: E402
from mtapi import queue  # noqa: E402
from mtapi.config import get_settings  # noqa: E402
from mtapi.db import SessionLocal, session_scope  # noqa: E402
from mtapi.logs import setup_logging  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

log = logging.getLogger("worker")
ALIVE = Path(os.environ.get("WORKER_ALIVE_FILE", "/tmp/worker-alive"))  # noqa: S108 — healthcheck reads its mtime
STOP = threading.Event()


def _heartbeat(worker_id: str, queues: list[str], task_id: int | None, done: int) -> None:
    ALIVE.touch()
    with session_scope() as db:
        db.execute(insert(m.WorkerHeartbeat).values(worker_id=worker_id, queues=",".join(queues), tasks_done=done,
                                                    current_task_id=task_id)
                   .on_conflict_do_update(index_elements=["worker_id"], set_={
                       "last_seen_at": text("now()"), "current_task_id": task_id, "tasks_done": done}))


def _schedule_cleanup() -> None:
    hour = datetime.now(UTC).strftime("%Y%m%d%H")
    with session_scope() as db:
        queue.enqueue(db, "system.cleanup", dedupe_key=f"cleanup:{hour}", priority=200)


def _renew_lease(task_id: int, worker_id: str, stop: threading.Event) -> None:
    while not stop.wait(60):
        try:
            with SessionLocal() as db:
                queue.extend_lease(db, task_id, worker_id)
            ALIVE.touch()
        except Exception:
            log.exception("lease renewal failed")


def run_one(task, worker_id: str) -> None:
    import tasks

    stop = threading.Event()
    renewer = threading.Thread(target=_renew_lease, args=(task.id, worker_id, stop), daemon=True)
    renewer.start()
    started = time.monotonic()
    extra = {"job_id": str(task.job_id) if task.job_id else None, "page_id": str(task.page_id) if task.page_id else None}
    try:
        if task.attempts > task.max_attempts:  # lease expired repeatedly: the task keeps killing workers
            raise tasks.Permanent("PAGE_FAILED", "exceeded attempts after lease expiry")
        tasks.HANDLERS[task.kind](task)
        with session_scope() as db:
            queue.complete(db, db.merge(task))
        log.info("task %s %s done in %.1fs", task.id, task.kind, time.monotonic() - started, extra=extra)
    except tasks.Permanent as e:
        with session_scope() as db:
            t = db.merge(task)
            t.attempts = t.max_attempts
            queue.fail(db, t, f"{e.code}: {e}")
        tasks.on_dead(task, e.code)
        log.warning("task %s %s rejected: %s", task.id, task.kind, e, extra=extra)
    except Exception as e:
        with session_scope() as db:
            t = db.merge(task)
            retry = queue.fail(db, t, f"{type(e).__name__}: {e}")
            task.last_error = t.last_error
        log.exception("task %s %s failed (%s)", task.id, task.kind, "will retry" if retry else "dead", extra=extra)
        if not retry:
            tasks.on_dead(task, "PAGE_FAILED")
    finally:
        stop.set()


def main() -> None:
    setup_logging()
    get_settings().check()
    queues = [q.strip() for q in os.environ.get("WORKER_QUEUES", "default").split(",") if q.strip()]
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: STOP.set())

    import ai
    import pipeline

    ai.seed_providers()
    if os.environ.get("PRELOAD_MODELS", "true").lower() == "true":
        pipeline.init()  # fail fast at startup if Qt/fonts/models are broken, not on the first customer page
    log.info("worker %s started on queues %s", worker_id, queues)

    done, last_beat, last_cleanup = 0, 0.0, 0.0
    idle = float(os.environ.get("WORKER_POLL_SECONDS", "1.5"))
    while not STOP.is_set():
        now = time.monotonic()
        if now - last_cleanup > 600:
            _schedule_cleanup()
            last_cleanup = now
        if now - last_beat > 30:
            _heartbeat(worker_id, queues, None, done)
            last_beat = now
        with SessionLocal() as db:
            task = queue.claim(db, worker_id, queues)
        if not task:
            STOP.wait(idle)
            continue
        _heartbeat(worker_id, queues, task.id, done)
        run_one(task, worker_id)  # finishes the current task even when asked to stop (graceful shutdown)
        done += 1
    log.info("worker %s stopped", worker_id)


if __name__ == "__main__":
    main()
