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

from app.api.v1.internal_translation_worker import _require_worker_secret
from app.core.config import settings
from app.core.database import get_db
from app.services.daily_challenge.llm import GeminiPromptClient
from app.services.daily_challenge.replenish import replenish_one_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

# A free-tier key 429s on a ~7-call burst, so space calls out (still well
# inside a Vercel Pro 60s function: ~7 x 4s ~= 28s) and give a 429 a real
# cooldown. On a paid key this is harmless headroom.
_THROTTLE_SECONDS = 4.0
_MAX_RETRIES = 4


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

    return ReplenishResponse(
        status=outcome.status,
        question_id=outcome.question_id,
        challenge_date=outcome.challenge_date,
        passage=outcome.passage,
        detail=outcome.detail,
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
    _: None = Depends(_require_worker_secret),
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
    _: None = Depends(_require_worker_secret),
) -> ReplenishResponse:
    """Vercel Cron Jobs send GET — same body as POST."""
    return _run_one_tick(db)


__all__ = ["_run_one_tick", "router"]
