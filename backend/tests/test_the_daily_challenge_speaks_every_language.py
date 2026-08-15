# ruff: noqa: RUF001
# The renderings below are Cyrillic prose, one-letter prepositions included.
"""The Daily Challenge is the one thing every user sees every day.

It was also the one piece of content nothing translated. Course content
is picked up by ``reconcile_entity``, which finds the entity's course
and fans out from its language. A Daily Challenge question has no
course, so it fell through — and nobody noticed, because the generator
happens to produce English and Russian and those were the only two
languages the platform had.

The day German and Ukrainian shipped, 490 published questions had zero
rows in either. With the fallback chain gone (a reader who chose German
is never shown Russian), that resolved to an empty string, and an empty
string renders: the card appeared with no question and four blank
buttons, inviting the reader to answer nothing.

These tests pin the three things that fix it: the questions get
translated, a question that is not translated is not served as blanks,
and the pool heals itself for languages added after the content.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.daily_challenge import (
    DailyChallengeOption,
    DailyChallengeQuestion,
    DailyChallengeSchedule,
)
from app.models.user import User, UserRole
from app.schemas.locale import LOCALE_CODES
from app.services.content_versions.write import record_human_version
from app.services.daily_challenge.text import QuestionTextBundle, fetch_question_text_bundle
from app.services.daily_challenge.translate import (
    question_translation_completeness,
    questions_missing_a_language,
    translate_pending_questions,
    translate_question,
)
from app.services.translation.protocol import TranslationResult
from app.services.translation.service import reset_translation_provider_cache

from ._fake_translation import fake_translate

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.services.translation.protocol import TranslationRequest


# Real sentences rather than a transliteration, because the pipeline now
# reads what comes back: a "translation" that is still recognisably
# English lands in ``needs_review`` and is never served, which is exactly
# what the validator is for. A fake that trips it would make these tests
# fail for a reason that has nothing to do with the Daily Challenge.
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
    "Peter": {"ru": "Пётр", "de": "Petrus", "uk": "Петро"},
    "James": {"ru": "Иаков", "de": "Jakobus", "uk": "Яків"},
    "John": {"ru": "Иоанн", "de": "Johannes", "uk": "Іван"},
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
        email=f"dc-lang-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Question Author",
        role=UserRole.TEACHER.value,
    )
    db.add(user)
    db.commit()
    return user


def _seed_question(
    db: Session,
    *,
    author_id: uuid.UUID,
    status: str = "published",
    option_texts: tuple[str, ...] = ("Paul", "Peter", "James", "John"),
) -> DailyChallengeQuestion:
    """A question as the generator leaves it: English source only."""
    question = DailyChallengeQuestion(
        question_type="multiple_choice",
        status=status,
        published_at=datetime.now(UTC) if status == "published" else None,
        published_by=author_id if status == "published" else None,
        created_by=author_id,
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
    for index, text in enumerate(option_texts):
        option = DailyChallengeOption(question_id=question.id, is_correct=index == 0, order_index=index)
        db.add(option)
        db.flush()
        record_human_version(
            db,
            entity_type="daily_challenge_option",
            entity_id=str(option.id),
            field="option_text",
            locale="en",
            text=text,
            authored_by=author_id,
        )
    db.commit()
    db.refresh(question)
    return question


def _schedule(db: Session, question: DailyChallengeQuestion, on_date: date) -> None:
    db.add(DailyChallengeSchedule(challenge_date=on_date, question_id=question.id))
    db.commit()


class TestTheQuestionGetsTranslated:
    def test_every_served_language_receives_the_question(self, db: Session, author: User):
        question = _seed_question(db, author_id=author.id)
        provider = _Provider()

        translate_question(db, question, provider=provider)

        for locale in LOCALE_CODES:
            bundle = fetch_question_text_bundle(db, question=question, display_locale=locale)
            assert bundle.question_text.strip(), f"{locale} has no question text"

    def test_the_answers_travel_with_the_question(self, db: Session, author: User):
        # A translated question with untranslated options is the worst of
        # the three states: it looks answerable and is not.
        question = _seed_question(db, author_id=author.id)
        translate_question(db, question, provider=_Provider())

        for locale in LOCALE_CODES:
            bundle = fetch_question_text_bundle(db, question=question, display_locale=locale)
            assert len(bundle.options) == 4
            assert all(text.strip() for text in bundle.options.values()), locale

    def test_it_does_not_translate_into_the_language_it_is_written_in(self, db: Session, author: User):
        question = _seed_question(db, author_id=author.id)
        provider = _Provider()

        translate_question(db, question, provider=provider)

        assert provider.calls, "nothing was translated at all"
        assert all(call.target_locale != "en" for call in provider.calls)

    def test_running_it_twice_costs_nothing(self, db: Session, author: User):
        question = _seed_question(db, author_id=author.id)
        first = _Provider()
        translate_question(db, question, provider=first)

        second = _Provider()
        translate_question(db, question, provider=second)

        assert first.calls
        assert second.calls == [], "unchanged text was sent to the provider again"


class TestCompleteness:
    def test_a_fresh_question_is_incomplete(self, db: Session, author: User):
        question = _seed_question(db, author_id=author.id)
        completeness = question_translation_completeness(db, question)
        assert not completeness.is_complete
        # Every language other than the one it was written in.
        assert set(completeness.by_locale()) == {code for code in LOCALE_CODES if code != "en"}

    def test_translating_it_makes_it_complete(self, db: Session, author: User):
        question = _seed_question(db, author_id=author.id)
        translate_question(db, question, provider=_Provider())
        assert question_translation_completeness(db, question).is_complete


class TestTheSweep:
    def test_it_finds_the_questions_written_before_a_language_existed(self, db: Session, author: User):
        untranslated = _seed_question(db, author_id=author.id)
        found = questions_missing_a_language(db, limit=10)
        assert untranslated.id in {q.id for q in found}

    def test_it_leaves_finished_questions_alone(self, db: Session, author: User):
        question = _seed_question(db, author_id=author.id)
        translate_question(db, question, provider=_Provider())
        found = questions_missing_a_language(db, limit=10)
        assert question.id not in {q.id for q in found}

    def test_a_question_waiting_on_a_person_is_not_swept_again(self, db: Session, author: User):
        # A row parked at needs_review is not retried — same model, same
        # temperature, same verdict. Counting it as missing put the
        # sweep in a loop: the same questions every night, every field
        # skipped, the budget spent on questions a person has to read
        # anyway.
        from app.models.content_version import ContentVersion, ContentVersionStatus

        question = _seed_question(db, author_id=author.id)
        translate_question(db, question, provider=_Provider())
        row = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_type == "daily_challenge_question",
                ContentVersion.entity_id == str(question.id),
                ContentVersion.field == "question_text",
                ContentVersion.locale == "de",
            )
            .one()
        )
        row.status = ContentVersionStatus.NEEDS_REVIEW
        db.commit()

        found = questions_missing_a_language(db, limit=10)

        assert question.id not in {q.id for q in found}

    def test_a_row_an_operator_re_opened_is_picked_up_again(self, db: Session, author: User):
        # ``POST /admin/translations/retry-reviewed`` parks a row at
        # ``failed`` — the one status the orchestrator retries. If the
        # sweep read that as settled, the rows somebody just asked to be
        # redone would be exactly the rows it never went back for.
        from app.models.content_version import ContentVersion, ContentVersionStatus

        question = _seed_question(db, author_id=author.id)
        translate_question(db, question, provider=_Provider())
        row = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_type == "daily_challenge_question",
                ContentVersion.entity_id == str(question.id),
                ContentVersion.field == "question_text",
                ContentVersion.locale == "uk",
            )
            .one()
        )
        row.status = ContentVersionStatus.FAILED
        row.attempts = 0
        db.commit()

        found = questions_missing_a_language(db, limit=10)

        assert question.id in {q.id for q in found}

    def test_it_repairs_what_it_finds(self, db: Session, author: User):
        _seed_question(db, author_id=author.id)
        _seed_question(db, author_id=author.id)

        sweep = translate_pending_questions(db, limit=1, provider=_Provider())

        # One per tick when asked for one — the budget is the point.
        assert sweep.questions == 1
        assert sweep.rows.translated > 0
        assert len(questions_missing_a_language(db, limit=10)) == 1


class TestAnEmptyQuestionIsNotAnAnswer:
    def test_blank_options_make_a_bundle_unservable(self):
        bundle = QuestionTextBundle(
            question_text="Wer schrieb den Römerbrief?",
            explanation=None,
            options={uuid.uuid4(): "Paulus", uuid.uuid4(): ""},
        )
        assert not bundle.is_servable

    def test_a_missing_explanation_does_not(self):
        bundle = QuestionTextBundle(
            question_text="Wer schrieb den Römerbrief?",
            explanation=None,
            options={uuid.uuid4(): "Paulus", uuid.uuid4(): "Petrus"},
        )
        assert bundle.is_servable

    def test_today_says_not_translated_rather_than_serving_blanks(
        self, db: Session, author: User, student: User, client: TestClient
    ):
        question = _seed_question(db, author_id=author.id)
        _schedule(db, question, datetime.now(UTC).date())

        resp = client.get("/api/v1/daily-challenge/today", headers={"Accept-Language": "de"})

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "daily_challenge.not_translated"

    def test_and_serves_it_once_the_language_arrives(
        self, db: Session, author: User, student: User, client: TestClient
    ):
        question = _seed_question(db, author_id=author.id)
        _schedule(db, question, datetime.now(UTC).date())
        translate_question(db, question, provider=_Provider())

        resp = client.get("/api/v1/daily-challenge/today", headers={"Accept-Language": "de"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["question_text"].strip()
        assert all(o["option_text"].strip() for o in body["options"])

    def test_the_archive_answers_the_same_way(self, db: Session, author: User, student: User, client: TestClient):
        question = _seed_question(db, author_id=author.id)
        yesterday = datetime.now(UTC).date() - timedelta(days=1)
        _schedule(db, question, yesterday)

        resp = client.get(
            f"/api/v1/daily-challenge/archive/{yesterday.isoformat()}",
            headers={"Accept-Language": "uk"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "daily_challenge.not_translated"
