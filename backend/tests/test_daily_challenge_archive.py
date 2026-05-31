"""Archive endpoint + service tests.

Covers: list pagination/cursor, attempt status annotation per date
(live vs archive replay), 422 on today/future, 404 on unscheduled
past, reveal payload only after attempting, attempt persists with
``is_archive=True`` + null streak_after, multiple replays allowed.

Re-uses seeders from ``test_daily_challenge_service.py`` so the
fixtures stay deduped.
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
)
from app.models.user import User, UserRole
from app.services.content_versions.write import record_human_version
from app.services.daily_challenge.schedule import utc_today

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


@pytest.fixture
def author(db: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"dc-arc-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Archive Author",
        role=UserRole.TEACHER.value,
    )
    db.add(u)
    db.commit()
    return u


def _seed_q(db: Session, *, author_id: uuid.UUID, chapter: int = 8, verse: int = 1) -> DailyChallengeQuestion:
    q = DailyChallengeQuestion(
        question_type="multiple_choice",
        status="published",
        published_at=datetime.now(UTC),
        published_by=author_id,
        created_by=author_id,
        bible_book="Romans",
        bible_chapter=chapter,
        bible_verse_from=verse,
        bible_verse_to=verse,
        source_locale="en",
    )
    db.add(q)
    db.flush()
    record_human_version(
        db,
        entity_type="daily_challenge_question",
        entity_id=str(q.id),
        field="question_text",
        locale="en",
        text=f"Romans {chapter}:{verse}?",
        authored_by=author_id,
    )
    record_human_version(
        db,
        entity_type="daily_challenge_question",
        entity_id=str(q.id),
        field="explanation",
        locale="en",
        text=f"Explanation for Romans {chapter}:{verse}",
        authored_by=author_id,
    )
    opts = [("A", True), ("B", False), ("C", False), ("D", False)]
    for idx, (text, is_correct) in enumerate(opts):
        o = DailyChallengeOption(question_id=q.id, is_correct=is_correct, order_index=idx)
        db.add(o)
        db.flush()
        record_human_version(
            db,
            entity_type="daily_challenge_option",
            entity_id=str(o.id),
            field="option_text",
            locale="en",
            text=text,
            authored_by=author_id,
        )
    db.commit()
    db.refresh(q)
    return q


def _schedule(db: Session, q: DailyChallengeQuestion, on_date: date, scheduled_by: uuid.UUID) -> None:
    db.add(
        DailyChallengeSchedule(
            challenge_date=on_date,
            question_id=q.id,
            scheduled_by=scheduled_by,
        )
    )
    db.commit()


# ── list endpoint ───────────────────────────────────────────────────


class TestArchiveList:
    def test_lists_past_dates_descending(self, db: Session, author: User, student: User, student_client: TestClient):
        today = utc_today()
        for days_ago in (5, 3, 1):
            q = _seed_q(db, author_id=author.id, chapter=8, verse=days_ago)
            _schedule(db, q, today - timedelta(days=days_ago), author.id)
        resp = student_client.get("/api/v1/daily-challenge/archive")
        assert resp.status_code == 200
        body = resp.json()
        dates = [e["challenge_date"] for e in body["entries"]]
        assert dates == sorted(dates, reverse=True)
        assert all(e["attempted_is_correct"] is None for e in body["entries"])

    def test_annotates_live_attempt_correctness(
        self, db: Session, author: User, student: User, student_client: TestClient
    ):
        today = utc_today()
        q = _seed_q(db, author_id=author.id)
        d = today - timedelta(days=2)
        _schedule(db, q, d, author.id)
        # Live attempt with the wrong option (the second one).
        wrong = next(o for o in q.options if not o.is_correct)
        db.add(
            DailyChallengeAttempt(
                user_id=student.id,
                question_id=q.id,
                challenge_date=d,
                is_archive=False,
                selected_option_id=wrong.id,
                is_correct=False,
                streak_after=1,
            )
        )
        db.commit()

        resp = student_client.get("/api/v1/daily-challenge/archive")
        assert resp.status_code == 200
        entry = next(e for e in resp.json()["entries"] if e["challenge_date"] == d.isoformat())
        assert entry["attempted_is_correct"] is False
        assert entry["archive_only_attempt"] is False

    def test_prefers_live_over_archive_attempt(
        self, db: Session, author: User, student: User, student_client: TestClient
    ):
        today = utc_today()
        q = _seed_q(db, author_id=author.id)
        d = today - timedelta(days=4)
        _schedule(db, q, d, author.id)
        correct = next(o for o in q.options if o.is_correct)
        wrong = next(o for o in q.options if not o.is_correct)
        # Live wrong, then archive replay correct → list should report
        # the LIVE result (wrong) and ``archive_only_attempt=False``.
        db.add(
            DailyChallengeAttempt(
                user_id=student.id,
                question_id=q.id,
                challenge_date=d,
                is_archive=False,
                selected_option_id=wrong.id,
                is_correct=False,
                streak_after=1,
            )
        )
        db.add(
            DailyChallengeAttempt(
                user_id=student.id,
                question_id=q.id,
                challenge_date=d,
                is_archive=True,
                selected_option_id=correct.id,
                is_correct=True,
            )
        )
        db.commit()

        resp = student_client.get("/api/v1/daily-challenge/archive")
        entry = next(e for e in resp.json()["entries"] if e["challenge_date"] == d.isoformat())
        assert entry["attempted_is_correct"] is False
        assert entry["archive_only_attempt"] is False

    def test_archive_only_attempt_is_flagged(
        self, db: Session, author: User, student: User, student_client: TestClient
    ):
        today = utc_today()
        q = _seed_q(db, author_id=author.id)
        d = today - timedelta(days=6)
        _schedule(db, q, d, author.id)
        correct = next(o for o in q.options if o.is_correct)
        db.add(
            DailyChallengeAttempt(
                user_id=student.id,
                question_id=q.id,
                challenge_date=d,
                is_archive=True,
                selected_option_id=correct.id,
                is_correct=True,
            )
        )
        db.commit()
        resp = student_client.get("/api/v1/daily-challenge/archive")
        entry = next(e for e in resp.json()["entries"] if e["challenge_date"] == d.isoformat())
        assert entry["attempted_is_correct"] is True
        assert entry["archive_only_attempt"] is True

    def test_returns_localized_book_label(self, db: Session, author: User, student: User, student_client: TestClient):
        today = utc_today()
        q = _seed_q(db, author_id=author.id)
        _schedule(db, q, today - timedelta(days=1), author.id)
        resp = student_client.get("/api/v1/daily-challenge/archive", headers={"Accept-Language": "ru"})
        body = resp.json()
        assert body["entries"][0]["bible_book_label"] == "Рим."


# ── single-date get ──────────────────────────────────────────────────


class TestArchiveGet:
    def test_returns_422_for_today(self, db: Session, author: User, student_client: TestClient):
        q = _seed_q(db, author_id=author.id)
        _schedule(db, q, utc_today(), author.id)
        resp = student_client.get(f"/api/v1/daily-challenge/archive/{utc_today().isoformat()}")
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "daily_challenge.archive_date_not_allowed"

    def test_returns_422_for_future(self, db: Session, student_client: TestClient):
        future = (utc_today() + timedelta(days=30)).isoformat()
        resp = student_client.get(f"/api/v1/daily-challenge/archive/{future}")
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "daily_challenge.archive_date_not_allowed"

    def test_returns_404_for_unscheduled_past_date(self, db: Session, student_client: TestClient):
        past = (utc_today() - timedelta(days=20)).isoformat()
        resp = student_client.get(f"/api/v1/daily-challenge/archive/{past}")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "daily_challenge.not_scheduled"

    def test_hides_answer_key_when_not_attempted(self, db: Session, author: User, student_client: TestClient):
        q = _seed_q(db, author_id=author.id)
        d = utc_today() - timedelta(days=3)
        _schedule(db, q, d, author.id)
        resp = student_client.get(f"/api/v1/daily-challenge/archive/{d.isoformat()}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["reveal"] is None
        for opt in body["options"]:
            assert "is_correct" not in opt

    def test_reveals_after_any_prior_attempt(
        self, db: Session, author: User, student: User, student_client: TestClient
    ):
        q = _seed_q(db, author_id=author.id)
        d = utc_today() - timedelta(days=3)
        _schedule(db, q, d, author.id)
        wrong = next(o for o in q.options if not o.is_correct)
        db.add(
            DailyChallengeAttempt(
                user_id=student.id,
                question_id=q.id,
                challenge_date=d,
                is_archive=False,
                selected_option_id=wrong.id,
                is_correct=False,
                streak_after=1,
            )
        )
        db.commit()
        resp = student_client.get(f"/api/v1/daily-challenge/archive/{d.isoformat()}")
        body = resp.json()
        assert body["reveal"]["last_attempt_was_correct"] is False
        correct = next(o for o in q.options if o.is_correct)
        assert body["reveal"]["correct_option_id"] == str(correct.id)


# ── attempt POST ─────────────────────────────────────────────────────


class TestArchiveAttempt:
    def test_writes_archive_true_and_null_streak(
        self, db: Session, author: User, student: User, student_client: TestClient
    ):
        q = _seed_q(db, author_id=author.id)
        d = utc_today() - timedelta(days=5)
        _schedule(db, q, d, author.id)
        correct = next(o for o in q.options if o.is_correct)
        resp = student_client.post(
            f"/api/v1/daily-challenge/archive/{d.isoformat()}/attempt",
            json={"selected_option_id": str(correct.id)},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_correct"] is True
        # Row written with archive flag + null streak.
        row = (
            db.query(DailyChallengeAttempt)
            .filter(
                DailyChallengeAttempt.user_id == student.id,
                DailyChallengeAttempt.challenge_date == d,
            )
            .one()
        )
        assert row.is_archive is True
        assert row.streak_after is None

    def test_multiple_replays_allowed(self, db: Session, author: User, student: User, student_client: TestClient):
        q = _seed_q(db, author_id=author.id)
        d = utc_today() - timedelta(days=2)
        _schedule(db, q, d, author.id)
        wrong = next(o for o in q.options if not o.is_correct)
        for _ in range(3):
            resp = student_client.post(
                f"/api/v1/daily-challenge/archive/{d.isoformat()}/attempt",
                json={"selected_option_id": str(wrong.id)},
            )
            assert resp.status_code == 201
        rows = (
            db.query(DailyChallengeAttempt)
            .filter(
                DailyChallengeAttempt.user_id == student.id,
                DailyChallengeAttempt.challenge_date == d,
            )
            .all()
        )
        assert len(rows) == 3
        assert all(r.is_archive for r in rows)

    def test_rejects_invalid_option(self, db: Session, author: User, student_client: TestClient):
        q = _seed_q(db, author_id=author.id)
        d = utc_today() - timedelta(days=1)
        _schedule(db, q, d, author.id)
        resp = student_client.post(
            f"/api/v1/daily-challenge/archive/{d.isoformat()}/attempt",
            json={"selected_option_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "daily_challenge.invalid_option"

    def test_rejects_today_date(self, db: Session, author: User, student_client: TestClient):
        q = _seed_q(db, author_id=author.id)
        _schedule(db, q, utc_today(), author.id)
        correct = next(o for o in q.options if o.is_correct)
        resp = student_client.post(
            f"/api/v1/daily-challenge/archive/{utc_today().isoformat()}/attempt",
            json={"selected_option_id": str(correct.id)},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "daily_challenge.archive_date_not_allowed"
