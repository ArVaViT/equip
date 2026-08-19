"""Editing the question has to reach its translations.

The course path compares a translation's `source_hash` against the text
it is supposed to be of, and treats a mismatch as work. The Daily
Challenge pool did not: it asked only "is any language missing", so an
edited question kept serving the previous translation in three languages
indefinitely, with nothing scheduled to notice.

It stopped being hypothetical on 2026-08-19, when 38 English sources
were cleaned up — they had carried a Russian half in the same string —
and every translation of them stayed as it was.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.daily_challenge import DailyChallengeOption, DailyChallengeQuestion
from app.models.user import User
from app.services.content_versions import record_human_version, record_mt_version
from app.services.daily_challenge.translate import questions_missing_a_language
from app.services.translation.hash import compute_source_hash
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-00000000ab01")
ORIGINAL = "What happened on the day of Pentecost?"
EDITED = "What happened in Jerusalem on the day of Pentecost?"


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


@pytest.fixture
def settled_question(db: Session) -> DailyChallengeQuestion:
    """A question complete in every language and needing nothing."""
    if db.get(User, ADMIN_ID) is None:
        db.add(User(id=ADMIN_ID, email="pool@example.com", full_name="A", role="admin"))
        db.commit()
    question = DailyChallengeQuestion(
        id=uuid.uuid4(),
        question_type="multiple_choice",
        status="published",
        bible_book="Acts",
        bible_chapter=2,
        category="passage_exegesis",
        source_locale="en",
        created_by=ADMIN_ID,
    )
    db.add(question)
    db.flush()
    option = DailyChallengeOption(id=uuid.uuid4(), question_id=question.id, order_index=0, is_correct=True)
    db.add(option)
    db.commit()

    for entity_type, entity_id, field, text in (
        ("daily_challenge_question", str(question.id), "question_text", ORIGINAL),
        ("daily_challenge_option", str(option.id), "option_text", "The Holy Spirit was poured out"),
    ):
        record_human_version(db, entity_type=entity_type, entity_id=entity_id, field=field, locale="en", text=text)
        source_hash = compute_source_hash(text, locale="en")
        for locale in ("ru", "de", "uk"):
            record_mt_version(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                locale=locale,
                text=f"{text} [{locale}]",
                source_locale="en",
                source_hash=source_hash,
            )
    db.commit()
    return question


class TestAnEditedSourceReopensTheQuestion:
    def test_it_starts_settled(self, db: Session, settled_question) -> None:
        assert questions_missing_a_language(db, limit=10) == []

    def test_editing_the_question_puts_it_back_in_the_queue(self, db: Session, settled_question) -> None:
        record_human_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=str(settled_question.id),
            field="question_text",
            locale="en",
            text=EDITED,
        )
        db.commit()

        assert [q.id for q in questions_missing_a_language(db, limit=10)] == [settled_question.id]

    def test_editing_an_option_does_too(self, db: Session, settled_question) -> None:
        option = db.query(DailyChallengeOption).filter_by(question_id=settled_question.id).one()
        record_human_version(
            db,
            entity_type="daily_challenge_option",
            entity_id=str(option.id),
            field="option_text",
            locale="en",
            text="The Holy Spirit was poured out on the disciples",
        )
        db.commit()

        assert [q.id for q in questions_missing_a_language(db, limit=10)] == [settled_question.id]

    def test_a_question_nobody_touched_stays_settled(self, db: Session, settled_question) -> None:
        # The sweep runs on every idle tick; a false positive here would
        # re-translate the whole pool forever.
        assert questions_missing_a_language(db, limit=10) == []
        assert questions_missing_a_language(db, limit=10) == []
