# ruff: noqa: RUF001
"""The fifth eternal requeue, and the first one inside the question pool.

A Daily Challenge field may carry more than one human row: the pool is
written in English and in Russian, and production has both for the same
question. The translation was made from one of them, and which one is
recorded nowhere except in the hash it kept.

The staleness check kept a single hash per field and let the last row of
an unordered result set win. When that was the row the translation was
*not* made from, the machine rows disagreed with it forever. The
question was reopened on every sweep, translated nothing — every field
was already current — and was reopened again on the next one.

Measured on 2026-08-20: the pool sweep spent every idle tick on the same
five questions, 24 rows each, all four locales, every row `ok` and at
the current generation, while 2,983 rows that were genuinely behind were
never reached. The worker reported `swept` with 90 fields skipped and
nothing translated, once a minute, for hours.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.models.daily_challenge import DailyChallengeQuestion
from app.services.content_versions import record_human_version, record_mt_version
from app.services.daily_challenge.translate import questions_missing_a_language
from app.services.translation.hash import compute_source_hash
from app.services.translation.version import TRANSLATOR_VERSION

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

RU = "В каком городе Павел встретил Акилу и Прискиллу?"
EN = "In which city did Paul meet Aquila and Priscilla?"


def _question(db: Session) -> DailyChallengeQuestion:
    question = DailyChallengeQuestion(
        id=uuid.uuid4(),
        question_type="multiple_choice",
        status="published",
        bible_book="Acts",
        bible_chapter=18,
        category="passage_exegesis",
        source_locale="ru",
    )
    db.add(question)
    db.flush()
    return question


def _finished_in_both_languages(db: Session, question: DailyChallengeQuestion, *, translated_from: str) -> None:
    """A question written by hand in English AND Russian, machine
    translated into the other two from ``translated_from``, and complete
    — nothing a worker tick could improve."""
    qid = str(question.id)
    record_human_version(
        db, entity_type="daily_challenge_question", entity_id=qid, field="question_text", locale="ru", text=RU
    )
    record_human_version(
        db, entity_type="daily_challenge_question", entity_id=qid, field="question_text", locale="en", text=EN
    )

    source_text = RU if translated_from == "ru" else EN
    source_hash = compute_source_hash(source_text, locale=translated_from)
    for locale, text in (("de", "In welcher Stadt traf Paulus Aquila?"), ("uk", "У якому місті Павло зустрів Акилу?")):
        record_mt_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=qid,
            field="question_text",
            locale=locale,
            text=text,
            source_locale=translated_from,
            source_hash=source_hash,
            translator_version=TRANSLATOR_VERSION,
        )
    db.commit()


class TestAQuestionNothingCanImprove:
    @pytest.mark.parametrize("translated_from", ["ru", "en"])
    def test_is_not_offered_as_work_whichever_language_it_came_from(self, db: Session, translated_from: str) -> None:
        """The defect, in both directions. Which human row the
        translation was made from must not decide whether the question
        looks finished — the machine rows match one of them either way."""
        question = _question(db)
        _finished_in_both_languages(db, question, translated_from=translated_from)

        picked = questions_missing_a_language(db, limit=10)

        assert question.id not in {q.id for q in picked}


class TestWhatTheCheckMustStillCatch:
    def test_a_translation_of_a_sentence_since_edited_is_still_reopened(self, db: Session) -> None:
        """The reason the hash check exists. A machine row matching none
        of the author's rows is a translation of text that has changed,
        and it must come back — 38 of them were serving stale answers in
        three languages until this check was added."""
        question = _question(db)
        qid = str(question.id)
        record_human_version(
            db, entity_type="daily_challenge_question", entity_id=qid, field="question_text", locale="ru", text=RU
        )
        record_mt_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=qid,
            field="question_text",
            locale="de",
            text="Eine Übersetzung von etwas anderem.",
            source_locale="ru",
            source_hash=compute_source_hash("Совершенно другой вопрос.", locale="ru"),
            translator_version=TRANSLATOR_VERSION,
        )
        db.commit()

        picked = questions_missing_a_language(db, limit=10)

        assert question.id in {q.id for q in picked}

    def test_a_row_from_an_older_generation_is_still_reopened(self, db: Session) -> None:
        """The other clause, unchanged: serving fine, made by rules we
        have since improved on."""
        question = _question(db)
        qid = str(question.id)
        record_human_version(
            db, entity_type="daily_challenge_question", entity_id=qid, field="question_text", locale="ru", text=RU
        )
        record_mt_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=qid,
            field="question_text",
            locale="de",
            text="Eine ältere Übersetzung.",
            source_locale="ru",
            source_hash=compute_source_hash(RU, locale="ru"),
            translator_version=max(0, TRANSLATOR_VERSION - 1),
        )
        db.commit()

        picked = questions_missing_a_language(db, limit=10)

        assert question.id in {q.id for q in picked}

    def test_a_missing_language_is_still_work(self, db: Session) -> None:
        """And the plainest case of all, which no amount of hashing
        should ever hide."""
        question = _question(db)
        qid = str(question.id)
        record_human_version(
            db, entity_type="daily_challenge_question", entity_id=qid, field="question_text", locale="ru", text=RU
        )
        db.commit()

        picked = questions_missing_a_language(db, limit=10)

        assert question.id in {q.id for q in picked}
