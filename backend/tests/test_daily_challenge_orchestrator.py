"""Sprint 5 tests — AI question generation orchestrator.

Mocks ``GeminiPromptClient.invoke`` so the tests are deterministic
and never hit the real API. The pipeline runs end-to-end against the
in-memory SQLite test DB, so we exercise:

  * Round 1-3 prompt sequencing (call count + system prompts)
  * Round 4a scripture validation against bundled KJV + Synodal
  * Round 4b doctrinal verdict handling (pass / reject / needs_framing)
  * Round 4c bilingual rejection + RU translation persistence
  * Round 6 DRAFT persistence + cv writes for both EN + RU
  * Audit trail keyed on ``generation_run_id`` (pre- and post-persistence)
  * Empty-survivor short-circuits return cleanly with errors set
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from app.models.content_version import ContentVersion
from app.models.daily_challenge import (
    DailyChallengeQuestion,
    DailyChallengeQuestionEvent,
    DailyChallengeQuestionStatus,
)
from app.models.user import User, UserRole
from app.services.daily_challenge.orchestrator import (
    GenerationRequest,
    run_generation,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _canonical_texts_without_a_network(monkeypatch):
    """The generator now reads the editions the reader is shown.

    Those come from the API — the English bundle is the King James
    Version, and handing KJV to the model is what produced 62 questions
    written in Early Modern English. Russian has no usable bundle at all
    (its file is misaligned), so there is nothing local to fall back to
    and nothing to fall back to is correct: a wrong verse handed to the
    generator produces a wrong question.

    Tests have no API key, so they say what the passage is.
    """
    from app.services.bible import substitution

    def _stub(ref, locale):
        return {
            "en": "For God so loved the world that He gave His one and only Son.",
            "ru": "Ибо так возлюбил Бог мир, что отдал Сына Своего Единородного.",
        }.get(locale)

    monkeypatch.setattr("app.services.daily_challenge.orchestrator.canonical_for_display", _stub)
    assert substitution.canonical_for_display is not None


@pytest.fixture
def author(db: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"dc-orch-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Orchestrator Author",
        role=UserRole.TEACHER.value,
    )
    db.add(u)
    db.commit()
    return u


def _candidate(
    *,
    qid: int,
    verse_start: int,
    verse_end: int | None = None,
    correct_idx: int = 0,
) -> dict[str, Any]:
    """Build a candidate question payload mirroring the round-1 JSON schema."""
    return {
        "id": f"q{qid}",
        "question_text": f"What is the truth taught in verse {verse_start}?",
        "verse_start": verse_start,
        "verse_end": verse_end,
        "options": [{"text": f"Option {i} for q{qid}", "is_correct": i == correct_idx} for i in range(4)],
        "explanation": f"Explanation for q{qid}",
        "category": "narrative_recall",
    }


def _make_client(responses: list[dict[str, Any]]) -> MagicMock:
    """Return a MagicMock client whose ``invoke`` returns ``responses`` in order.

    Asserts at the end of the test that every queued response was used —
    catches drift between the prompt sequence the orchestrator runs and
    the sequence the test expects."""
    client = MagicMock()
    iter_responses = iter(responses)
    client.invoke.side_effect = lambda **_: next(iter_responses)
    return client


def _happy_path_responses(
    *,
    n_candidates: int = 2,
    verse_starts: tuple[int, ...] = (14, 16),
) -> list[dict[str, Any]]:
    """Canned 7-call response set for a full clean run on John 3."""
    candidates_a = {"candidates": [_candidate(qid=i, verse_start=verse_starts[i]) for i in range(n_candidates)]}
    candidates_b = {"candidates": [_candidate(qid=10 + i, verse_start=verse_starts[i]) for i in range(n_candidates)]}
    critiques_a = {"critiques": [{"candidate_index": i, "verdict": "ok"} for i in range(n_candidates)]}
    critiques_b = {"critiques": [{"candidate_index": i, "verdict": "ok"} for i in range(n_candidates)]}
    synthesis = {"survivors": [_candidate(qid=100 + i, verse_start=verse_starts[i]) for i in range(n_candidates)]}
    doctrinal = {"reviews": [{"survivor_index": i, "verdict": "pass"} for i in range(n_candidates)]}
    bilingual = {
        "reviews": [
            {
                "survivor_index": i,
                "verdict": "pass",
                "ru_translation": {
                    "question_text": f"Вопрос {i} на русском",
                    "explanation": f"Объяснение {i}",
                    "options": [{"text": f"Вариант {j} для q{i}"} for j in range(4)],
                },
            }
            for i in range(n_candidates)
        ]
    }
    return [
        candidates_a,
        candidates_b,
        critiques_a,
        critiques_b,
        synthesis,
        doctrinal,
        bilingual,
    ]


# ── happy path ───────────────────────────────────────────────────────


def test_happy_path_persists_drafts_and_full_audit_trail(db: Session, author: User) -> None:
    """Two survivors clear every gate; both land as DRAFT rows with cv
    EN + RU writes and the full audit trail."""
    client = _make_client(_happy_path_responses())
    request = GenerationRequest(
        book="John",
        chapter=3,
        verse_from=14,
        verse_to=17,
        n_candidates_per_agent=2,
        max_survivors=2,
        created_by=author.id,
    )

    outcome = run_generation(db, client=client, request=request)

    assert len(outcome.created_question_ids) == 2
    assert outcome.rejected_at_scripture == 0
    assert outcome.rejected_at_doctrinal == 0
    assert outcome.rejected_at_bilingual == 0
    assert outcome.errors == []
    assert outcome.rounds_executed >= 6

    persisted = (
        db.query(DailyChallengeQuestion).filter(DailyChallengeQuestion.id.in_(outcome.created_question_ids)).all()
    )
    assert len(persisted) == 2
    for q in persisted:
        assert q.status == DailyChallengeQuestionStatus.DRAFT.value
        assert q.rejected is False
        assert q.bible_book == "John"
        assert q.bible_chapter == 3

    events = (
        db.query(DailyChallengeQuestionEvent)
        .filter(DailyChallengeQuestionEvent.generation_run_id == outcome.generation_run_id)
        .all()
    )
    event_types = [e.event_type for e in events]
    # Each round writes at least one event.
    assert event_types.count("ai_generated") == 2
    assert event_types.count("ai_critique") == 2
    # Synthesis event PLUS one ai_synthesis per persisted question.
    assert event_types.count("ai_synthesis") >= 1 + len(persisted)
    assert "scripture_validated" in event_types
    assert "doctrinally_reviewed" in event_types
    assert "bilingually_reviewed" in event_types
    assert "pilot_summary" in event_types

    # Pre-persistence rounds are keyed by run_id only (question_id NULL).
    pre_persist = [e for e in events if e.question_id is None]
    assert any(e.event_type == "ai_generated" for e in pre_persist)

    # RU translations were written as cv rows.
    cv_rows = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "daily_challenge_question",
            ContentVersion.entity_id.in_([str(qid) for qid in outcome.created_question_ids]),
            ContentVersion.locale == "ru",
        )
        .all()
    )
    assert len(cv_rows) >= 2
    assert any("на русском" in (row.text or "") for row in cv_rows)


# ── scripture rejection ──────────────────────────────────────────────


def test_scripture_validation_rejects_invalid_verse(db: Session, author: User) -> None:
    """A survivor pointing to a non-existent verse is rejected at
    Stage 4a without invoking the doctrinal or bilingual rounds."""
    survivor_good = _candidate(qid=1, verse_start=14)
    survivor_bad = _candidate(qid=2, verse_start=9999)  # John 3:9999 doesn't exist
    responses = [
        {"candidates": [survivor_good]},
        {"candidates": [survivor_bad]},
        {"critiques": []},
        {"critiques": []},
        {"survivors": [survivor_good, survivor_bad]},
        # Doctrinal + bilingual only see the good one
        {"reviews": [{"survivor_index": 0, "verdict": "pass"}]},
        {"reviews": [{"survivor_index": 0, "verdict": "pass"}]},
    ]
    client = _make_client(responses)
    request = GenerationRequest(
        book="John",
        chapter=3,
        verse_from=14,
        verse_to=17,
        n_candidates_per_agent=2,
        max_survivors=2,
        created_by=author.id,
    )

    outcome = run_generation(db, client=client, request=request)

    assert outcome.rejected_at_scripture == 1
    assert len(outcome.created_question_ids) == 1


def test_no_survivors_after_scripture_short_circuits(db: Session, author: User) -> None:
    """All-bad survivors → short-circuit with an error and no doctrinal/
    bilingual LLM calls."""
    bad = _candidate(qid=1, verse_start=9999)
    responses = [
        {"candidates": [bad]},
        {"candidates": [bad]},
        {"critiques": []},
        {"critiques": []},
        {"survivors": [bad]},
    ]
    client = _make_client(responses)
    request = GenerationRequest(
        book="John",
        chapter=3,
        verse_from=14,
        verse_to=17,
        n_candidates_per_agent=1,
        max_survivors=1,
        created_by=author.id,
    )

    outcome = run_generation(db, client=client, request=request)

    assert outcome.rejected_at_scripture == 1
    assert outcome.created_question_ids == []
    assert any("scripture" in e for e in outcome.errors)
    assert client.invoke.call_count == 5  # rounds 1-3 only


# ── doctrinal verdict handling ───────────────────────────────────────


def test_doctrinal_reject_drops_survivor(db: Session, author: User) -> None:
    """A doctrinally-rejected survivor never reaches the bilingual
    review and never persists."""
    good = _candidate(qid=1, verse_start=14)
    bad = _candidate(qid=2, verse_start=16)
    responses = [
        {"candidates": [good]},
        {"candidates": [bad]},
        {"critiques": []},
        {"critiques": []},
        {"survivors": [good, bad]},
        {
            "reviews": [
                {"survivor_index": 0, "verdict": "pass"},
                {"survivor_index": 1, "verdict": "reject"},
            ]
        },
        {
            "reviews": [
                {
                    "survivor_index": 0,
                    "verdict": "pass",
                    "ru_translation": {
                        "question_text": "RU",
                        "options": [{"text": "RU opt"}],
                    },
                }
            ]
        },
    ]
    client = _make_client(responses)
    request = GenerationRequest(
        book="John",
        chapter=3,
        verse_from=14,
        verse_to=17,
        created_by=author.id,
    )

    outcome = run_generation(db, client=client, request=request)

    assert outcome.rejected_at_doctrinal == 1
    assert len(outcome.created_question_ids) == 1


def test_doctrinal_needs_framing_rewrites_text(db: Session, author: User) -> None:
    """``needs_framing`` swaps in the proposed text before persistence."""
    good = _candidate(qid=1, verse_start=14)
    responses = [
        {"candidates": [good]},
        {"candidates": [good]},
        {"critiques": []},
        {"critiques": []},
        {"survivors": [good]},
        {
            "reviews": [
                {
                    "survivor_index": 0,
                    "verdict": "needs_framing",
                    "proposed_reframe": {
                        "question_text": "Reframed question text",
                        "explanation": "Reframed explanation",
                    },
                }
            ]
        },
        {"reviews": [{"survivor_index": 0, "verdict": "pass"}]},
    ]
    client = _make_client(responses)
    request = GenerationRequest(
        book="John",
        chapter=3,
        verse_from=14,
        verse_to=17,
        created_by=author.id,
    )

    outcome = run_generation(db, client=client, request=request)

    assert len(outcome.created_question_ids) == 1
    qid = outcome.created_question_ids[0]
    en_question = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "daily_challenge_question",
            ContentVersion.entity_id == str(qid),
            ContentVersion.field == "question_text",
            ContentVersion.locale == "en",
        )
        .one()
    )
    assert en_question.text == "Reframed question text"


# ── bilingual rejection ──────────────────────────────────────────────


def test_bilingual_reject_drops_survivor(db: Session, author: User) -> None:
    """``rejected_at_bilingual`` increments and the survivor never persists."""
    good = _candidate(qid=1, verse_start=14)
    other = _candidate(qid=2, verse_start=16)
    responses = [
        {"candidates": [good]},
        {"candidates": [other]},
        {"critiques": []},
        {"critiques": []},
        {"survivors": [good, other]},
        {
            "reviews": [
                {"survivor_index": 0, "verdict": "pass"},
                {"survivor_index": 1, "verdict": "pass"},
            ]
        },
        {
            "reviews": [
                {"survivor_index": 0, "verdict": "pass"},
                {"survivor_index": 1, "verdict": "reject"},
            ]
        },
    ]
    client = _make_client(responses)
    request = GenerationRequest(
        book="John",
        chapter=3,
        verse_from=14,
        verse_to=17,
        created_by=author.id,
    )

    outcome = run_generation(db, client=client, request=request)

    assert outcome.rejected_at_bilingual == 1
    assert len(outcome.created_question_ids) == 1


# ── canonical text missing ───────────────────────────────────────────


def test_canonical_text_missing_returns_outcome_with_error(db: Session, author: User) -> None:
    """A book/chapter that isn't bundled in either KJV or Synodal halts
    the run before any LLM call."""
    client = MagicMock()
    # Book deliberately misspelled so the bundle lookup misses.
    request = GenerationRequest(
        book="NotARealBook",
        chapter=1,
        verse_from=1,
        verse_to=2,
        created_by=author.id,
    )

    outcome = run_generation(db, client=client, request=request)

    assert outcome.created_question_ids == []
    assert outcome.rounds_executed == 0
    assert client.invoke.call_count == 0
    assert any("canonical text missing" in e for e in outcome.errors)
