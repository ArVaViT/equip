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

import hmac
import logging
import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session  # noqa: TC002 — used by FastAPI Depends at runtime

from app.core.config import settings
from app.core.database import get_db
from app.services.course_service import get_course
from app.services.translation.course_pipeline import translate_course_content
from app.services.translation.queue import (
    claim_next_job,
    mark_job_done,
    mark_job_failed,
)

if TYPE_CHECKING:
    from app.models.translation_job import TranslationJob


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


class WorkerTickResponse(BaseModel):
    """Worker reports back so the cron driver can log + alert.

    ``status`` is one of ``"idle"`` (queue empty), ``"done"``, or
    ``"failed"``. ``job_id`` is null only when idle. ``attempts``
    is the post-tick count on the job.
    """

    status: str
    job_id: str | None = None
    course_id: str | None = None
    attempts: int | None = None


def _require_worker_secret(
    x_worker_secret: str | None = Header(default=None, alias="X-Worker-Secret"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """Constant-time shared-secret check. Refuses every request when
    the env var is unset — opt-in by design so dev environments without
    the queue cron don't accidentally expose the endpoint.

    Accepts two header shapes so a single env var serves both flows:

    * ``X-Worker-Secret: <secret>`` — direct human / test access.
    * ``Authorization: Bearer <secret>`` — what Vercel Cron Jobs send
      automatically (Vercel signs each cron request with the
      ``CRON_SECRET`` env var; we map ``TRANSLATION_WORKER_SECRET`` to
      that value at deploy so the auth scheme matches).
    """
    expected = settings.TRANSLATION_WORKER_SECRET
    if expected is None or not expected.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Translation worker is not configured on this deployment.",
        )
    expected_value = expected.get_secret_value()

    presented = x_worker_secret or ""
    if not presented and authorization and authorization.startswith("Bearer "):
        presented = authorization.removeprefix("Bearer ").strip()

    if not hmac.compare_digest(presented, expected_value):
        # 401 with a generic message so a probing attacker can't
        # distinguish 'wrong secret' from 'no secret header'.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Worker authentication failed.",
        )


def _run_one_tick(db: Session) -> WorkerTickResponse:
    """One claim → process → mark cycle. Extracted so tests can drive
    it directly without going through the FastAPI dependency stack."""
    job: TranslationJob | None = claim_next_job(db)
    if job is None:
        return WorkerTickResponse(status="idle")

    course_id = job.course_id
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

    try:
        translate_course_content(db, course)
    except SQLAlchemyError as exc:
        # Roll the session forward to a clean transaction before
        # writing the job-status flip; otherwise the mark_job_failed
        # commit would itself raise on the still-poisoned session.
        db.rollback()
        mark_job_failed(db, job, error=f"sqlalchemy: {exc}")
        logger.exception("translation_worker: SQLAlchemyError on job %s course %s", job_id, course_id)
        return WorkerTickResponse(
            status="failed",
            job_id=job_id,
            course_id=course_id,
            attempts=attempts,
        )
    except Exception as exc:
        mark_job_failed(db, job, error=f"{type(exc).__name__}: {exc}")
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

    mark_job_done(db, job)
    return WorkerTickResponse(
        status="done",
        job_id=job_id,
        course_id=course_id,
        attempts=attempts,
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
    _: None = Depends(_require_worker_secret),
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
    _: None = Depends(_require_worker_secret),
) -> WorkerTickResponse:
    """Vercel Cron Jobs send GET — same body as the POST handler. Kept
    as a thin alias instead of changing the canonical method so test
    drivers and admin tools that already use POST stay working.
    """
    return _run_one_tick(db)


# Public surface for tests + future admin tooling.
__all__ = ["_require_worker_secret", "_run_one_tick", "router"]


def generate_worker_secret() -> str:
    """Convenience for the operator setting up the cron driver. Use
    ``python -c 'from app.api.v1.internal_translation_worker import generate_worker_secret; print(generate_worker_secret())'``
    to mint a fresh secret, then put it in both ``TRANSLATION_WORKER_SECRET``
    on the backend and the cron driver's header config.
    """
    return secrets.token_urlsafe(48)
