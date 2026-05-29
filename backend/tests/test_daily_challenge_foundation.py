"""Foundation tests for the Daily Challenge MVP schema.

Phase 5c — pins the load-bearing invariants of the schema before the
service layer arrives. Three groups of tests:

1. **Model defaults** — fresh rows carry the expected zero state so the
   streak-init path in the service layer can rely on it.
2. **Partial unique on attempts** — the partial index that resolves
   the "two browser tabs" race for live attempts (but allows unlimited
   archive replays).
3. **Streak constraints** — the CHECK constraints that guarantee
   non-negative counters survive the ORM round-trip.

The Postgres-only invariants (the schedule-publishability trigger,
the column-level REVOKE on ``options.is_correct``) are exercised by
the schema-smoke-postgres CI job, not here — SQLite has no triggers
or column-level grants.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session  # noqa: TC002 — used at runtime by fixture annotations

from app.models.daily_challenge import (
    DailyChallengeAttempt,
    DailyChallengeOption,
    DailyChallengeQuestion,
    DailyChallengeQuestionStatus,
    DailyChallengeQuestionType,
    DailyChallengeSchedule,
    DailyChallengeStreak,
)
from app.models.user import User, UserRole


@pytest.fixture
def author(db: Session) -> User:
    """A teacher user that owns the questions we seed below."""
    u = User(
        id=uuid.uuid4(),
        email=f"dc-author-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Daily Challenge Author",
        role=UserRole.TEACHER.value,
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def student(db: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"dc-student-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Daily Challenge Student",
        role=UserRole.STUDENT.value,
    )
    db.add(u)
    db.commit()
    return u


def _make_question(
    db: Session,
    *,
    author_id: uuid.UUID,
    status: str = "draft",
    rejected: bool = False,
) -> DailyChallengeQuestion:
    """Build a minimal valid question. Translatable text doesn't land
    here — the Daily Challenge service layer writes to cv. For schema
    tests we just need the structural row."""
    q = DailyChallengeQuestion(
        question_type=DailyChallengeQuestionType.MULTIPLE_CHOICE.value,
        status=status,
        rejected=rejected,
        created_by=author_id,
        bible_book="Romans",
        bible_chapter=8,
        bible_verse_from=1,
        bible_verse_to=1,
        category="passage_exegesis",
        source_locale="en",
    )
    db.add(q)
    db.flush()
    for i in range(4):
        db.add(
            DailyChallengeOption(
                question_id=q.id,
                is_correct=(i == 0),
                order_index=i,
            )
        )
    db.commit()
    db.refresh(q)
    return q


# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------


class TestQuestionDefaults:
    def test_fresh_question_lands_in_draft_status(self, db: Session, author: User):
        q = _make_question(db, author_id=author.id)
        assert q.status == DailyChallengeQuestionStatus.DRAFT.value
        assert q.rejected is False
        assert q.published_at is None

    def test_options_round_trip_with_order_and_correctness(self, db: Session, author: User):
        q = _make_question(db, author_id=author.id)
        opts = sorted(q.options, key=lambda o: o.order_index)
        assert [o.order_index for o in opts] == [0, 1, 2, 3]
        # Exactly one correct option — invariant the service layer
        # asserts at commit time. Schema doesn't enforce it (would
        # fight a multi-row INSERT that hasn't reached a coherent
        # state yet) but the test asserts the helper produced it.
        assert sum(1 for o in opts if o.is_correct) == 1
        assert opts[0].is_correct is True


class TestStreakDefaults:
    def test_fresh_streak_starts_at_zero(self, db: Session, student: User):
        s = DailyChallengeStreak(user_id=student.id)
        db.add(s)
        db.commit()
        db.refresh(s)
        assert s.current_streak == 0
        assert s.longest_streak == 0
        assert s.last_engaged_date is None


# ---------------------------------------------------------------------------
# Partial unique on attempts
# ---------------------------------------------------------------------------


class TestAttemptUniqueness:
    def test_two_live_attempts_same_user_same_date_violates(self, db: Session, author: User, student: User):
        """The race-resolving partial unique. Same (user, date)
        cannot have two live attempts. The second INSERT raises
        ``IntegrityError`` — the route catches that and returns the
        first attempt verbatim.
        """
        q = _make_question(db, author_id=author.id, status="published", rejected=False)
        today = date(2026, 5, 29)
        db.add(
            DailyChallengeAttempt(
                user_id=student.id,
                question_id=q.id,
                challenge_date=today,
                is_archive=False,
                is_correct=True,
                streak_after=1,
            )
        )
        db.commit()

        # Second live attempt on the same date for the same user — should fail.
        db.add(
            DailyChallengeAttempt(
                user_id=student.id,
                question_id=q.id,
                challenge_date=today,
                is_archive=False,
                is_correct=False,
                streak_after=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_archive_replays_allowed_unbounded_for_same_user_same_date(self, db: Session, author: User, student: User):
        """Archive attempts are excluded from the partial unique — a
        student can replay yesterday's question as many times as they
        want without violating any constraint. Streak math is decoupled
        via the CHECK on ``streak_after`` (NULL for archives)."""
        q = _make_question(db, author_id=author.id, status="published", rejected=False)
        past_date = date(2026, 5, 20)
        for _ in range(3):
            db.add(
                DailyChallengeAttempt(
                    user_id=student.id,
                    question_id=q.id,
                    challenge_date=past_date,
                    is_archive=True,
                    is_correct=False,
                    streak_after=None,
                )
            )
        db.commit()
        rows = db.query(DailyChallengeAttempt).filter_by(user_id=student.id, challenge_date=past_date).all()
        assert len(rows) == 3

    def test_one_live_attempt_plus_archive_replays_coexist(self, db: Session, author: User, student: User):
        """The user submitted a live attempt today, then later replayed
        an OLD question whose challenge_date happens to equal today
        (a question previously scheduled for today is also available
        in the archive — edge case but valid). The live attempt is
        gated by the partial unique; the archive replay slips past."""
        q1 = _make_question(db, author_id=author.id, status="published", rejected=False)
        q2 = _make_question(db, author_id=author.id, status="published", rejected=False)
        today = date(2026, 5, 29)
        db.add(
            DailyChallengeAttempt(
                user_id=student.id,
                question_id=q1.id,
                challenge_date=today,
                is_archive=False,
                is_correct=True,
                streak_after=5,
            )
        )
        db.add(
            DailyChallengeAttempt(
                user_id=student.id,
                question_id=q2.id,
                challenge_date=today,
                is_archive=True,
                is_correct=True,
                streak_after=None,
            )
        )
        db.commit()
        assert db.query(DailyChallengeAttempt).filter_by(user_id=student.id, challenge_date=today).count() == 2


class TestStreakCheckConstraints:
    def test_negative_current_streak_violates_check(self, db: Session, student: User):
        s = DailyChallengeStreak(user_id=student.id, current_streak=-1)
        db.add(s)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


# ---------------------------------------------------------------------------
# Schedule wiring
# ---------------------------------------------------------------------------


class TestSchedule:
    def test_one_schedule_per_date(self, db: Session, author: User):
        """``challenge_date`` is the PK on the schedule table — exactly
        one question per UTC day. The second INSERT for the same date
        raises an IntegrityError on the PK."""
        q1 = _make_question(db, author_id=author.id, status="published", rejected=False)
        q2 = _make_question(db, author_id=author.id, status="published", rejected=False)
        today = date(2026, 5, 29)
        db.add(
            DailyChallengeSchedule(
                challenge_date=today,
                question_id=q1.id,
                scheduled_by=author.id,
            )
        )
        db.commit()
        db.add(
            DailyChallengeSchedule(
                challenge_date=today,
                question_id=q2.id,
                scheduled_by=author.id,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
