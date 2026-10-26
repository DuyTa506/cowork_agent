"""The worker loop: claim a job, run it, record the result, repeat."""
from __future__ import annotations

import logging
import signal
import threading
import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core import config
from app.core.database import SessionLocal, engine
from app.core.logging import configure_logging
from app.core.migrate import ensure_schema
from app.models import Job, JobKind
from app.services import attachments, jobs, pipeline
from app.services import chat as chat_service
from app.services.formatcheck import sessions as format_sessions

log = logging.getLogger("app.worker")


def handle(db: Session, job: Job) -> None:
    """Runs one claimed job and records its outcome (done, retried or failed)."""
    try:
        if job.kind == JobKind.INDEX:
            pipeline.process(db, job.target_id)
        elif job.kind == JobKind.ATTACHMENT:
            attachments.process(db, job.target_id)
        else:
            raise ValueError(f"unknown job kind {job.kind!r}")
        jobs.complete(db, job)
    except pipeline.IndexingUnavailable as exc:
        db.rollback()
        log.warning("job %s: index unavailable (attempt %s): %s", job.id, job.attempts, exc)
        if not jobs.fail(db, job, str(exc)):
            _give_up(db, job, "Không lập được chỉ mục (máy chủ chỉ mục/embedding không phản hồi).")
    except Exception as exc:  # noqa: BLE001  (a bad document must not stop the worker)
        db.rollback()
        log.exception("job %s failed", job.id)
        if not jobs.fail(db, job, f"{type(exc).__name__}: {exc}"):
            _give_up(db, job, "Lỗi xử lý nội bộ; báo quản trị viên.")


def _give_up(db: Session, job: Job, detail: str) -> None:
    """Records on the document or attachment that the job failed for good."""
    if job.kind == JobKind.ATTACHMENT:
        attachments.mark_failed(db, job.target_id, detail)
    else:
        pipeline.mark_failed(db, job.target_id, detail)


def run_once(session_factory: Callable[[], Session] = SessionLocal) -> bool:
    """Processes at most one job; returns whether there was one."""
    with session_factory() as db:
        job = jobs.claim_next(db)
        if job is None:
            return False
        handle(db, job)
        return True


def purge_temporary(session_factory: Callable[[], Session] = SessionLocal) -> int:
    """Deletes expired format-check files and conversations idle past the retention; returns how many were removed."""
    with session_factory() as db:
        removed = format_sessions.purge_expired(db)
        db.commit()
        chats = chat_service.purge_idle(db, None)
    if removed:
        log.info("removed %s expired format-check sessions", removed)
    if chats:
        log.info("removed %s idle conversations", chats)
    return removed + chats


PURGE_EVERY_SECONDS = 600


def main() -> None:
    """Entry point: sets up logging and the schema, then works until SIGINT/SIGTERM (finishing the current job first)."""
    configure_logging()
    ensure_schema(engine)
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    with SessionLocal() as db:
        revived = jobs.requeue_stale(db)
    log.info("worker started (requeued %s abandoned jobs)", revived)
    next_purge = 0.0
    while not stop.is_set():
        if time.monotonic() >= next_purge:
            purge_temporary()
            next_purge = time.monotonic() + PURGE_EVERY_SECONDS
        if not run_once():
            stop.wait(config.WORKER_POLL_SECONDS)
    log.info("worker stopped")
