# ruff: noqa: RUF001
# Cyrillic course titles are compared against Latin-alphabet prompt text
# throughout; the confusable-character rule has nothing to say about any
# of it.
"""The instruction has to fit the fourth course, not only the first three.

Every translation call used to open by telling the model it was working
for a Bible-study platform, and rule 9 told it the audience was a Bible
school in a Slavic Pentecostal community and the register was "plain,
warm, unhurried. Not academic, not corporate, not liturgical."

That was measured, on German, and it was right for the catalogue it was
measured on — three courses on Scripture. It is wrong for a course on
church finance, on contract law, on a clinical procedure. Those are
written formally on purpose, and "not academic" instructs the model to
lower a register the author raised, while rule 8 — write the sentence a
German author would have written — pulls the other way.

The evidence for what a course is about was already in the prompt and
was being contradicted by it: ``registry.py`` puts the course's own
title in the context line of every entity, and the source text itself
is right there between the fences. So the register is read off those
two rather than asserted, and what the old rule was actually buying —
German that stops inflating itself — is kept as the drift it is.

Measured before shipping, ru→de/uk/en, 25 real strings from the three
live courses: against the old prompt the pairs split 11-11 under a blind
judge, while the old prompt against its own second run split 15-7. The
change moves the output less than re-running the same prompt does.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.models.course import Course, CourseStatus
from app.models.quiz import QuizOption
from app.services.translation.prompt import build_system_prompt
from app.services.translation.registry import REGISTRY
from app.services.translation.reviewer import build_review_prompt, quotes_scripture

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

LOCALES = ["de", "uk", "en", "ru"]
FALLBACK_TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-00000000bd12")


class TestTheSystemPromptNamesNoSubject:
    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_prompt_no_longer_tells_every_call_it_is_a_bible_school(self, locale: str) -> None:
        # A course on church finance is translated by this same prompt,
        # and a false premise in the opening sentence is one the model
        # is entitled to believe.
        prompt = build_system_prompt(source_locale="ru", target_locale=locale)
        assert "Bible school" not in prompt
        assert "Bible-study" not in prompt
        assert "Pentecostal" not in prompt

    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_register_is_taken_from_the_source_rather_than_named(self, locale: str) -> None:
        prompt = build_system_prompt(source_locale="ru", target_locale=locale)
        assert "Take the register from the source" in prompt
        # The four registers a subject can arrive in, each told to survive.
        for word in ("Plain stays plain", "technical stays technical", "formal stays formal"):
            assert word in prompt

    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_model_is_pointed_at_the_context_line_for_the_subject(self, locale: str) -> None:
        # The course title has been travelling in the context line since
        # before this change; nothing new is stored to make this work.
        prompt = build_system_prompt(source_locale="ru", target_locale=locale)
        assert "names the course this text belongs to" in prompt

    @pytest.mark.parametrize("locale", ["de", "uk", "en"])
    def test_the_measured_german_lesson_survives_as_a_direction_not_a_destination(self, locale: str) -> None:
        # What the old rule bought was output that stops reaching for a
        # register the source has not got. Losing that would undo a
        # measured fix; keeping it as a named destination would break
        # every course that is formal on purpose.
        prompt = build_system_prompt(source_locale="ru", target_locale=locale)
        assert "The drift to watch for is upward" in prompt
        assert "Add no gravity the source has not got" in prompt
        assert "Take none away either" in prompt

    def test_the_structural_rules_and_the_language_notes_are_untouched(self) -> None:
        # Rule 9 was rewritten in place. Rules 1-8 and the per-language
        # notes are what keeps a verse a verse and a calque out.
        prompt = build_system_prompt(source_locale="ru", target_locale="de")
        assert "EQV" in prompt
        assert "Translate ONLY" in prompt
        assert "10. German specifics" in prompt

    def test_it_stays_free_of_dynamic_state(self) -> None:
        # The docstring's promise: the same pair gives the same prompt,
        # so a change to it shows up in review and nowhere else.
        assert build_system_prompt(source_locale="ru", target_locale="de") == build_system_prompt(
            source_locale="ru", target_locale="de"
        )


class TestTheReviewerObjectsToTranslationDefects:
    def test_the_editor_is_no_longer_hired_by_a_bible_school(self) -> None:
        prompt = build_review_prompt(
            source="Пожертвование в размере 250 долларов США.",
            translation="Eine Spende in Höhe von 150 US-Dollar.",
            source_language="Russian",
            target_language="German",
            content_kind="html",
            context="Lesson block from the course «Финансы поместной церкви»",
            source_locale="ru",
        )
        assert "Bible school" not in prompt

    def test_a_wrong_number_unit_or_term_of_art_is_a_named_objection_class(self) -> None:
        # The old list named seven classes and none of them covered a
        # mistranslated legal term, a wrong unit or a dosage.
        prompt = build_review_prompt(
            source="Доза составляет 10–15 мг/кг.",
            translation="Die Dosis beträgt 10–15 mg/g.",
            source_language="Russian",
            target_language="German",
            content_kind="html",
            context="Lesson block from the course «Основы клинической практики»",
            source_locale="ru",
        )
        assert "a name, a term of art, a number, a unit, a date or a citation" in prompt

    def test_the_register_objection_is_measured_against_the_source(self) -> None:
        prompt = build_review_prompt(
            source="Пётр встал и просто сказал: покайтесь.",
            translation="Petrus erhob sich und verkündigte in feierlicher Weise die Notwendigkeit der Umkehr.",
            source_language="Russian",
            target_language="German",
            content_kind="html",
            context="Lesson block from the course «Книга Деяний Апостолов»",
            source_locale="ru",
        )
        assert "the register does not match the source" in prompt
        assert "the source is formal and the translation is chatty" in prompt

    def test_scripture_objections_are_offered_when_the_text_quotes_scripture(self) -> None:
        prompt = build_review_prompt(
            source="Формула соборного решения записана в Деян. 15:28.",
            translation="Die Formel des Konzilsbeschlusses steht in Apg 16,28.",
            source_language="Russian",
            target_language="German",
            content_kind="html",
            context="Lesson block from the course «Книга Деяний Апостолов»",
            source_locale="ru",
        )
        assert "chapter-and-verse reference" in prompt
        assert "quoted from a German Bible" in prompt

    def test_scripture_objections_are_withheld_when_there_is_no_scripture(self) -> None:
        # Two of seven slots spent on something that cannot occur is two
        # slots the wrong unit and the wrong legal term do not get.
        prompt = build_review_prompt(
            source="Пересчёт наличных производится не менее чем двумя лицами.",
            translation="Das Bargeld wird von mindestens zwei Personen gezählt.",
            source_language="Russian",
            target_language="German",
            content_kind="html",
            context="Lesson block from the course «Финансы поместной церкви»",
            source_locale="ru",
        )
        assert "chapter-and-verse reference" not in prompt
        assert "Bible" not in prompt

    def test_a_caller_that_names_no_source_locale_still_gets_a_prompt(self) -> None:
        # ``source_locale`` is optional so no existing caller breaks;
        # without it the parser still recognises an English reference,
        # and a text with none simply gets the subject-neutral list.
        with_ref = build_review_prompt(
            source="The council's formula is recorded in Acts 15:28.",
            translation="Die Formel steht in Apg 15,28.",
            source_language="English",
            target_language="German",
            content_kind="html",
            context=None,
        )
        assert "chapter-and-verse reference" in with_ref

    def test_the_objections_it_already_earned_are_still_on_the_list(self) -> None:
        # The classes below are the ones a person actually caught in
        # production. Rewriting the list must not have dropped one.
        prompt = build_review_prompt(
            source="Гамалиил формулирует принцип перед Синедрионом.",
            translation="Nikodemus formuliert den Grundsatz vor dem Sanhedrin.",
            source_language="Russian",
            target_language="German",
            content_kind="html",
            context=None,
            source_locale="ru",
        )
        assert "says something the source does not" in prompt
        assert "grammar a native speaker would not write" in prompt
        assert "word order or idiom carried over" in prompt
        assert "Do NOT object to a wording you would merely have chosen" in prompt


class TestQuotesScripture:
    @pytest.mark.parametrize(
        "source",
        [
            "Формула записана в Деян. 15:28.",
            "Давид пророчествовал об этом в Пс. 109:1.",
            "See Acts 1:8 for the commission.",
        ],
    )
    def test_a_text_carrying_a_reference_is_recognised(self, source: str) -> None:
        assert quotes_scripture(source, "ru") is True

    @pytest.mark.parametrize(
        "source",
        [
            "Пересчёт наличных производится не менее чем двумя лицами.",
            "Доза парацетамола составляет 10–15 мг/кг массы тела на приём.",
            "Организация, освобождённая от налогообложения, ведёт раздельный учёт.",
            "",
        ],
    )
    def test_a_text_with_no_reference_is_not_mistaken_for_scripture(self, source: str) -> None:
        assert quotes_scripture(source, "ru") is False

    def test_a_section_number_that_looks_like_a_reference_is_not_one(self) -> None:
        # 501(c)(3) and 15:28 are both digits and punctuation. Only one
        # of them names a book, which is what the detector keys on.
        assert quotes_scripture("В соответствии с пунктом 501(c)(3) Кодекса.", "ru") is False


class TestTheOptionFallbackReportsTheCourseInsteadOfAssertingASubject:
    """The one context line in the registry that named a subject.

    When an option's question text cannot be fetched, everything the
    model had left was "Answer option for a Bible-study quiz question."
    On a module about church finance that line is not a hint, it is a
    false statement about the subject, and it is the only thing in the
    prompt describing the text. The course title is already resolved by
    the caller; saying that instead costs nothing and is true.
    """

    def test_the_course_is_named_when_the_question_cannot_be_fetched(self, db: Session) -> None:
        orphan = QuizOption(id=uuid.uuid4(), question_id=uuid.uuid4(), order_index=0, is_correct=False)
        course = Course(
            id=f"course-{uuid.uuid4().hex[:8]}",
            status=CourseStatus.PUBLISHED,
            source_locale="ru",
            created_by=FALLBACK_TEACHER_ID,
        )
        course.title = "Финансы поместной церкви"
        context = REGISTRY["quiz_option"].build_context_with_db(db, orphan, course)
        assert "Финансы поместной церкви" in context
        assert "Bible" not in context

    def test_a_course_with_no_hydrated_title_still_gets_a_line(self, db: Session) -> None:
        # ``course.title`` comes from content_versions and a caller that
        # has not hydrated it raises AttributeError, which the pipeline
        # hook swallows — leaving the entity silently untranslated.
        orphan = QuizOption(id=uuid.uuid4(), question_id=uuid.uuid4(), order_index=0, is_correct=False)
        assert REGISTRY["quiz_option"].build_context_with_db(db, orphan, None) == ("Answer option for a quiz question.")
