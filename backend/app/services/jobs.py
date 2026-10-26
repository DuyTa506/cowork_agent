"""A small job queue in the application database, consumed by the worker process.

Claiming is a conditional UPDATE (``WHERE id = :id AND state = 'queued'``) and succeeds for exactly one worker, so several
workers can run side by side on SQLite or PostgreSQL without extra infrastructure.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import config
from app.models import Job, JobKind, JobState
from app.models.base import now_utc

STALE_AFTER = timedelta(minutes=30)  # a RUNNING job older than this belongs to a worker that died


def enqueue(db: Session, target_id: int, *, kind: str = JobKind.INDEX, payload: dict | None = None) -> Job:
    """Queues work for a document or attachment (`target_id`) unless an identical job is already waiting; returns the (new or existing) job."""
    waiting = db.scalar(select(Job).where(Job.target_id == target_id, Job.kind == kind, Job.state == JobState.QUEUED))
    if waiting:
        return waiting
    job = Job(kind=kind, target_id=target_id, payload=payload or {})
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session) -> Job | None:
    """Takes the oldest queued job for this worker, or returns None when there is nothing to do."""
    for candidate in db.scalars(select(Job.id).where(Job.state == JobState.QUEUED).order_by(Job.id).limit(5)).all():
        taken = db.execute(update(Job).where(Job.id == candidate, Job.state == JobState.QUEUED)
                           .values(state=JobState.RUNNING, attempts=Job.attempts + 1, started_at=now_utc())).rowcount
        db.commit()
        if taken:
            return db.get(Job, candidate)
    return None


def complete(db: Session, job: Job) -> None:
    """Marks the job done."""
    job.state, job.finished_at, job.error = JobState.DONE, now_utc(), ""
    db.commit()


def fail(db: Session, job: Job, error: str, *, retry: bool = True) -> bool:
    """Records a failure. Returns True when the job was put back for another attempt, False when it is finally failed."""
    job.error = error[:4000]
    if retry and job.attempts < config.WORKER_MAX_ATTEMPTS:
        job.state = JobState.QUEUED
        db.commit()
        return True
    job.state, job.finished_at = JobState.FAILED, now_utc()
    db.commit()
    return False


def requeue_stale(db: Session) -> int:
    """Puts jobs abandoned by a crashed worker back in the queue; returns how many."""
    cutoff = now_utc() - STALE_AFTER
    count = db.execute(update(Job).where(Job.state == JobState.RUNNING, Job.started_at < cutoff).values(state=JobState.QUEUED)).rowcount
    db.commit()
    return count


def pending(db: Session) -> int:
    """Number of jobs waiting or running (for the admin screen)."""
    return len(db.scalars(select(Job.id).where(Job.state.in_([JobState.QUEUED, JobState.RUNNING]))).all())
