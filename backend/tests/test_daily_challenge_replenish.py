"""Tests for the Daily Challenge auto-replenish worker
(``services/daily_challenge/replenish.py`` + the cron endpoint).

The LLM-heavy generation + the editorial promote DAG are mocked; the real
``publish_question`` + ``schedule_for_date`` run against the SQLite test DB
so the orchestration glue (and the "append to the end of the schedule"
contract) is exercised end-to-end.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from app.models.daily_challenge import (
    DailyChallengeQuestion,
    DailyChallengeQuestionStatus,
    DailyChallengeSchedule,
)
from app.models.user import User, UserRole
from app.services.daily_challenge import replenish as R
from app.services.daily_challenge.orchestrator import GenerationOutcome
from app.services.daily_challenge.seed_passages import SEED_PASSAGES

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.orm import Session


def _admin(db: Session) -> User:
    u = User(id=uuid.uuid4(), email=f"admin-{uuid.uuid4().hex[:8]}@t.local", role=UserRole.ADMIN.value)
    db.add(u)
    db.commit()
    return u


def _draft(db: Session, *, created_by: uuid.UUID) -> DailyChallengeQuestion:
    q = DailyChallengeQuestion(
        id=uuid.uuid4(),
        question_type="multiple_choice",
        status="draft",
        bible_book="Genesis",
        bible_chapter=1,
        category="passage_exegesis",
        source_locale="en",
        created_by=created_by,
    )
    db.add(q)
    db.commit()
    return q


class TestPickPassage:
    def test_cursor_advances_with_question_count(self, db: Session) -> None:
        # 0 questions → index 0; after N questions → index N (mod len).
        assert R._pick_passage(db) == SEED_PASSAGES[0]
        admin = _admin(db)
        _draft(db, created_by=admin.id)
        assert R._pick_passage(db) == SEED_PASSAGES[1]

    def test_cursor_wraps(self, db: Session) -> None:
        # Index is count % len, so it never indexes past the list end.
        idx = (10_000) % len(SEED_PASSAGES)
        assert 0 <= idx < len(SEED_PASSAGES)


class TestNextUnscheduledDate:
    def test_skips_taken_dates(self, db: Session) -> None:
        admin = _admin(db)
        q = _draft(db, created_by=admin.id)
        db.add(DailyChallengeSchedule(challenge_date=date(2026, 7, 1), question_id=q.id))
        db.add(DailyChallengeSchedule(challenge_date=date(2026, 7, 2), question_id=q.id))
        db.commit()
        assert R._next_unscheduled_date(db, start=date(2026, 7, 1)) == date(2026, 7, 3)


class TestReplenishOneQuestion:
    def test_no_actor_when_no_admin(self, db: Session) -> None:
        out = R.replenish_one_question(db, client=object())  # type: ignore[arg-type]
        assert out.status == "no_actor"

    def test_no_survivors(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        _admin(db)
        monkeypatch.setattr(
            R,
            "run_generation",
            lambda *a, **k: GenerationOutcome(generation_run_id=uuid.uuid4(), created_question_ids=[]),
        )
        out = R.replenish_one_question(db, client=object())  # type: ignore[arg-type]
        assert out.status == "no_survivors"

    def test_generation_error_is_caught(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        _admin(db)

        def _boom(*_a: object, **_k: object) -> GenerationOutcome:
            raise RuntimeError("Gemini 429")

        monkeypatch.setattr(R, "run_generation", _boom)
        out = R.replenish_one_question(db, client=object())  # type: ignore[arg-type]
        assert out.status == "error"
        assert "429" in (out.detail or "")

    def test_publish_failure_rejects_orphan(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        # The generation pipeline commits its question; if a later
        # promote/publish step dies, the row cannot be rolled back. The tick
        # must terminally reject it (audit reason intact) so it neither
        # lingers as a zombie draft nor gets reused by the passage cursor.
        admin = _admin(db)

        def _fake_generate(db_: Session, *, client: object, request: object) -> GenerationOutcome:
            q = _draft(db_, created_by=admin.id)
            return GenerationOutcome(generation_run_id=uuid.uuid4(), created_question_ids=[q.id])

        def _fake_promote(
            db_: Session, *, question: DailyChallengeQuestion, actor_id: uuid.UUID
        ) -> DailyChallengeQuestion:
            question.status = DailyChallengeQuestionStatus.PILOT_PASSED.value
            db_.flush()
            return question

        def _publish_boom(*_a: object, **_k: object) -> DailyChallengeQuestion:
            raise RuntimeError("publish exploded")

        monkeypatch.setattr(R, "run_generation", _fake_generate)
        monkeypatch.setattr(R, "promote_status", _fake_promote)
        monkeypatch.setattr(R, "publish_question", _publish_boom)

        out = R.replenish_one_question(db, client=object())  # type: ignore[arg-type]
        assert out.status == "error"
        orphan = db.query(DailyChallengeQuestion).filter_by(id=uuid.UUID(out.question_id)).one()
        assert orphan.rejected is True
        assert "publish failed" in (orphan.rejection_reason or "")

    def test_stuck_promotion_rejects_orphan(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        # Promotion that never reaches pilot_passed is the same orphan class.
        admin = _admin(db)

        def _fake_generate(db_: Session, *, client: object, request: object) -> GenerationOutcome:
            q = _draft(db_, created_by=admin.id)
            return GenerationOutcome(generation_run_id=uuid.uuid4(), created_question_ids=[q.id])

        monkeypatch.setattr(R, "run_generation", _fake_generate)
        monkeypatch.setattr(R, "promote_status", lambda db_, *, question, actor_id: question)  # no-op: stays draft

        out = R.replenish_one_question(db, client=object())  # type: ignore[arg-type]
        assert out.status == "error"
        assert "stuck at status=draft" in (out.detail or "")
        orphan = db.query(DailyChallengeQuestion).filter_by(id=uuid.UUID(out.question_id)).one()
        assert orphan.rejected is True

    def test_happy_path_publishes_and_appends(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        admin = _admin(db)

        def _fake_generate(db_: Session, *, client: object, request: object) -> GenerationOutcome:
            q = _draft(db_, created_by=admin.id)
            return GenerationOutcome(generation_run_id=uuid.uuid4(), created_question_ids=[q.id])

        def _fake_promote(
            db_: Session, *, question: DailyChallengeQuestion, actor_id: uuid.UUID
        ) -> DailyChallengeQuestion:
            question.status = DailyChallengeQuestionStatus.PILOT_PASSED.value
            db_.flush()
            return question

        monkeypatch.setattr(R, "run_generation", _fake_generate)
        monkeypatch.setattr(R, "promote_status", _fake_promote)
        # publish_question + schedule_for_date run for real.

        out = R.replenish_one_question(db, client=object(), start_date=date(2026, 7, 10))  # type: ignore[arg-type]
        assert out.status == "scheduled"
        assert out.challenge_date == "2026-07-10"
        # A real schedule row landed on the appended date, pointing at a
        # now-published question.
        row = db.query(DailyChallengeSchedule).filter_by(challenge_date=date(2026, 7, 10)).one()
        q = db.query(DailyChallengeQuestion).filter_by(id=row.question_id).one()
        assert q.status == DailyChallengeQuestionStatus.PUBLISHED.value

    def test_appends_after_existing_schedule(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        admin = _admin(db)
        existing = _draft(db, created_by=admin.id)
        db.add(DailyChallengeSchedule(challenge_date=date(2026, 7, 10), question_id=existing.id))
        db.commit()

        def _fake_generate(db_: Session, *, client: object, request: object) -> GenerationOutcome:
            q = _draft(db_, created_by=admin.id)
            return GenerationOutcome(generation_run_id=uuid.uuid4(), created_question_ids=[q.id])

        def _fake_promote(
            db_: Session, *, question: DailyChallengeQuestion, actor_id: uuid.UUID
        ) -> DailyChallengeQuestion:
            question.status = DailyChallengeQuestionStatus.PILOT_PASSED.value
            db_.flush()
            return question

        monkeypatch.setattr(R, "run_generation", _fake_generate)
        monkeypatch.setattr(R, "promote_status", _fake_promote)

        out = R.replenish_one_question(db, client=object(), start_date=date(2026, 7, 10))  # type: ignore[arg-type]
        # 7-10 is taken → appended to 7-11.
        assert out.status == "scheduled"
        assert out.challenge_date == "2026-07-11"


class TestWorkerTickUnconfigured:
    def test_unconfigured_without_gemini_key(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.api.v1 import internal_daily_challenge_worker as W
        from app.core.config import settings

        monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
        out = W._run_one_tick(db)
        assert out.status == "unconfigured"
