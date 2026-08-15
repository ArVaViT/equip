"""Cron-driven worker that appends ONE Daily Challenge question per day.

Not user-facing. A daily cron (Vercel Cron) POSTs/GETs here with the same
shared secret as the translation worker (Vercel signs every cron request
with ``CRON_SECRET``; we map ``TRANSLATION_WORKER_SECRET`` to it). Per
call it generates one question from the next seed passage and schedules
it at the end of the list — see ``services/daily_challenge/replenish.py``.

One-passage-per-tick is the whole point: it keeps daily Gemini usage
(~7 calls) under the free-tier daily budget, so the bank refills forever
without a bulk run that trips the quota.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session  # noqa: TC002 — used by FastAPI Depends at runtime

from app.api.dependencies import require_worker_secret
from app.core.config import settings
from app.core.database import get_db
from app.services.daily_challenge.llm import GeminiPromptClient
from app.services.daily_challenge.replenish import replenish_one_question
from app.services.daily_challenge.translate import translate_pending_questions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

# A free-tier key 429s on a ~7-call burst, so space calls out and give a
# 429 a real cooldown. Vercel Fluid Compute Pro: 300s effective function
# timeout (verified 2026-06-11); worst-case tick ~65-135s fits with 2x
# headroom. On a paid key this is harmless headroom.
_THROTTLE_SECONDS = 4.0
_MAX_RETRIES = 4

# Questions repaired per tick by the translation sweep. See the comment
# at the call site for why the number is small.
_TRANSLATION_SWEEP_LIMIT = 2


class ReplenishResponse(BaseModel):
    """Worker reports back so the cron driver can log + alert.

    ``status``: ``scheduled`` (new question appended), ``no_survivors``
    (generated but all candidates failed a gate), ``error`` (retry next
    tick), ``no_actor`` (no admin to attribute to), or ``unconfigured``
    (no Gemini key on this deployment)."""

    status: str
    question_id: str | None = None
    challenge_date: str | None = None
    passage: str | None = None
    detail: str | None = None
    # How much of the backlog this tick repaired. Reported so the cron
    # log answers "is the pool catching up or falling behind?" without a
    # database query.
    translated_rows: int = 0
    questions_swept: int = 0


def _run_one_tick(db: Session) -> ReplenishResponse:
    """One generate → publish → schedule cycle. Extracted so tests can
    drive it without the FastAPI dependency stack."""
    api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else ""
    if not api_key:
        return ReplenishResponse(status="unconfigured", detail="GEMINI_API_KEY not set on this deployment")

    model = settings.GEMINI_MODEL or "gemini-2.5-flash-lite"

    with GeminiPromptClient(
        api_key=api_key,
        default_model=model,
        max_retries=_MAX_RETRIES,
        min_request_interval_seconds=_THROTTLE_SECONDS,
        retry_backoff_seconds=_THROTTLE_SECONDS,
        retry_backoff_cap_seconds=30.0,
    ) as client:
        outcome = replenish_one_question(db, client=client)

    # Then repair a little of the backlog. Questions written before a
    # language existed have nobody to translate them — the generator only
    # ever produces English and Russian, and there is no course above a
    # Daily Challenge question for the edit-triggered pipeline to hang
    # off. Without this sweep the gap is permanent for every question
    # already in the bank.
    #
    # Two per tick, deliberately: one question costs ~12 provider calls
    # (question text, explanation, four options, each into three
    # languages), and this worker shares a daily Gemini budget with the
    # generation run above it. Sipping, not gulping.
    swept = 0
    translated = 0
    try:
        sweep = translate_pending_questions(db, limit=_TRANSLATION_SWEEP_LIMIT)
        translated = sweep.rows.translated
        swept = sweep.questions
    except Exception as exc:
        db.rollback()
        logger.warning("daily-challenge worker: translation sweep failed: %s", exc)

    return ReplenishResponse(
        status=outcome.status,
        question_id=outcome.question_id,
        challenge_date=outcome.challenge_date,
        passage=outcome.passage,
        detail=outcome.detail,
        translated_rows=translated,
        questions_swept=swept,
    )


@router.post(
    "/daily-challenge-worker",
    response_model=ReplenishResponse,
    summary="Generate + append one Daily Challenge question",
    responses={
        200: {"description": "One tick ran (``status`` describes the outcome)."},
        401: {"description": "Worker secret missing or wrong"},
        503: {"description": "TRANSLATION_WORKER_SECRET is not configured on this deployment"},
    },
)
def replenish_post(
    db: Session = Depends(get_db),
    _: None = Depends(require_worker_secret),
) -> ReplenishResponse:
    """Cron-callable. Generates one question and appends it."""
    return _run_one_tick(db)


@router.get(
    "/daily-challenge-worker",
    response_model=ReplenishResponse,
    summary="Generate + append one Daily Challenge question (GET alias for Vercel Cron)",
    responses={
        200: {"description": "Same payload as the POST variant."},
        401: {"description": "Worker secret missing or wrong"},
        503: {"description": "TRANSLATION_WORKER_SECRET is not configured on this deployment"},
    },
)
def replenish_get(
    db: Session = Depends(get_db),
    _: None = Depends(require_worker_secret),
) -> ReplenishResponse:
    """Vercel Cron Jobs send GET — same body as POST."""
    return _run_one_tick(db)


__all__ = ["_run_one_tick", "router"]
