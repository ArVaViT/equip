"""Schedule lookup for the Daily Challenge.

Sprint 2 covers the read path — ``get_today_question`` is what every
student-facing route uses to find "what's today's question?". The
admin-side scheduling UI (set/replace a question for a given UTC date)
lands in Sprint 3 alongside the editorial pipeline.

Today's UTC date is the natural key — there's at most one row in
``daily_challenge_schedule`` per ``challenge_date``. The schedule row
points at a question whose status must be ``published`` and which
isn't rejected; the Postgres trigger ``dc_schedule_assert_publishable``
enforces that gate at write time, so this read path can trust the
target question is valid.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload

from app.models.daily_challenge import (
    DailyChallengeQuestion,
    DailyChallengeSchedule,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def utc_today() -> date:
    """Single source of truth for "what's today?" — UTC-only, no
    per-user timezone (deferred per the locked decisions)."""
    return datetime.now(UTC).date()


def get_today_question(
    db: Session,
    *,
    on_date: date | None = None,
) -> tuple[DailyChallengeSchedule, DailyChallengeQuestion] | None:
    """Return today's (or another date's) scheduled question with
    its options eager-loaded.

    Returns ``None`` when no question is scheduled for the date —
    the route layer maps that to a ``daily_challenge.not_scheduled``
    error envelope.

    ``on_date`` is exposed so the archive endpoint can reuse this
    helper for any past date; default is UTC today.
    """
    target_date = on_date or utc_today()

    schedule = (
        db.query(DailyChallengeSchedule).filter(DailyChallengeSchedule.challenge_date == target_date).one_or_none()
    )
    if schedule is None:
        return None

    question = (
        db.query(DailyChallengeQuestion)
        .options(selectinload(DailyChallengeQuestion.options))
        .filter(DailyChallengeQuestion.id == schedule.question_id)
        .one_or_none()
    )
    if question is None:
        # ON DELETE RESTRICT prevents this in prod, but we still
        # guard against it instead of crashing — would only happen
        # if someone bypassed the FK via raw SQL.
        return None

    return schedule, question
