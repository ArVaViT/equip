"""Live attempt submission for the Daily Challenge.

The hot service in Sprint 2. Three failure modes the route layer maps
to typed error envelopes:

* **No question scheduled for today** (``NoScheduleError``) — the
  editorial team has a gap; the frontend hides the daily card.
* **Selected option doesn't belong to today's question**
  (``InvalidOptionError``) — stale frontend cache or a tampered
  request.
* **Already attempted** — handled silently. The partial-unique
  ``(user_id, challenge_date) WHERE is_archive=FALSE`` makes the
  second INSERT raise ``IntegrityError``; we catch it, re-read the
  existing attempt, and return it verbatim. Idempotent on the same
  request shape.

The streak is updated inside the same transaction as the attempt
INSERT, so a rollback rolls back both. The streak service holds
``FOR UPDATE`` on the row.

We materialise ``streak_after`` on the attempt row so the post-submit
response doesn't need a second query and so observability ("what was
the streak right after this attempt?") is one column away.
"""

from __future__ import annotations

import uuid  # noqa: TC003 — used at runtime by dataclass annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.models.daily_challenge import (
    DailyChallengeAttempt,
    DailyChallengeOption,
    DailyChallengeQuestion,
    DailyChallengeSchedule,
)
from app.services.daily_challenge.schedule import get_today_question, utc_today
from app.services.daily_challenge.streak import apply_streak_for_attempt

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class NoScheduleError(Exception):
    """No question is scheduled for today."""


class InvalidOptionError(Exception):
    """The submitted option id doesn't belong to today's question."""

    def __init__(self, *, selected_option_id: uuid.UUID, question_id: uuid.UUID) -> None:
        super().__init__(f"option {selected_option_id} does not belong to question {question_id}")
        self.selected_option_id = selected_option_id
        self.question_id = question_id


@dataclass(frozen=True, slots=True)
class DailyChallengeAttemptOutcome:
    """Service-level result. Route layer maps to ``AttemptResponse``."""

    attempt: DailyChallengeAttempt
    schedule: DailyChallengeSchedule
    question: DailyChallengeQuestion
    correct_option_id: uuid.UUID
    streak_after: int
    is_new_attempt: bool
    """``True`` when this call created the attempt row; ``False`` when
    the user had already submitted today and we returned the existing
    row. The route uses this only for telemetry — the response shape
    is the same either way (the client doesn't care)."""


def _correct_option_for(question: DailyChallengeQuestion) -> DailyChallengeOption:
    """Return the question's correct option. Application-level
    invariant: exactly one. If anything else, raise — the schema let
    a malformed question through and the service refuses to grade it
    rather than silently picking the first correct match."""
    correct = [o for o in question.options if o.is_correct]
    if len(correct) != 1:
        raise RuntimeError(
            f"daily challenge question {question.id} has {len(correct)} correct "
            "options; editorial pipeline failed to enforce the single-correct invariant"
        )
    return correct[0]


def submit_today_attempt(
    db: Session,
    *,
    user_id: uuid.UUID,
    selected_option_id: uuid.UUID,
) -> DailyChallengeAttemptOutcome:
    """Submit an attempt at today's question.

    Concurrency-safe — two simultaneous calls from the same user
    resolve via the partial unique constraint; the loser re-reads
    and returns the winner's attempt verbatim.

    Idempotent — a repeat call with the same selected option after the
    user already attempted today returns the existing attempt. The
    streak service is not called a second time, so the streak counter
    doesn't drift.

    Raises ``NoScheduleError`` when no question is scheduled for today
    and ``InvalidOptionError`` when ``selected_option_id`` belongs to
    a different question.
    """
    today = utc_today()

    schedule_q = get_today_question(db, on_date=today, allow_fallback=True)
    if schedule_q is None:
        raise NoScheduleError(f"no question scheduled for UTC date {today.isoformat()}")
    schedule, question = schedule_q

    # Validate the option belongs to today's question. Done as one
    # query instead of walking ``question.options`` so a malformed
    # frontend payload is rejected before we touch the streak row.
    selected = (
        db.query(DailyChallengeOption)
        .filter(
            DailyChallengeOption.id == selected_option_id,
            DailyChallengeOption.question_id == question.id,
        )
        .one_or_none()
    )
    if selected is None:
        raise InvalidOptionError(selected_option_id=selected_option_id, question_id=question.id)

    correct_option = _correct_option_for(question)
    is_correct = selected.is_correct

    # Try to insert the attempt. The partial unique blocks the
    # two-tab race; on IntegrityError we re-read the existing row.
    attempt = DailyChallengeAttempt(
        user_id=user_id,
        question_id=question.id,
        challenge_date=today,
        is_archive=False,
        selected_option_id=selected.id,
        is_correct=is_correct,
    )
    db.add(attempt)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(DailyChallengeAttempt)
            .filter(
                DailyChallengeAttempt.user_id == user_id,
                DailyChallengeAttempt.challenge_date == today,
                DailyChallengeAttempt.is_archive.is_(False),
            )
            .one()
        )
        # ``streak_after`` was set on the winning write; safe to return.
        return DailyChallengeAttemptOutcome(
            attempt=existing,
            schedule=schedule,
            question=question,
            correct_option_id=correct_option.id,
            streak_after=existing.streak_after or 0,
            is_new_attempt=False,
        )

    new_streak = apply_streak_for_attempt(db, user_id=user_id, challenge_date=today)
    attempt.streak_after = new_streak
    db.flush()
    db.commit()
    db.refresh(attempt)

    return DailyChallengeAttemptOutcome(
        attempt=attempt,
        schedule=schedule,
        question=question,
        correct_option_id=correct_option.id,
        streak_after=new_streak,
        is_new_attempt=True,
    )
