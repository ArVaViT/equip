"""Daily auto-replenish: generate ONE Daily Challenge question and append
it to the end of the schedule.

The bulk bootstrap (``scripts/bootstrap_daily_challenge_bank.py``) fires a
~7-call burst per passage, which blows a free-tier Gemini quota when run
210x back to back. This worker instead does exactly one passage per call,
driven by a once-a-day cron — ~7 calls/day stays comfortably under the
free daily budget (the same reason the translation cron survives on the
free tier: it sips, it doesn't gulp).

Per tick it:
  1. picks the next seed passage (cursor = current question count, so it
     advances every success and cycles through the 210-passage list),
  2. runs the full generation pipeline for that one passage (6-round
     confrontation + scripture/doctrinal/bilingual gates),
  3. promotes the surviving draft → published,
  4. schedules it on the next unscheduled date (the end of the list).

Any failure (quota 429, gate rejection, publish/schedule error) returns a
status string and leaves the DB clean — the next day's tick simply tries
again. Autofill keeps the live challenge working in the meantime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func

from app.models.daily_challenge import (
    DailyChallengeQuestion,
    DailyChallengeQuestionStatus,
    DailyChallengeSchedule,
)
from app.models.user import User, UserRole
from app.services.daily_challenge.admin import (
    promote_status,
    publish_question,
    schedule_for_date,
)
from app.services.daily_challenge.orchestrator import GenerationRequest, run_generation
from app.services.daily_challenge.seed_passages import SEED_PASSAGES

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from app.services.daily_challenge.llm import GeminiPromptClient

logger = logging.getLogger(__name__)

# draft → scripture_validated → doctrinal_reviewed → bilingual_reviewed →
# pilot_passed (4 forward edges), matching the bootstrap.
_PROMOTE_STAGES_FROM_DRAFT = 4


@dataclass(slots=True)
class ReplenishOutcome:
    """Worker tick result. ``status`` is one of ``scheduled`` (a new
    question was published + appended), ``no_survivors`` (generation ran
    but every candidate was rejected at a gate), ``error`` (generation or
    persistence failed — try again next tick), or ``no_actor`` (no admin
    user to attribute the editorial actions to)."""

    status: str
    question_id: str | None = None
    challenge_date: str | None = None
    passage: str | None = None
    detail: str | None = None


def _next_unscheduled_date(db: Session, *, start: date) -> date:
    """Earliest date ``>= start`` with no schedule row. Forward-only — we
    never overwrite an existing day (mirrors the bootstrap)."""
    taken = {
        s.challenge_date
        for s in db.query(DailyChallengeSchedule).filter(DailyChallengeSchedule.challenge_date >= start).all()
    }
    d = start
    while d in taken:
        d += timedelta(days=1)
    return d


def _pick_passage(db: Session) -> dict[str, object]:
    """Cursor = current question count, so each success advances the
    pointer and the worker cycles through the seed list without repeats
    until it wraps (210 days)."""
    count = db.query(func.count(DailyChallengeQuestion.id)).scalar() or 0
    return SEED_PASSAGES[count % len(SEED_PASSAGES)]


def _system_actor_id(db: Session) -> uuid.UUID | None:
    """Editorial actions (promote/publish/schedule) are audit-logged, so
    they need a real actor. Attribute the bot's work to the oldest active
    admin rather than hardcoding a user id into the deployment."""
    return (
        db.query(User.id)
        .filter(User.role == UserRole.ADMIN.value, User.deactivated_at.is_(None))
        .order_by(User.created_at)
        .limit(1)
        .scalar()
    )


def replenish_one_question(
    db: Session,
    *,
    client: GeminiPromptClient,
    actor_id: uuid.UUID | None = None,
    n_candidates: int = 2,
    start_date: date | None = None,
) -> ReplenishOutcome:
    """Generate one question and append it to the schedule. See module
    docstring. ``actor_id`` defaults to the oldest active admin."""
    actor = actor_id or _system_actor_id(db)
    if actor is None:
        return ReplenishOutcome(status="no_actor", detail="no active admin user to attribute generation to")

    passage = _pick_passage(db)
    label = f"{passage['book']} {passage['chapter']}"
    request = GenerationRequest(
        book=str(passage["book"]),
        chapter=int(passage["chapter"]),  # type: ignore[call-overload]
        verse_from=passage.get("verse_from"),  # type: ignore[arg-type]
        verse_to=passage.get("verse_to"),  # type: ignore[arg-type]
        n_candidates_per_agent=n_candidates,
        max_survivors=1,
        created_by=actor,
    )

    try:
        outcome = run_generation(db, client=client, request=request)
    except Exception as exc:  # any generation failure -> retry next tick
        db.rollback()
        logger.warning("replenish: generation failed for %s: %s", label, exc)
        return ReplenishOutcome(status="error", passage=label, detail=f"generation: {exc}")

    if not outcome.created_question_ids:
        logger.info("replenish: no survivors for %s (all candidates rejected)", label)
        return ReplenishOutcome(status="no_survivors", passage=label, detail="all candidates rejected at a gate")

    qid = outcome.created_question_ids[0]
    question = db.query(DailyChallengeQuestion).filter_by(id=qid).one()
    try:
        for _ in range(_PROMOTE_STAGES_FROM_DRAFT):
            question = promote_status(db, question=question, actor_id=actor)
        if question.status != DailyChallengeQuestionStatus.PILOT_PASSED.value:
            return ReplenishOutcome(
                status="error", question_id=str(qid), passage=label, detail=f"stuck at status={question.status}"
            )
        question = publish_question(db, question=question, actor_id=actor)
    except Exception as exc:
        db.rollback()
        logger.warning("replenish: publish failed for %s: %s", qid, exc)
        return ReplenishOutcome(status="error", question_id=str(qid), passage=label, detail=f"publish: {exc}")

    cursor = _next_unscheduled_date(db, start=start_date or datetime.now(UTC).date())
    try:
        schedule_for_date(db, question=question, on_date=cursor, actor_id=actor)
    except Exception as exc:
        db.rollback()
        logger.warning("replenish: schedule failed for %s on %s: %s", qid, cursor, exc)
        return ReplenishOutcome(status="error", question_id=str(qid), passage=label, detail=f"schedule: {exc}")

    logger.info("replenish: scheduled %s (%s) for %s", qid, label, cursor.isoformat())
    return ReplenishOutcome(status="scheduled", question_id=str(qid), challenge_date=cursor.isoformat(), passage=label)
