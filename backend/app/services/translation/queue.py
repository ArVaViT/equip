"""Queue helpers for the publish-time translation pipeline.

Three operations the publish path + worker need:

* ``enqueue_course_translation`` — publish path enqueues one job per
  course mutation. Idempotent in the sense that an already-queued or
  already-processing job for the same course short-circuits: piling up
  five identical jobs because a teacher mashes Save five times in a row
  is waste, not behaviour anyone wants.

* ``claim_next_job`` — worker pulls the oldest claimable job under
  ``FOR UPDATE SKIP LOCKED`` so two concurrent workers never grab the
  same row. Returns ``None`` when the queue is empty; the worker
  endpoint then 204s and the cron re-fires on the next tick.

* ``mark_job_done`` / ``mark_job_failed`` — worker reports the
  outcome. Failure bumps ``attempts``; once the count reaches
  ``TRANSLATION_JOB_MAX_ATTEMPTS`` the job promotes to
  ``failed_permanent`` and the admin reset surface from Phase 5au is
  the only way back to ``failed``.

The session lifecycle is deliberately strict: helpers commit at the
end so a follow-up exception in the caller doesn't bleed claimed-row
state across requests.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.translation_job import (
    TRANSLATION_JOB_MAX_ATTEMPTS,
    TranslationJob,
    TranslationJobStatus,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


def enqueue_course_translation(
    db: Session,
    course_id: str,
    *,
    requested_by: uuid.UUID | str | None = None,
) -> TranslationJob:
    """Enqueue a translation job for ``course_id`` unless one is
    already pending.

    "Already pending" means a row with status ``queued`` or
    ``processing``. The publish hook gets the same idempotency it had
    with the synchronous orchestrator (idempotent because the orchestrator
    short-circuits on ``source_hash``), so a teacher tapping Save twice
    does not double-bill Gemini.

    Commits before returning so the row is visible to a worker reading
    from a different session immediately.
    """
    existing = (
        db.execute(
            select(TranslationJob)
            .where(TranslationJob.course_id == course_id)
            .where(TranslationJob.status.in_([TranslationJobStatus.QUEUED, TranslationJobStatus.PROCESSING]))
            .order_by(TranslationJob.enqueued_at)
            .limit(1)
        )
        .scalars()
        .first()
    )
    if existing is not None:
        logger.info(
            "translation_queue: course %s already has pending job %s (status=%s); skipping enqueue",
            course_id,
            existing.id,
            existing.status,
        )
        return existing

    job = TranslationJob(
        course_id=course_id,
        status=TranslationJobStatus.QUEUED,
        requested_by=requested_by if requested_by is not None else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("translation_queue: enqueued job %s for course %s", job.id, course_id)
    return job


def claim_next_job(db: Session) -> TranslationJob | None:
    """Claim the oldest ``queued`` or ``failed`` job for processing.

    Two concurrent workers never grab the same row because the
    ``SELECT ... FOR UPDATE SKIP LOCKED`` predicate makes Postgres
    skip any row already row-locked by another transaction.
    ``failed`` jobs are eligible for re-claim so a transient Gemini
    outage doesn't leak a job into oblivion.

    Returns ``None`` when no claimable job exists; the worker endpoint
    then 204s and the cron re-fires on the next tick.

    The session is left in an OPEN transaction holding the row lock
    until the caller commits — that's the point: the worker's
    ``mark_job_done`` / ``mark_job_failed`` call commits the status
    flip in the same transaction so the row visibility window is
    minimised.
    """
    job = (
        db.execute(
            select(TranslationJob)
            .where(TranslationJob.status.in_([TranslationJobStatus.QUEUED, TranslationJobStatus.FAILED]))
            .order_by(TranslationJob.enqueued_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .first()
    )
    if job is None:
        return None
    job.status = TranslationJobStatus.PROCESSING
    job.started_at = datetime.now(UTC)
    job.attempts = job.attempts + 1
    db.flush()
    return job


def mark_job_done(db: Session, job: TranslationJob) -> TranslationJob:
    """Flip the claimed job to ``done`` and stamp ``finished_at``.

    Called by the worker after a successful ``translate_course_content``
    pass. Commits the transaction so the row lock from
    ``claim_next_job`` is released.
    """
    job.status = TranslationJobStatus.DONE
    job.finished_at = datetime.now(UTC)
    job.last_error = None
    db.commit()
    db.refresh(job)
    return job


def mark_job_failed(db: Session, job: TranslationJob, *, error: str) -> TranslationJob:
    """Record a worker failure. Promotes to ``failed_permanent`` when
    the attempt budget is exhausted, otherwise re-queues as
    ``failed``.

    Commits the transaction so the row lock from ``claim_next_job``
    is released regardless of whether the job survives or terminates.
    """
    job.last_error = error[:2000] if error else None
    job.finished_at = datetime.now(UTC)
    if job.attempts >= TRANSLATION_JOB_MAX_ATTEMPTS:
        job.status = TranslationJobStatus.FAILED_PERMANENT
    else:
        # Soft failure — re-queueable by the next worker pass via the
        # ``claim_next_job`` predicate.
        job.status = TranslationJobStatus.FAILED
    db.commit()
    db.refresh(job)
    return job
