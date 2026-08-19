"""Cron-driven worker that drains the translation queue.

This endpoint is not user-facing. A cron driver (Vercel Cron, Supabase
Edge Function, or anything else that can POST on a schedule) calls it
periodically with a shared-secret header. Per call the worker:

1. Claims the oldest claimable job via ``claim_next_job`` (one
   ``SELECT ... FOR UPDATE SKIP LOCKED`` so concurrent crons never
   grab the same row).
2. Runs the existing ``translate_course_content`` orchestrator.
3. Marks the job ``done`` (success) or ``failed`` / ``failed_permanent``
   (failure — same 5-attempt cap as cv rows).
4. Returns a small JSON payload the driver can log.

One-job-per-tick is deliberate: each tick is bounded by one Vercel
function lifetime, and a per-call budget keeps the worker observable
(every claim shows up as one row in the driver's logs). If the queue
backs up, the cron schedule needs to fire more often — that's a
config knob, not a code change.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session  # noqa: TC002 — used by FastAPI Depends at runtime

from app.api.dependencies import require_worker_secret
from app.core.config import settings
from app.core.database import get_db
from app.core.metrics import emit, gauge, timing
from app.services.course_service import get_course
from app.services.daily_challenge.translate import translate_pending_questions
from app.services.staged_edits import promote_ready_fields
from app.services.translation.budget import worker_budget
from app.services.translation.completeness import promote_if_complete
from app.services.translation.course_pipeline import (
    merge_orchestrator_reports,
    translate_course_content,
)
from app.services.translation.queue import (
    claim_next_job,
    get_queue_status,
    mark_job_done,
    mark_job_failed,
    mark_job_paused,
    record_job_failure,
)
from app.services.translation.reconciler import sweep_courses
from app.services.translation.staged_pipeline import translate_staged_edits

if TYPE_CHECKING:
    from app.models.translation_job import TranslationJob
    from app.services.translation.orchestrator import OrchestratorReport


logger = logging.getLogger(__name__)

# Questions the idle sweep repairs per tick. One question is about a
# dozen provider calls, so this is roughly a minute of work — and it only
# ever runs on a tick that had nothing else to do.
_IDLE_POOL_SWEEP_LIMIT = 5

router = APIRouter(prefix="/internal", tags=["internal"])


class WorkerTickResponse(BaseModel):
    """Worker reports back so the cron driver can log + alert.

    ``status`` is one of ``"idle"`` (queue empty and nothing behind),
    ``"swept"`` (queue was empty, and the sweep found courses to
    translate), ``"done"``,
    ``"paused"`` (budget spent mid-course, job re-queued to continue on
    the next tick), or ``"failed"``. ``job_id`` is null only when idle.
    ``attempts`` is the post-tick count on the job.
    """

    status: str
    job_id: str | None = None
    course_id: str | None = None
    attempts: int | None = None

    # What the tick actually did. The pipeline logs this at INFO, and on
    # this deployment INFO from application loggers does not reach the
    # log drain — only the platform's own request lines do. That left
    # the only externally visible signal as a status word, and "done"
    # covers both "translated four hundred fields" and "walked the whole
    # tree and wrote nothing". Those need telling apart from outside,
    # without a log search and without database access.
    translated: int | None = None
    skipped: int | None = None
    failed_fields: int | None = None
    needs_review: int | None = None
    planned: int | None = None


def _emit_queue_gauges(db: Session) -> None:
    """Emit per-status queue depth gauges so the Datadog dashboard +
    backlog monitor have something to plot.

    Wrapped in try/except: a metric failure must NEVER break the
    worker tick. If Datadog goes dark for a few minutes that's fine;
    the queue itself drains regardless.
    """
    try:
        counts = get_queue_status(db)
        processing = int(counts.get("processing", 0))
        gauge("equip.translation.queue_depth", float(counts.get("queued", 0) + counts.get("failed", 0)))
        gauge("equip.translation.queue_processing", float(processing))
        gauge("equip.translation.queue_failed_permanent", float(counts.get("failed_permanent", 0)))
        if processing:
            # WARNING so it actually ships to Datadog (the in-process handler
            # is WARNING+; the INFO gauge lines above only reach stdout). The
            # "[Equip] Translation jobs stuck in processing" monitor watches
            # this message — its previous form queried a custom metric that
            # no pipeline ever produced, so it could never fire.
            # Any job still claimed when a tick begins has outlived the
            # invocation that claimed it: the reaper releases them after
            # eight minutes, so a healthy queue shows zero here at tick
            # start. The old threshold of "more than three" put the
            # realistic case — one or two permanently wedged jobs —
            # below the floor, where it was invisible.
            logger.warning("translation worker: %s jobs stuck in processing", processing)
    except Exception:
        return


def _emit_field_outcomes(report: OrchestratorReport) -> None:
    """How many fields this tick actually moved, by outcome.

    Until now the only record of that lived in one INFO line — which the
    Datadog index drops — and in the HTTP response body, which nobody
    reads. Every metric the pipeline had described the *queue*, so a
    worker that walked a thousand fields and wrote none of them looked
    identical to a worker with nothing to do: queue empty, duration
    healthy, status "done". Production span that way for an hour.

    With this, "translated is flat while the queue is not" is a
    condition a monitor can express.
    """
    try:
        for outcome, count in (
            ("translated", report.translated),
            ("skipped", report.skipped),
            ("failed", report.failed),
            ("needs_review", report.needs_review),
        ):
            if count:
                emit("equip.translation.fields_total", float(count), outcome=outcome)
    except Exception:
        return


def _emit_translation_duration(start_monotonic: float, *, outcome: str) -> None:
    """Emit ``equip.translation.duration_ms`` keyed by outcome.

    Tagged with ``outcome={done,failed}`` so the dashboard can split
    the latency curve by success vs failure — a sustained gap between
    the two distributions usually means the failure path is timing
    out on an upstream call.

    Wrapped in try/except so a metric failure cannot break the worker.
    """
    try:
        elapsed_ms = (time.monotonic() - start_monotonic) * 1000.0
        timing("equip.translation.duration_ms", elapsed_ms, outcome=outcome)
    except Exception:
        return


def _run_one_tick(db: Session) -> WorkerTickResponse:
    """One claim → process → mark cycle. Extracted so tests can drive
    it directly without going through the FastAPI dependency stack."""
    # Emit queue gauges BEFORE the claim so the timeseries shows the
    # backlog at tick start (post-claim values would be off-by-one for
    # the row we're about to grab).
    _emit_queue_gauges(db)
    job: TranslationJob | None = claim_next_job(db)
    if job is None:
        # Nothing queued — so go looking rather than going back to sleep.
        #
        # The queue only ever holds what an event put there, and two
        # things never raise an event: a language switched on after the
        # content was written, and a pass that failed and was never
        # retried. Both are invisible to a worker that only drains.
        # The sweep re-examines the least recently checked courses, a
        # few per tick, and queues anything with a gap — so "somebody
        # has to remember to re-translate everything" stops being a
        # step anyone performs. See ``translation/reconciler.py``.
        sweep = sweep_courses(db)
        if sweep.found_work:
            logger.info("worker: idle queue, sweep queued %d course(s)", sweep.queued)
            return WorkerTickResponse(status="swept")

        # Still nothing. The Daily Challenge pool has the same kind of
        # backlog and no minute-by-minute worker of its own: its sweep
        # rides along with the nightly generator, two questions a night,
        # which is right for catching a question written before a
        # language existed and hopeless for anything larger. Raising
        # TRANSLATOR_VERSION left three thousand rows behind it — at two
        # questions a night, four months.
        #
        # This tick is idle and paid for either way. Sweeping the pool
        # here costs nothing extra and leaves the nightly budget alone,
        # and the time budget keeps it inside one invocation.
        pool_budget = worker_budget(
            seconds=settings.TRANSLATION_WORKER_BUDGET_SECONDS,
            gemini_timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
        )
        try:
            pool = translate_pending_questions(db, limit=_IDLE_POOL_SWEEP_LIMIT, budget=pool_budget)
        except Exception as exc:
            db.rollback()
            logger.warning("worker: idle pool sweep failed: %s", exc)
            return WorkerTickResponse(status="idle")
        if pool.questions:
            logger.info(
                "worker: idle queue, swept %d question(s) from the pool (%d rows)",
                pool.questions,
                pool.rows.translated,
            )
            return WorkerTickResponse(
                status="swept",
                translated=pool.rows.translated,
                skipped=pool.rows.skipped,
                failed_fields=pool.rows.failed,
                needs_review=pool.rows.needs_review,
            )
        return WorkerTickResponse(status="idle")

    course_id = job.course_id
    job_pk = job.id
    job_id = str(job.id)
    attempts = job.attempts
    course = get_course(db, course_id)
    if course is None:
        # Course deleted between enqueue and claim — terminate the job
        # with a permanent failure so the queue doesn't spin on it
        # forever. The cascade FK already nulled the row in some
        # deployments; defensive handling here means the worker
        # never crashes on a missing parent.
        mark_job_failed(db, job, error=f"course {course_id!r} not found at claim time")
        return WorkerTickResponse(
            status="failed",
            job_id=job_id,
            course_id=course_id,
            attempts=attempts,
        )

    # Measure end-to-end translate_course_content time. ``time.monotonic``
    # is correct here (not affected by NTP / system clock jumps); we want
    # elapsed wall time, not absolute timestamps.
    tick_start = time.monotonic()
    budget = worker_budget(
        seconds=settings.TRANSLATION_WORKER_BUDGET_SECONDS,
        gemini_timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
    )
    try:
        # Held edits first. They are what a teacher is actively waiting
        # on — a correction they made to a live course, invisible to
        # students until every language has it — and there are only ever
        # a handful. The course walk behind them can be thousands of
        # fields, and letting it go first would put a one-line fix
        # behind a full re-check of the whole tree.
        report = translate_staged_edits(db, course, budget=budget)
        promote_ready_fields(db, course)
        if not report.incomplete:
            report = merge_orchestrator_reports(
                report,
                translate_course_content(db, course, budget=budget),
            )
    except SQLAlchemyError as exc:
        # A SQLAlchemyError poisons the transaction, so we must rollback
        # before writing the status flip. But a plain rollback would also
        # discard the attempts increment that claim_next_job only flushed
        # (not committed) — leaving mark_job_failed to read the pre-claim
        # count, never hit the cap, and re-queue a deterministically
        # DB-failing job forever. record_job_failure rolls back AND
        # re-stamps the post-claim ``attempts`` (captured above), so the
        # cap check works and the job can reach failed_permanent.
        record_job_failure(db, job_id=job_pk, attempts=attempts, error=f"sqlalchemy: {exc}")
        # Emit duration even on failure so the dashboard's p50/p95
        # tile includes the cost of failed work (the operator needs
        # to see if failures are also slow → upstream timeout).
        _emit_translation_duration(tick_start, outcome="failed")
        logger.exception("translation_worker: SQLAlchemyError on job %s course %s", job_id, course_id)
        return WorkerTickResponse(
            status="failed",
            job_id=job_id,
            course_id=course_id,
            attempts=attempts,
        )
    except Exception as exc:
        mark_job_failed(db, job, error=f"{type(exc).__name__}: {exc}")
        _emit_translation_duration(tick_start, outcome="failed")
        logger.exception(
            "translation_worker: unexpected error on job %s course %s",
            job_id,
            course_id,
        )
        return WorkerTickResponse(
            status="failed",
            job_id=job_id,
            course_id=course_id,
            attempts=attempts,
        )

    # The pass stopped on the clock, not on the work. Everything it
    # translated is committed; the job goes back in the queue and the
    # next tick — a minute later — resumes where this one left off, at
    # no cost for what is already done. A large course is now a course
    # that takes several ticks, which is the thing it always was; what
    # changed is that we no longer mistake that for failure.
    _emit_field_outcomes(report)
    if report.incomplete:
        _emit_translation_duration(tick_start, outcome="paused")
        mark_job_paused(db, job, made_progress=report.made_progress)
        logger.info(
            "translation_worker: job %s paused mid-course %s after %.0fs (translated=%d needs_review=%d failed=%d)",
            job_id,
            course_id,
            budget.elapsed,
            report.translated,
            report.needs_review,
            report.failed,
        )
        return WorkerTickResponse(
            status="paused",
            job_id=job_id,
            course_id=course_id,
            attempts=job.attempts,
            translated=report.translated,
            skipped=report.skipped,
            failed_fields=report.failed,
            needs_review=report.needs_review,
            planned=report.translated + report.skipped + report.failed + report.needs_review,
        )

    _emit_translation_duration(tick_start, outcome="done")
    mark_job_done(db, job)

    # A course the teacher sent out sits in ``publishing`` until every
    # language has it and every translation has passed its check. This
    # pass may be the one that completed it — that is what makes
    # publication a state the course reaches rather than a flag someone
    # flipped ahead of the work. Never blocks the job's completion: the
    # translations are written either way.
    try:
        promote_if_complete(db, course)
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "translation_worker: promotion check failed for course %s after job %s",
            course_id,
            job_id,
        )

    return WorkerTickResponse(
        status="done",
        job_id=job_id,
        course_id=course_id,
        attempts=attempts,
        translated=report.translated,
        skipped=report.skipped,
        failed_fields=report.failed,
        needs_review=report.needs_review,
        planned=report.translated + report.skipped + report.failed + report.needs_review,
    )


@router.post(
    "/translation-worker",
    response_model=WorkerTickResponse,
    summary="Drain one translation job from the queue",
    responses={
        200: {"description": "One job processed (``status`` is ``done`` / ``failed`` / ``idle``)"},
        401: {"description": "Worker secret missing or wrong"},
        503: {"description": "TRANSLATION_WORKER_SECRET is not configured on this deployment"},
    },
)
def drain_one_job(
    db: Session = Depends(get_db),
    _: None = Depends(require_worker_secret),
) -> WorkerTickResponse:
    """Cron-callable. Claims one job and runs the orchestrator."""
    return _run_one_tick(db)


@router.get(
    "/translation-worker",
    response_model=WorkerTickResponse,
    summary="Drain one translation job (GET alias for Vercel Cron)",
    responses={
        200: {"description": "Same payload as the POST variant."},
        401: {"description": "Worker secret missing or wrong"},
        503: {"description": "TRANSLATION_WORKER_SECRET is not configured on this deployment"},
    },
)
def drain_one_job_get(
    db: Session = Depends(get_db),
    _: None = Depends(require_worker_secret),
) -> WorkerTickResponse:
    """Vercel Cron Jobs send GET — same body as the POST handler. Kept
    as a thin alias instead of changing the canonical method so test
    drivers and admin tools that already use POST stay working.
    """
    return _run_one_tick(db)


class QueueHealthResponse(BaseModel):
    """Per-status counts for the ``translation_jobs`` queue."""

    queued: int
    processing: int
    done: int
    failed: int
    failed_permanent: int


@router.get(
    "/translation-queue/health",
    response_model=QueueHealthResponse,
    summary="Per-status counts on the translation_jobs queue",
    responses={
        200: {"description": "Current queue depth + in-flight + failure counts."},
        401: {"description": "Worker secret missing or wrong"},
        503: {"description": "TRANSLATION_WORKER_SECRET is not configured on this deployment"},
    },
)
def queue_health(
    db: Session = Depends(get_db),
    _: None = Depends(require_worker_secret),
) -> QueueHealthResponse:
    """Authenticated health probe — same secret as the worker.

    Lets an operator curl-check backlog without poking the database:

        curl -H "X-Worker-Secret: <secret>" \\
             https://api.equipbible.com/api/v1/internal/translation-queue/health

    Same secret intentionally — anyone allowed to drive the worker is
    allowed to read the queue shape.
    """
    counts = get_queue_status(db)
    return QueueHealthResponse(
        queued=counts.get("queued", 0),
        processing=counts.get("processing", 0),
        done=counts.get("done", 0),
        failed=counts.get("failed", 0),
        failed_permanent=counts.get("failed_permanent", 0),
    )


# Public surface for tests + future admin tooling.
__all__ = [
    "_emit_queue_gauges",
    "_emit_translation_duration",
    "_run_one_tick",
    "router",
]


def generate_worker_secret() -> str:
    """Convenience for the operator setting up the cron driver. Use
    ``python -c 'from app.api.v1.internal_translation_worker import generate_worker_secret; print(generate_worker_secret())'``
    to mint a fresh secret, then put it in both ``TRANSLATION_WORKER_SECRET``
    on the backend and the cron driver's header config.
    """
    return secrets.token_urlsafe(48)
