"""Sprint 2 service-layer + endpoint tests for the Daily Challenge.

Three groups:

1. **Streak math** — the YouVersion-style increment / reset / no-op
   rules. Pure unit tests on ``apply_streak_for_attempt`` so the rules
   are pinned independently of the route layer.
2. **Attempt race resolution** — the partial-unique-driven "two tabs"
   race; the second call to ``submit_today_attempt`` must return the
   first attempt's record verbatim without double-incrementing the
   streak.
3. **Endpoints** — happy path + error paths for ``GET /today``,
   ``POST /today/attempt``, ``GET /streak`` using FastAPI's TestClient.

Question + option text is seeded via ``record_human_version`` calls
into ``content_versions`` to mirror how the Sprint 3 editorial
pipeline will land them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.models.daily_challenge import (
    DailyChallengeAttempt,
    DailyChallengeOption,
    DailyChallengeQuestion,
    DailyChallengeSchedule,
    DailyChallengeStreak,
)
from app.models.user import User, UserRole
from app.services.content_versions.write import record_human_version
from app.services.daily_challenge import (
    InvalidOptionError,
    NoScheduleError,
    apply_streak_for_attempt,
    submit_today_attempt,
)
from app.services.daily_challenge.schedule import utc_today

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def author(db: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"dc-author-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Test Author",
        role=UserRole.TEACHER.value,
    )
    db.add(u)
    db.commit()
    return u


def _seed_question_with_options(
    db: Session,
    *,
    author_id: uuid.UUID,
    status: str = "published",
    source_locale: str = "en",
) -> DailyChallengeQuestion:
    """Build a fully-stocked published question + 4 options. Translatable
    text lands in content_versions via record_human_version, matching
    what the Sprint 3 editorial pipeline will do.
    """
    q = DailyChallengeQuestion(
        question_type="multiple_choice",
        status=status,
        published_at=datetime.now(UTC) if status == "published" else None,
        published_by=author_id if status == "published" else None,
        created_by=author_id,
        bible_book="Romans",
        bible_chapter=8,
        bible_verse_from=1,
        bible_verse_to=1,
        category="passage_exegesis",
        source_locale=source_locale,
    )
    db.add(q)
    db.flush()

    record_human_version(
        db,
        entity_type="daily_challenge_question",
        entity_id=str(q.id),
        field="question_text",
        locale=source_locale,
        text="In Romans 8:1, who is free from condemnation?",
        authored_by=author_id,
    )
    record_human_version(
        db,
        entity_type="daily_challenge_question",
        entity_id=str(q.id),
        field="explanation",
        locale=source_locale,
        text="Romans 8:1 — no condemnation for those in Christ Jesus.",
        authored_by=author_id,
    )

    option_texts = [
        ("Those in Christ Jesus", True),
        ("Those who keep the law", False),
        ("Those who are baptized", False),
        ("Those born of God", False),
    ]
    for idx, (text, is_correct) in enumerate(option_texts):
        opt = DailyChallengeOption(
            question_id=q.id,
            is_correct=is_correct,
            order_index=idx,
        )
        db.add(opt)
        db.flush()
        record_human_version(
            db,
            entity_type="daily_challenge_option",
            entity_id=str(opt.id),
            field="option_text",
            locale=source_locale,
            text=text,
            authored_by=author_id,
        )

    db.commit()
    db.refresh(q)
    return q


def _schedule_for_today(db: Session, question: DailyChallengeQuestion, scheduled_by: uuid.UUID) -> None:
    db.add(
        DailyChallengeSchedule(
            challenge_date=utc_today(),
            question_id=question.id,
            scheduled_by=scheduled_by,
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# Verse-range normalization (create_question CHECK-safety)
# ---------------------------------------------------------------------------


class TestNormalizeVerseRange:
    """``_normalize_verse_range`` must coerce any (from, to) pair to satisfy the
    daily_challenge_questions CHECK. The fat-bank run lost ~27% of whole-chapter
    passages because the LLM emitted a dangling verse_end with no verse_start."""

    @pytest.mark.parametrize(
        ("vf", "vt", "expected"),
        [
            (None, None, (None, None)),  # whole-chapter
            (None, 16, (None, None)),  # dangling end (the real bug) -> drop it
            (5, None, (5, None)),  # start only
            (5, 10, (5, 10)),  # valid range
            (10, 5, (10, None)),  # reversed -> keep start
            (0, 5, (None, None)),  # non-positive start
            (5, 0, (5, None)),  # non-positive end
            (-3, 4, (None, None)),  # negative start
        ],
    )
    def test_normalize(self, vf, vt, expected):
        from app.services.daily_challenge.admin import _normalize_verse_range

        assert _normalize_verse_range(vf, vt) == expected

    def test_create_question_with_dangling_verse_to_does_not_violate_check(self, db: Session, author: User):
        """The model mirrors the prod CHECK, so SQLite enforces it: before the
        fix this raised IntegrityError; now it persists CHECK-safe (None/None)."""
        from app.services.daily_challenge.admin import OptionDraft, create_question

        q = create_question(
            db,
            question_type="multiple_choice",
            bible_book="Jonah",
            bible_chapter=1,
            bible_verse_from=None,
            bible_verse_to=16,  # dangling end, no start — the bug case
            question_text="What did Jonah do when called to Nineveh?",
            options=[OptionDraft(text="Fled to Tarshish", is_correct=True), OptionDraft(text="Obeyed", is_correct=False)],
            explanation="Jonah 1 — he fled toward Tarshish.",
            category="narrative_meaning",
            created_by=author.id,
            fallback_locale="en",
        )
        db.commit()
        db.refresh(q)
        assert q.bible_verse_from is None
        assert q.bible_verse_to is None

    def test_create_question_preserves_valid_range(self, db: Session, author: User):
        from app.services.daily_challenge.admin import OptionDraft, create_question

        q = create_question(
            db,
            question_type="multiple_choice",
            bible_book="Psalms",
            bible_chapter=119,
            bible_verse_from=1,
            bible_verse_to=16,
            question_text="What does Psalm 119:1-16 commend?",
            options=[OptionDraft(text="Walking in the law", is_correct=True), OptionDraft(text="Riches", is_correct=False)],
            explanation="Psalm 119 exalts God's word.",
            category="passage_exegesis",
            created_by=author.id,
            fallback_locale="en",
        )
        db.commit()
        db.refresh(q)
        assert (q.bible_verse_from, q.bible_verse_to) == (1, 16)


# ---------------------------------------------------------------------------
# Streak math
# ---------------------------------------------------------------------------


class TestStreakMath:
    """Pin the YouVersion-style streak rules. ANY attempt counts; the
    streak math doesn't care about correctness."""

    def test_first_ever_attempt_creates_row_at_one(self, db: Session, student):
        new = apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 29))
        assert new == 1
        row = db.query(DailyChallengeStreak).filter_by(user_id=student.id).one()
        assert row.current_streak == 1
        assert row.longest_streak == 1
        assert row.last_engaged_date == date(2026, 5, 29)

    def test_same_day_resubmit_is_idempotent(self, db: Session, student):
        d = date(2026, 5, 29)
        apply_streak_for_attempt(db, user_id=student.id, challenge_date=d)
        repeat = apply_streak_for_attempt(db, user_id=student.id, challenge_date=d)
        assert repeat == 1
        row = db.query(DailyChallengeStreak).filter_by(user_id=student.id).one()
        assert row.current_streak == 1

    def test_consecutive_day_increments(self, db: Session, student):
        apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 28))
        new = apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 29))
        assert new == 2
        row = db.query(DailyChallengeStreak).filter_by(user_id=student.id).one()
        assert row.longest_streak == 2

    def test_one_day_gap_resets_to_one(self, db: Session, student):
        apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 28))
        # Skip 2026-05-29 entirely; come back 2026-05-30. That's a gap
        # of one missed day → reset (YouVersion strict; no grace
        # tokens per the locked decisions).
        new = apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 30))
        assert new == 1
        row = db.query(DailyChallengeStreak).filter_by(user_id=student.id).one()
        # Longest is held even after the reset.
        assert row.longest_streak == 1
        assert row.current_streak == 1

    def test_longer_gap_resets_to_one(self, db: Session, student):
        apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 1))
        new = apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 29))
        assert new == 1

    def test_longest_streak_tracks_max_across_resets(self, db: Session, student):
        for delta in range(5):
            apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 1) + timedelta(days=delta))
        # Reset
        apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 20))
        row = db.query(DailyChallengeStreak).filter_by(user_id=student.id).one()
        assert row.current_streak == 1
        assert row.longest_streak == 5

    def test_backward_date_is_noop(self, db: Session, student):
        """Clock skew / test fixture / manual backfill submits a date
        earlier than last_engaged. Defensive: no-op rather than
        decrementing the counter."""
        apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 29))
        result = apply_streak_for_attempt(db, user_id=student.id, challenge_date=date(2026, 5, 28))
        assert result == 1
        row = db.query(DailyChallengeStreak).filter_by(user_id=student.id).one()
        assert row.current_streak == 1
        assert row.last_engaged_date == date(2026, 5, 29)


# ---------------------------------------------------------------------------
# Attempt service — race + invalid option + idempotency
# ---------------------------------------------------------------------------


class TestSubmitTodayAttempt:
    def test_no_schedule_falls_back_to_published_pool(self, db: Session, author: User, student: User):
        # No schedule row for today, but a published question exists: rather
        # than go dark, the live path auto-fills today's slot from the pool.
        q = _seed_question_with_options(db, author_id=author.id)
        opt_id = q.options[0].id
        result = submit_today_attempt(db, user_id=student.id, selected_option_id=opt_id)
        assert result.schedule.challenge_date == utc_today()
        # the gap was self-healed into a real, persisted schedule row
        assert (
            db.query(DailyChallengeSchedule).filter(DailyChallengeSchedule.challenge_date == utc_today()).one_or_none()
            is not None
        )

    def test_no_schedule_and_empty_pool_raises(self, db: Session, author: User, student: User):
        # A draft question is NOT in the publishable pool, so there is nothing
        # to fall back to and the genuine "no schedule" error still surfaces.
        _seed_question_with_options(db, author_id=author.id, status="draft")
        with pytest.raises(NoScheduleError):
            submit_today_attempt(db, user_id=student.id, selected_option_id=uuid.uuid4())

    def test_invalid_option_raises(self, db: Session, author: User, student: User):
        q = _seed_question_with_options(db, author_id=author.id)
        _schedule_for_today(db, q, author.id)
        with pytest.raises(InvalidOptionError):
            submit_today_attempt(
                db,
                user_id=student.id,
                selected_option_id=uuid.uuid4(),  # nonexistent
            )

    def test_correct_answer_records_streak_one(self, db: Session, author: User, student: User):
        q = _seed_question_with_options(db, author_id=author.id)
        _schedule_for_today(db, q, author.id)
        correct = next(o for o in q.options if o.is_correct)
        outcome = submit_today_attempt(db, user_id=student.id, selected_option_id=correct.id)
        assert outcome.attempt.is_correct is True
        assert outcome.streak_after == 1
        assert outcome.is_new_attempt is True

    def test_wrong_answer_still_records_streak_one_youversion_style(self, db: Session, author: User, student: User):
        """Vadym's locked decision: any attempt counts for the streak.
        Wrong answers still move the streak."""
        q = _seed_question_with_options(db, author_id=author.id)
        _schedule_for_today(db, q, author.id)
        wrong = next(o for o in q.options if not o.is_correct)
        outcome = submit_today_attempt(db, user_id=student.id, selected_option_id=wrong.id)
        assert outcome.attempt.is_correct is False
        assert outcome.streak_after == 1

    def test_double_submit_returns_first_attempt_without_double_streak(self, db: Session, author: User, student: User):
        """The "two browser tabs" race. The second call to
        submit_today_attempt must return the first attempt verbatim
        and NOT call the streak service a second time."""
        q = _seed_question_with_options(db, author_id=author.id)
        _schedule_for_today(db, q, author.id)
        correct = next(o for o in q.options if o.is_correct)

        first = submit_today_attempt(db, user_id=student.id, selected_option_id=correct.id)
        # Second submission, same user, same day — simulates the
        # second-tab race. Service should return the existing attempt
        # and not double-count the streak.
        second = submit_today_attempt(db, user_id=student.id, selected_option_id=correct.id)

        assert second.attempt.id == first.attempt.id
        assert second.is_new_attempt is False
        assert second.streak_after == 1

        attempts = db.query(DailyChallengeAttempt).filter_by(user_id=student.id, challenge_date=utc_today()).all()
        assert len(attempts) == 1


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class TestDailyChallengeEndpoints:
    def test_today_returns_404_when_nothing_scheduled(self, db: Session, student_client: TestClient):
        # Genuinely empty: no schedule AND no publishable question to fall back to.
        resp = student_client.get("/api/v1/daily-challenge/today")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["code"] == "daily_challenge.not_scheduled"

    def test_today_falls_back_when_unscheduled_but_pool_exists(
        self, db: Session, author: User, student_client: TestClient
    ):
        # No schedule row, but a published question exists -> /today serves it
        # from the pool instead of 404ing (the schedule self-heals).
        _seed_question_with_options(db, author_id=author.id)
        resp = student_client.get("/api/v1/daily-challenge/today")
        assert resp.status_code == 200

    def test_today_returns_question_without_answer_key(
        self,
        db: Session,
        author: User,
        student_client: TestClient,
    ):
        q = _seed_question_with_options(db, author_id=author.id)
        _schedule_for_today(db, q, author.id)
        resp = student_client.get(
            "/api/v1/daily-challenge/today",
            headers={"Accept-Language": "en"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["question_text"].startswith("In Romans 8:1")
        # Answer key is NOT in the response — only resolved option_text +
        # id + order_index.
        for opt in body["options"]:
            assert "is_correct" not in opt
            assert "option_text" in opt
        assert body["already_attempted"] is False
        assert body["user_attempt"] is None
        # Book label localized for EN locale (canonical English).
        assert body["bible_book"] == "Romans"
        assert body["bible_book_label"] == "Rom."

    def test_today_book_label_localizes_to_russian_under_ru_locale(
        self,
        db: Session,
        author: User,
        student_client: TestClient,
    ):
        q = _seed_question_with_options(db, author_id=author.id)
        _schedule_for_today(db, q, author.id)
        resp = student_client.get(
            "/api/v1/daily-challenge/today",
            headers={"Accept-Language": "ru"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # ``bible_book`` stays the canonical English (for analytics/joins);
        # ``bible_book_label`` is the localized short-form.
        assert body["bible_book"] == "Romans"
        assert body["bible_book_label"] == "Рим."

    def test_post_attempt_reveals_explanation_and_correct_id(
        self,
        db: Session,
        author: User,
        student_client: TestClient,
    ):
        q = _seed_question_with_options(db, author_id=author.id)
        _schedule_for_today(db, q, author.id)
        correct = next(o for o in q.options if o.is_correct)
        resp = student_client.post(
            "/api/v1/daily-challenge/today/attempt",
            json={"selected_option_id": str(correct.id)},
            headers={"Accept-Language": "en"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_correct"] is True
        assert body["correct_option_id"] == str(correct.id)
        assert body["streak_after"] == 1
        assert body["explanation"]

    def test_post_attempt_invalid_option_is_422(
        self,
        db: Session,
        author: User,
        student_client: TestClient,
    ):
        q = _seed_question_with_options(db, author_id=author.id)
        _schedule_for_today(db, q, author.id)
        resp = student_client.post(
            "/api/v1/daily-challenge/today/attempt",
            json={"selected_option_id": str(uuid.uuid4())},
            headers={"Accept-Language": "en"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "daily_challenge.invalid_option"

    def test_streak_endpoint_returns_zero_for_fresh_user(
        self,
        db: Session,
        student_client: TestClient,
    ):
        resp = student_client.get("/api/v1/daily-challenge/streak")
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_streak"] == 0
        assert body["longest_streak"] == 0
        assert body["last_engaged_date"] is None
