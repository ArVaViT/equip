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

import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models.daily_challenge import (
    DailyChallengeQuestion,
    DailyChallengeSchedule,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def utc_today() -> date:
    """Single source of truth for "what's today?" — UTC-only, no
    per-user timezone (deferred per the locked decisions)."""
    return datetime.now(UTC).date()


def _autofill_today_schedule(db: Session, target_date: date) -> DailyChallengeSchedule | None:
    """Fill a gap in the schedule from the published question pool.

    The editorial pipeline can fall behind (Gemini quota throttles seeding),
    leaving today with no scheduled row — which would surface to students as
    a ``not_scheduled`` 404. Rather than go dark, pick a published,
    non-rejected question deterministically by date (so the same question
    shows all day and rotates daily) and persist a real schedule row. An
    explicitly-seeded question always wins because the caller short-circuits
    on the existing row before reaching here.

    Returns ``None`` only when there are no publishable questions at all.
    """
    ids = [
        row[0]
        for row in (
            db.query(DailyChallengeQuestion.id)
            .filter(
                DailyChallengeQuestion.status == "published",
                DailyChallengeQuestion.rejected.is_(False),
            )
            .order_by(DailyChallengeQuestion.id)
            .all()
        )
    ]
    if not ids:
        return None

    question_id = ids[target_date.toordinal() % len(ids)]
    schedule = DailyChallengeSchedule(challenge_date=target_date, question_id=question_id)
    db.add(schedule)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request already filled today's slot — use that row.
        db.rollback()
        return (
            db.query(DailyChallengeSchedule).filter(DailyChallengeSchedule.challenge_date == target_date).one_or_none()
        )
    # WARNING, not info: the in-process Datadog handler ships WARNING+ only,
    # and the "[Equip] Daily Challenge schedule ran dry" log monitor watches
    # this exact message — at INFO it never reached Datadog and the monitor
    # was permanently blind to the silent outage it exists to catch.
    logger.warning(
        "daily_challenge: auto-filled schedule for %s from published pool (question %s)",
        target_date.isoformat(),
        question_id,
    )
    return schedule


def get_today_question(
    db: Session,
    *,
    on_date: date | None = None,
    allow_fallback: bool = False,
) -> tuple[DailyChallengeSchedule, DailyChallengeQuestion] | None:
    """Return today's (or another date's) scheduled question with
    its options eager-loaded.

    Returns ``None`` when no question is scheduled for the date —
    the route layer maps that to a ``daily_challenge.not_scheduled``
    error envelope.

    ``on_date`` is exposed so the archive endpoint can reuse this
    helper for any past date; default is UTC today.

    ``allow_fallback`` (live "today" path only) auto-fills a missing
    schedule from the published pool so the challenge never goes dark.
    The archive path leaves it ``False`` — an unscheduled past date is
    genuinely empty.
    """
    target_date = on_date or utc_today()

    schedule = (
        db.query(DailyChallengeSchedule).filter(DailyChallengeSchedule.challenge_date == target_date).one_or_none()
    )
    if schedule is None:
        if not (allow_fallback and target_date == utc_today()):
            return None
        schedule = _autofill_today_schedule(db, target_date)
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
