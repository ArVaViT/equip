"""Sprint 3 tests — editorial pipeline.

Pins the forward-only status DAG, the orthogonal ``rejected``
boolean, and the schedule-publishability gate. Three groups:

1. **create_question** — happy path + validation errors (no correct
   option, wrong option count, true_false != 2 options).
2. **promote_status / reject / publish** — the editorial DAG; pin
   each forward edge + the rejection lock + the publishability gate.
3. **schedule_for_date** — idempotency on the same pair; rejection
   of non-published or already-scheduled dates.

Audit-trail rows are not deeply asserted here (a smoke check on
"events were written" is enough); the AI orchestrator tests will
exercise the events table more thoroughly when they land.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

import pytest

from app.models.daily_challenge import (
    DailyChallengeQuestion,
    DailyChallengeQuestionEvent,
    DailyChallengeQuestionStatus,
    DailyChallengeSchedule,
)
from app.models.user import User, UserRole
from app.services.daily_challenge import (
    NotPublishableError,
    OptionDraft,
    QuestionRejectedError,
    StatusTransitionError,
    create_question,
    promote_status,
    publish_question,
    reject_question,
    schedule_for_date,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture
def author(db: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"dc-ed-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Editorial Author",
        role=UserRole.TEACHER.value,
    )
    db.add(u)
    db.commit()
    return u


def _good_options() -> list[OptionDraft]:
    return [
        OptionDraft(text="Those in Christ Jesus", is_correct=True),
        OptionDraft(text="Those who keep the law", is_correct=False),
        OptionDraft(text="Those who are baptized", is_correct=False),
        OptionDraft(text="Those born of God", is_correct=False),
    ]


def _make_draft(db: Session, author: User) -> DailyChallengeQuestion:
    return create_question(
        db,
        question_type="multiple_choice",
        bible_book="Romans",
        bible_chapter=8,
        bible_verse_from=1,
        bible_verse_to=1,
        question_text="In Romans 8:1, who is free from condemnation?",
        options=_good_options(),
        explanation="No condemnation for those in Christ Jesus.",
        category="passage_exegesis",
        created_by=author.id,
        fallback_locale="en",
    )


def _promote_to(
    db: Session, q: DailyChallengeQuestion, target: DailyChallengeQuestionStatus, author: User
) -> DailyChallengeQuestion:
    while q.status != target.value:
        q = promote_status(db, question=q, actor_id=author.id)
    return q


class TestCreateQuestion:
    def test_happy_path(self, db: Session, author: User):
        q = _make_draft(db, author)
        assert q.status == "draft"
        assert q.rejected is False
        assert q.source_locale == "en"
        # An event row exists for the "create" transition.
        events = db.query(DailyChallengeQuestionEvent).filter_by(question_id=q.id, event_type="status_change").all()
        assert len(events) == 1

    def test_zero_correct_options_raises(self, db: Session, author: User):
        bad = [OptionDraft(text="A", is_correct=False), OptionDraft(text="B", is_correct=False)]
        with pytest.raises(ValueError):
            create_question(
                db,
                question_type="multiple_choice",
                bible_book="Romans",
                bible_chapter=8,
                bible_verse_from=1,
                bible_verse_to=1,
                question_text="Q",
                options=bad,
                explanation=None,
                category=None,
                created_by=author.id,
            )

    def test_two_correct_options_raises(self, db: Session, author: User):
        bad = [OptionDraft(text="A", is_correct=True), OptionDraft(text="B", is_correct=True)]
        with pytest.raises(ValueError):
            create_question(
                db,
                question_type="multiple_choice",
                bible_book="Romans",
                bible_chapter=8,
                bible_verse_from=1,
                bible_verse_to=1,
                question_text="Q",
                options=bad,
                explanation=None,
                category=None,
                created_by=author.id,
            )

    def test_true_false_needs_exactly_two_options(self, db: Session, author: User):
        with pytest.raises(ValueError):
            create_question(
                db,
                question_type="true_false",
                bible_book="Romans",
                bible_chapter=8,
                bible_verse_from=1,
                bible_verse_to=1,
                question_text="Q",
                options=_good_options(),  # four options; rejected
                explanation=None,
                category=None,
                created_by=author.id,
            )


class TestPromoteStatus:
    def test_walks_dag_forward_to_pilot_passed(self, db: Session, author: User):
        """promote() walks draft → … → pilot_passed (four edges).
        The pilot_passed → published transition is handled separately
        by publish_question (so published_at gets stamped)."""
        q = _make_draft(db, author)
        stages = [
            DailyChallengeQuestionStatus.SCRIPTURE_VALIDATED,
            DailyChallengeQuestionStatus.DOCTRINALLY_REVIEWED,
            DailyChallengeQuestionStatus.BILINGUALLY_REVIEWED,
            DailyChallengeQuestionStatus.PILOT_PASSED,
        ]
        for s in stages:
            q = promote_status(db, question=q, actor_id=author.id)
            assert q.status == s.value

    def test_no_forward_from_pilot_passed_via_promote(self, db: Session, author: User):
        """promote() refuses the pilot_passed → published edge; the
        caller must use publish_question() to also stamp published_at."""
        q = _make_draft(db, author)
        q = _promote_to(db, q, DailyChallengeQuestionStatus.PILOT_PASSED, author)
        with pytest.raises(StatusTransitionError):
            promote_status(db, question=q, actor_id=author.id)

    def test_no_forward_from_published(self, db: Session, author: User):
        q = _make_draft(db, author)
        q = _promote_to(db, q, DailyChallengeQuestionStatus.PILOT_PASSED, author)
        q = publish_question(db, question=q, actor_id=author.id)
        with pytest.raises(StatusTransitionError):
            promote_status(db, question=q, actor_id=author.id)

    def test_no_forward_from_archived(self, db: Session, author: User):
        q = _make_draft(db, author)
        q.status = DailyChallengeQuestionStatus.ARCHIVED.value
        db.commit()
        with pytest.raises(StatusTransitionError):
            promote_status(db, question=q, actor_id=author.id)

    def test_rejected_blocks_promote(self, db: Session, author: User):
        q = _make_draft(db, author)
        q = reject_question(db, question=q, actor_id=author.id, reason="answer ambiguous")
        with pytest.raises(QuestionRejectedError):
            promote_status(db, question=q, actor_id=author.id)


class TestReject:
    def test_rejection_is_orthogonal_to_status(self, db: Session, author: User):
        q = _make_draft(db, author)
        q = promote_status(db, question=q, actor_id=author.id)  # → scripture_validated
        previous_status = q.status
        q = reject_question(db, question=q, actor_id=author.id, reason="doctrinal lean")
        # Status unchanged — the row stays at whatever stage killed it.
        assert q.status == previous_status
        assert q.rejected is True
        assert q.rejection_reason == "doctrinal lean"

    def test_double_reject_is_idempotent(self, db: Session, author: User):
        q = _make_draft(db, author)
        q = reject_question(db, question=q, actor_id=author.id, reason="first")
        q = reject_question(db, question=q, actor_id=author.id, reason="second")
        assert q.rejection_reason == "first"  # not overwritten


class TestPublish:
    def test_must_be_pilot_passed(self, db: Session, author: User):
        q = _make_draft(db, author)
        # At draft → not eligible.
        with pytest.raises(StatusTransitionError):
            publish_question(db, question=q, actor_id=author.id)

    def test_publishing_sets_published_at(self, db: Session, author: User):
        q = _make_draft(db, author)
        q = _promote_to(db, q, DailyChallengeQuestionStatus.PILOT_PASSED, author)
        assert q.published_at is None
        q = publish_question(db, question=q, actor_id=author.id)
        assert q.status == "published"
        assert q.published_at is not None
        assert q.published_by == author.id


class TestSchedule:
    def test_only_published_can_be_scheduled(self, db: Session, author: User):
        q = _make_draft(db, author)
        with pytest.raises(NotPublishableError):
            schedule_for_date(db, question=q, on_date=date(2026, 5, 30), actor_id=author.id)

    def test_idempotent_same_pair(self, db: Session, author: User):
        q = _make_draft(db, author)
        q = _promote_to(db, q, DailyChallengeQuestionStatus.PILOT_PASSED, author)
        q = publish_question(db, question=q, actor_id=author.id)
        first = schedule_for_date(db, question=q, on_date=date(2026, 5, 30), actor_id=author.id)
        # Same (date, question) — no-op return.
        second = schedule_for_date(db, question=q, on_date=date(2026, 5, 30), actor_id=author.id)
        assert first.challenge_date == second.challenge_date
        assert first.question_id == second.question_id

    def test_date_collision_with_different_question_raises(self, db: Session, author: User):
        q1 = _make_draft(db, author)
        q1 = _promote_to(db, q1, DailyChallengeQuestionStatus.PILOT_PASSED, author)
        q1 = publish_question(db, question=q1, actor_id=author.id)
        schedule_for_date(db, question=q1, on_date=date(2026, 5, 30), actor_id=author.id)

        q2 = _make_draft(db, author)
        q2 = _promote_to(db, q2, DailyChallengeQuestionStatus.PILOT_PASSED, author)
        q2 = publish_question(db, question=q2, actor_id=author.id)
        with pytest.raises(NotPublishableError):
            schedule_for_date(db, question=q2, on_date=date(2026, 5, 30), actor_id=author.id)

    def test_autofill_placeholder_is_replaced_by_editor(self, db: Session, author: User):
        # The live dry-day fallback writes a placeholder schedule with
        # scheduled_by=NULL. An editor scheduling a curated question for that
        # date must REPLACE it (not be blocked), or the autofill would hijack
        # the slot with no recovery.
        q1 = _make_draft(db, author)
        q1 = _promote_to(db, q1, DailyChallengeQuestionStatus.PILOT_PASSED, author)
        q1 = publish_question(db, question=q1, actor_id=author.id)
        db.add(DailyChallengeSchedule(challenge_date=date(2026, 5, 30), question_id=q1.id, scheduled_by=None))
        db.commit()

        q2 = _make_draft(db, author)
        q2 = _promote_to(db, q2, DailyChallengeQuestionStatus.PILOT_PASSED, author)
        q2 = publish_question(db, question=q2, actor_id=author.id)
        result = schedule_for_date(db, question=q2, on_date=date(2026, 5, 30), actor_id=author.id)
        assert result.question_id == q2.id
        assert result.scheduled_by == author.id


class TestEndpoints:
    def test_create_through_publish_walk(self, db: Session, client):
        """End-to-end via the client: create draft → walk DAG →
        publish → schedule. Uses the default ``client`` fixture which
        authenticates as a teacher (per conftest)."""
        # Create
        resp = client.post(
            "/api/v1/admin/daily-challenge/questions",
            json={
                "question_type": "multiple_choice",
                "bible_book": "Romans",
                "bible_chapter": 8,
                "bible_verse_from": 1,
                "bible_verse_to": 1,
                "question_text": "Who is free from condemnation?",
                "explanation": "Romans 8:1.",
                "category": "passage_exegesis",
                "options": [
                    {"text": "Those in Christ Jesus", "is_correct": True},
                    {"text": "Those who keep the law", "is_correct": False},
                    {"text": "Those who are baptized", "is_correct": False},
                    {"text": "Those born of God", "is_correct": False},
                ],
            },
        )
        assert resp.status_code == 201, resp.text
        qid = resp.json()["id"]

        # Promote 4x to reach pilot_passed; then publish separately.
        for _ in range(4):
            resp = client.post(f"/api/v1/admin/daily-challenge/questions/{qid}/promote")
            assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "pilot_passed"

        resp = client.post(f"/api/v1/admin/daily-challenge/questions/{qid}/publish")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "published"
        assert resp.json()["published_at"] is not None

        # Schedule.
        resp = client.post(
            "/api/v1/admin/daily-challenge/schedule",
            json={"challenge_date": "2026-06-15", "question_id": qid},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["challenge_date"] == "2026-06-15"

    def test_promote_rejected_returns_409(self, db: Session, client):
        # Create + reject + try to promote → 409 validation.failed.
        resp = client.post(
            "/api/v1/admin/daily-challenge/questions",
            json={
                "question_type": "multiple_choice",
                "bible_book": "Romans",
                "bible_chapter": 8,
                "question_text": "Q",
                "explanation": "E",
                "options": [
                    {"text": "A", "is_correct": True},
                    {"text": "B", "is_correct": False},
                ],
            },
        )
        qid = resp.json()["id"]
        client.post(
            f"/api/v1/admin/daily-challenge/questions/{qid}/reject",
            json={"reason": "ambiguous"},
        )
        resp = client.post(f"/api/v1/admin/daily-challenge/questions/{qid}/promote")
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "validation.failed"

    def test_student_cannot_access_admin_routes(self, db: Session, student_client):
        resp = student_client.get(f"/api/v1/admin/daily-challenge/questions/{uuid.uuid4()}")
        assert resp.status_code == 403
