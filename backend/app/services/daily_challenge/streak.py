"""Streak accounting for the Daily Challenge.

YouVersion-style semantics (Vadym, 2026-05-29): ANY submission counts
as a day of engagement. The streak math doesn't care whether the user
got it right — only whether they showed up.

Algorithm
---------

On every live attempt submit:

* Acquire a row lock on the user's streak row (``FOR UPDATE``). This
  serialises concurrent submits from two browser tabs against each
  other and against the daily cron.
* If no row exists: insert one at ``current_streak=1``.
* If the row's ``last_engaged_date`` already equals the attempt date:
  no-op — same-day re-submits are idempotent.
* If the row's ``last_engaged_date`` is the day before: increment
  ``current_streak`` by 1.
* Otherwise (gap of ≥ 2 days, OR ``last_engaged_date`` is NULL, OR
  somehow ``last_engaged_date > attempt_date`` from clock skew):
  reset to 1.
* Track ``longest_streak`` as the max ever observed.

No grace tokens, no XP — both intentionally deferred per the locked
decisions. See ``memory:project-equip-daily-challenge-decisions.md``.

Idempotency contract
--------------------

``apply_streak_for_attempt(db, user_id, challenge_date)`` is safe to
call multiple times with the same arguments. The second call sees
``last_engaged_date == challenge_date`` and returns the current
streak verbatim. The route layer doesn't need a separate "did this
attempt already write?" check.

Race resolution
---------------

The attempt row carries a partial unique on
``(user_id, challenge_date) WHERE is_archive = FALSE``. When two tabs
submit at the same second the second INSERT fails with
``IntegrityError``. The attempt service catches it, re-reads the
existing attempt, and returns the recorded ``streak_after`` value
WITHOUT calling this service a second time. That keeps the streak
math monotonic.
"""

from __future__ import annotations

import uuid  # noqa: TC003 — annotations evaluated by SQLAlchemy at runtime
from datetime import date, timedelta
from typing import TYPE_CHECKING

from app.models.daily_challenge import DailyChallengeStreak

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def apply_streak_for_attempt(
    db: Session,
    *,
    user_id: uuid.UUID,
    challenge_date: date,
) -> int:
    """Increment / reset / no-op the user's streak based on the attempt
    date. Returns the new ``current_streak`` value.

    Must be called inside the same transaction as the attempt INSERT
    so a rollback of the attempt also rolls back the streak update.
    """
    streak = (
        db.query(DailyChallengeStreak).filter(DailyChallengeStreak.user_id == user_id).with_for_update().one_or_none()
    )

    if streak is None:
        # First-ever attempt. Insert under the same transaction so the
        # row lock acquired by FOR UPDATE on the (nonexistent) row is
        # replaced by the lock implied by INSERT … the partial-unique
        # on attempts is the second safety net for the create race.
        streak = DailyChallengeStreak(
            user_id=user_id,
            current_streak=1,
            longest_streak=1,
            last_engaged_date=challenge_date,
        )
        db.add(streak)
        db.flush()
        return 1

    last = streak.last_engaged_date

    if last is None:
        # Row exists (created by some other path?) but no prior
        # engagement. Treat as first ever for the streak.
        streak.current_streak = 1
    elif last == challenge_date:
        # Idempotent — same-day re-submit. No mutation.
        return streak.current_streak
    elif challenge_date == last + timedelta(days=1):
        streak.current_streak += 1
    elif challenge_date < last:
        # Defensive: an attempt submitted with a challenge_date EARLIER
        # than the recorded last engagement is logically impossible in
        # a UTC-only world. If it ever happens (clock skew, manual
        # backfill, test fixture) treat as a no-op rather than
        # corrupting the counter downward.
        return streak.current_streak
    else:
        # Gap of ≥ 2 days. Reset to 1 — today is the new start.
        streak.current_streak = 1

    if streak.current_streak > streak.longest_streak:
        streak.longest_streak = streak.current_streak
    streak.last_engaged_date = challenge_date
    db.flush()
    return streak.current_streak


def get_user_streak(
    db: Session,
    *,
    user_id: uuid.UUID,
) -> DailyChallengeStreak | None:
    """Return the user's streak row, or ``None`` if they've never
    engaged. The endpoint layer turns ``None`` into a ``current=0``
    response so the client doesn't have to handle the missing case."""
    return db.query(DailyChallengeStreak).filter(DailyChallengeStreak.user_id == user_id).one_or_none()
