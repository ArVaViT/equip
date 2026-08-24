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
  ``failed_permanent`` and the admin reset surface is
  the only way back to ``failed``.

The session lifecycle is deliberately strict: helpers commit at the
end so a follow-up exception in the caller doesn't bleed claimed-row
state across requests.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select

from app.models.translation_job import (
    TRANSLATION_JOB_MAX_ATTEMPTS,
    TranslationJob,
    TranslationJobStatus,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

# A worker that claimed a job but never reported back — Vercel function
# timeout/OOM mid-run — leaves the row stuck in ``processing`` forever:
# never re-claimed, never failed, and it blocks re-enqueue of that course.
# A single serverless invocation is capped well under this window, so any
# job still ``processing`` past it is certainly dead and safe to re-claim.
#
# Eight minutes, down from fifteen: a tick now bounds itself with
# ``TRANSLATION_WORKER_BUDGET_SECONDS`` plus the worst case of the one
# call it may still have started, so the longest a live tick can run is
# under five minutes. The window only has to outlast that, and every
# minute above it is a minute a killed job spends waiting instead of
# translating.
_PROCESSING_STALE_AFTER = timedelta(minutes=8)


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
    # Only a job that has not started yet stands in for this one.
    #
    # A job already ``processing`` used to count too, and that quietly
    # dropped edits. The worker reads held edits once, at the start of
    # its tick, and marks the job done at the end; an edit saved in
    # between was staged, found a "pending" job, enqueued nothing, and
    # was then left with no job at all — invisible to the reconciler as
    # well, which reads content_versions while the edit sits in staging.
    # The window is a whole tick, and a large course is processing for
    # most of every tick.
    #
    # Enqueuing anyway is close to free: the worker's own decide phase
    # skips everything already done, so a redundant job costs one plan
    # and no provider calls.
    existing = (
        db.execute(
            select(TranslationJob)
            .where(TranslationJob.course_id == course_id)
            .where(TranslationJob.status == TranslationJobStatus.QUEUED)
            .order_by(TranslationJob.enqueued_at)
            .limit(1)
        )
        .scalars()
        .first()
    )
    if existing is not None:
        logger.info(
            "translation_queue: course %s already has a queued job %s; skipping enqueue",
            course_id,
            existing.id,
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
    outage doesn't leak a job into oblivion. Jobs stuck in ``processing``
    past ``_PROCESSING_STALE_AFTER`` (a worker that died mid-run) are also
    re-claimed so they recover instead of blocking the course forever.

    Returns ``None`` when no claimable job exists; the worker endpoint
    then 204s and the cron re-fires on the next tick.

    The session is left in an OPEN transaction holding the row lock
    until the caller commits — that's the point: the worker's
    ``mark_job_done`` / ``mark_job_failed`` call commits the status
    flip in the same transaction so the row visibility window is
    minimised.
    """
    stale_before = datetime.now(UTC) - _PROCESSING_STALE_AFTER
    job = (
        db.execute(
            select(TranslationJob)
            .where(
                or_(
                    TranslationJob.status.in_([TranslationJobStatus.QUEUED, TranslationJobStatus.FAILED]),
                    and_(
                        TranslationJob.status == TranslationJobStatus.PROCESSING,
                        TranslationJob.started_at < stale_before,
                    ),
                )
            )
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


def mark_job_paused(db: Session, job: TranslationJob, *, made_progress: bool) -> TranslationJob:
    """Hand the job back unfinished — it ran out of time, not out of luck.

    A course too large for one worker invocation used to be
    indistinguishable from a course that breaks the worker: both left a
    row that never reached ``done``. The difference is whether the tick
    accomplished anything, and it decides what happens to ``attempts``:

    * **Progress made** — reset the counter. The course is moving, one
      budget's worth of fields per tick, and it must not be declared
      permanently failed for being long. This is what the August 2026
      incident needed and did not have.
    * **Nothing moved** — leave the counter where ``claim_next_job`` put
      it. A job that keeps waking up and achieving nothing is not
      merely large, and the attempt cap should still catch it.

    Back to ``queued`` rather than left in ``processing`` so the next
    cron tick claims it immediately instead of waiting out the stale
    window. ``started_at`` is cleared for the same reason.
    """
    job.status = TranslationJobStatus.QUEUED
    job.started_at = None
    job.finished_at = None
    job.last_error = None
    if made_progress:
        job.attempts = 0
    db.commit()
    db.refresh(job)
    logger.info(
        "translation_queue: job %s paused for course %s (progress=%s, attempts=%d)",
        job.id,
        job.course_id,
        made_progress,
        job.attempts,
    )
    return job


def get_queue_status(db: Session) -> dict[str, int]:
    """Return per-status row counts on ``translation_jobs``.

    Used by:
    * The worker tick to emit ``equip.translation.queue_*`` gauges so
      Datadog can show backlog + in-flight + failure curves over time.
    * The ``/internal/translation-queue/health`` endpoint so ops can
      curl-check the queue without poking the database.

    Returns a dict keyed by status value (``queued`` / ``processing``
    / ``done`` / ``failed`` / ``failed_permanent``) with the raw row
    counts. Statuses with zero rows are still present (value 0) so the
    dict shape is stable for downstream consumers.
    """
    rows = db.execute(select(TranslationJob.status, func.count().label("n")).group_by(TranslationJob.status)).all()
    counts: dict[str, int] = {s.value: 0 for s in TranslationJobStatus}
    for row in rows:
        counts[row[0]] = int(row[1])
    return counts


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


def record_job_failure(db: Session, *, job_id: uuid.UUID, attempts: int, error: str) -> TranslationJob | None:
    """Record a worker failure resiliently, independent of the session
    state left by a failed ``translate_course_content`` pass.

    The worker's ``except SQLAlchemyError`` path MUST ``rollback()`` to
    clear the poisoned transaction before it can write anything. But a
    rollback also discards the ``attempts`` increment + ``PROCESSING``
    flip that ``claim_next_job`` only *flushed* (never committed). If we
    then re-read ``job.attempts`` it shows the PRE-claim count, the
    ``>= TRANSLATION_JOB_MAX_ATTEMPTS`` check never trips, and a job that
    deterministically raises a DB error is re-claimed on every cron tick
    forever — burning Gemini calls and never reaching
    ``failed_permanent``. (``mark_job_failed`` is correct only when the
    in-session increment is still live, i.e. the no-rollback paths.)

    This helper sidesteps the trap: it rolls the session back to a clean
    transaction, re-fetches the row ``FOR UPDATE``, and stamps the
    caller-supplied ``attempts`` — captured post-claim, so it survives
    the rollback as a plain int. Promotion then sees the correct count.
    Returns ``None`` if the row vanished (e.g. cascade-deleted) between
    claim and failure.
    """
    db.rollback()
    job = db.execute(select(TranslationJob).where(TranslationJob.id == job_id).with_for_update()).scalars().first()
    if job is None:
        return None
    job.attempts = attempts
    job.last_error = error[:2000] if error else None
    job.finished_at = datetime.now(UTC)
    if attempts >= TRANSLATION_JOB_MAX_ATTEMPTS:
        job.status = TranslationJobStatus.FAILED_PERMANENT
    else:
        job.status = TranslationJobStatus.FAILED
    db.commit()
    db.refresh(job)
    return job
