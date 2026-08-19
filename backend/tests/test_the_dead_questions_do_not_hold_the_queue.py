# ruff: noqa: RUF001
# The renderings below are Cyrillic prose, one-letter prepositions included.
"""Five questions nothing can fix took every sweep the pool ever got.

``questions_missing_a_language`` counted a locale as satisfied when it
was ``ok`` or ``needs_review``, and outstanding otherwise. A locale
sitting at ``failed_permanent`` fell in the second group — but the
executor refuses to retry that row, so the question was outstanding
forever.

That is worse here than in the course sweep, because this list is
ordered oldest-first and cut to ``limit``. Five dead questions at the
head of the pool filled every list, the sweep translated nothing, and
the question behind them that a single provider call would have fixed
was never once selected. Three consecutive ticks in production returned
``questions=5, translated=0`` with zero provider calls.

Ordinary ``failed`` has to stay outstanding — that one IS retried, and
clearing ``attempts`` from the admin surface is how an operator asks for
another go.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.daily_challenge import DailyChallengeOption, DailyChallengeQuestion
from app.models.user import User, UserRole
from app.services.content_versions.write import record_human_version
from app.services.daily_challenge.translate import (
    questions_missing_a_language,
    translate_pending_questions,
    translate_question,
)
from app.services.translation.protocol import TranslationResult
from app.services.translation.service import reset_translation_provider_cache

from ._fake_translation import fake_translate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.translation.protocol import TranslationRequest

_RENDERINGS: dict[str, dict[str, str]] = {
    "Who wrote the letter to the Romans?": {
        "ru": "Кто написал послание к римлянам?",
        "de": "Wer schrieb den Brief an die Römer?",
        "uk": "Хто є автором послання до римлян?",
    },
    "The letter names its author in the opening verse.": {
        "ru": "Послание называет своего автора в первом стихе.",
        "de": "Der Brief nennt seinen Verfasser im ersten Vers.",
        "uk": "Послання називає свого автора у першому вірші.",
    },
    "Paul": {"ru": "Павел", "de": "Paulus", "uk": "Павло"},
}


class _Provider:
    name = "recording"

    def __init__(self) -> None:
        self.calls: list[TranslationRequest] = []

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls.append(request)
        rendering = _RENDERINGS.get(request.text, {}).get(request.target_locale)
        return TranslationResult(
            text=rendering or fake_translate(request.text, target_locale=request.target_locale),
            model="test",
        )


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


@pytest.fixture
def author(db: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"pool-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Question Author",
        role=UserRole.TEACHER.value,
    )
    db.add(user)
    db.commit()
    return user


def _seed_question(db: Session, *, author_id: uuid.UUID, created_at: datetime) -> DailyChallengeQuestion:
    """One English-source question, as the generator leaves it."""
    question = DailyChallengeQuestion(
        question_type="multiple_choice",
        status="published",
        published_at=created_at,
        published_by=author_id,
        created_by=author_id,
        created_at=created_at,
        rejected=False,
        bible_book="Romans",
        bible_chapter=8,
        bible_verse_from=1,
        bible_verse_to=4,
        source_locale="en",
    )
    db.add(question)
    db.flush()
    record_human_version(
        db,
        entity_type="daily_challenge_question",
        entity_id=str(question.id),
        field="question_text",
        locale="en",
        text="Who wrote the letter to the Romans?",
        authored_by=author_id,
    )
    record_human_version(
        db,
        entity_type="daily_challenge_question",
        entity_id=str(question.id),
        field="explanation",
        locale="en",
        text="The letter names its author in the opening verse.",
        authored_by=author_id,
    )
    option = DailyChallengeOption(question_id=question.id, is_correct=True, order_index=0)
    db.add(option)
    db.flush()
    record_human_version(
        db,
        entity_type="daily_challenge_option",
        entity_id=str(option.id),
        field="option_text",
        locale="en",
        text="Paul",
        authored_by=author_id,
    )
    db.commit()
    db.refresh(question)
    return question


def _kill(db: Session, question: DailyChallengeQuestion) -> None:
    """Spend the retries on one locale, the way five attempts leave it."""
    row = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "daily_challenge_question",
            ContentVersion.entity_id == str(question.id),
            ContentVersion.field == "question_text",
            ContentVersion.locale == "de",
            ContentVersion.superseded_by.is_(None),
        )
        .one()
    )
    row.status = ContentVersionStatus.FAILED_PERMANENT
    row.attempts = 5
    db.commit()


class TestAPoolWithFiveDeadQuestionsAtTheHead:
    def test_the_fixable_question_behind_them_is_reached(self, db: Session, author: User) -> None:
        # The pool as production had it: five questions the pipeline has
        # given up on, written before the one that a single call fixes,
        # and a sweep that only ever looks at the first five.
        base = datetime.now(UTC) - timedelta(days=30)
        for index in range(5):
            dead = _seed_question(db, author_id=author.id, created_at=base + timedelta(days=index))
            translate_question(db, dead, provider=_Provider())
            _kill(db, dead)
        fixable = _seed_question(db, author_id=author.id, created_at=base + timedelta(days=10))

        pending = questions_missing_a_language(db, limit=5)

        assert fixable.id in {question.id for question in pending}

    def test_two_ticks_in_a_row_are_not_the_same_five(self, db: Session, author: User) -> None:
        # The loop that made it visible: three consecutive ticks each
        # reported five questions and zero rows, because the list never
        # changed and nothing in it could move.
        base = datetime.now(UTC) - timedelta(days=30)
        for index in range(5):
            dead = _seed_question(db, author_id=author.id, created_at=base + timedelta(days=index))
            translate_question(db, dead, provider=_Provider())
            _kill(db, dead)
        _seed_question(db, author_id=author.id, created_at=base + timedelta(days=10))

        first = translate_pending_questions(db, limit=5, provider=_Provider())
        second = translate_pending_questions(db, limit=5, provider=_Provider())

        assert first.rows.translated > 0, "the first tick should have repaired the fixable question"
        assert second.questions == 0, "the second tick should find nothing left it can move"

    def test_a_dead_locale_alone_does_not_bring_a_question_back(self, db: Session, author: User) -> None:
        question = _seed_question(db, author_id=author.id, created_at=datetime.now(UTC))
        translate_question(db, question, provider=_Provider())
        assert question.id not in {q.id for q in questions_missing_a_language(db, limit=10)}

        _kill(db, question)

        assert question.id not in {q.id for q in questions_missing_a_language(db, limit=10)}

    def test_a_retryable_failure_still_brings_it_back(self, db: Session, author: User) -> None:
        # ``failed`` is not ``failed_permanent``: the executor asks
        # again, so the sweep must keep offering it.
        question = _seed_question(db, author_id=author.id, created_at=datetime.now(UTC))
        translate_question(db, question, provider=_Provider())
        row = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_type == "daily_challenge_question",
                ContentVersion.entity_id == str(question.id),
                ContentVersion.field == "question_text",
                ContentVersion.locale == "uk",
                ContentVersion.superseded_by.is_(None),
            )
            .one()
        )
        row.status = ContentVersionStatus.FAILED
        row.attempts = 0
        db.commit()

        assert question.id in {q.id for q in questions_missing_a_language(db, limit=10)}
