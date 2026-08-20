# ruff: noqa: RUF001
# The Cyrillic and the digit pairs beside it are the material under test.
"""Two numbers with a colon between them are not a Bible reference.

``_VERSE_REF_RE`` matched any two numbers separated by a colon or a dot
inside plausible chapter and verse bounds, and a time of day fits those
bounds exactly. Verified on 2026-08-19 against the real validator, in
both directions:

    "The class meets at 2:30"     -> "Der Kurs beginnt um 14:30 Uhr"
    "Занятие начинается в 14:30"  -> "The class meets at 2:30"

Both came back ``verse_reference_lost``, which is blocking, which parks
the row at ``needs_review`` — where ``executor`` skips it for as long as
the source hash is unchanged, and the reconciler reads the course as
waiting on a person. A timetable in a lesson retires the lesson.

``Урок 3.2 и 4.5 расписания`` is the same trap one step earlier: the
validator reads it as two references, 3:2 and 4:5, and stays quiet only
for as long as the translation happens to repeat both digits.

``bible.references.parse_references`` has always answered this properly
— it will not call anything a reference unless a declared book name
stands in front of it — so it is what decides the source side now.
"""

from __future__ import annotations

from app.services.bible.references import parse_references
from app.services.translation.validation import ValidationIssue, validate_translation


def blocking(issues: list[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues if issue.blocking}


class TestATimeOfDayIsNotAReference:
    def test_an_english_clock_becoming_a_german_one(self):
        issues = validate_translation(
            source="<p>The class meets at 2:30 in the afternoon in the main building.</p>",
            translated="<p>Der Kurs beginnt um 14:30 Uhr im Hauptgebäude.</p>",
            source_locale="en",
            target_locale="de",
        )
        assert blocking(issues) == set()

    def test_a_russian_clock_becoming_an_english_one(self):
        issues = validate_translation(
            source="<p>Занятие начинается в 14:30 в главном корпусе.</p>",
            translated="<p>The class meets at 2:30 in the afternoon in the main building.</p>",
            source_locale="ru",
            target_locale="en",
        )
        assert blocking(issues) == set()


class TestASectionNumberIsNotAReference:
    def test_lesson_numbering_is_not_read_as_chapter_and_verse(self):
        issues = validate_translation(
            source="<p>Урок 3.2 и 4.5 расписания на этой неделе для всех студентов.</p>",
            translated="<p>Woche drei, zweiter Teil, und Woche vier, fünfter Teil, für alle Studenten.</p>",
            source_locale="ru",
            target_locale="de",
        )
        assert blocking(issues) == set()

    def test_the_parser_agrees_no_book_no_reference(self):
        assert parse_references("The class meets at 2:30") == []
        assert parse_references("Урок 3.2 и 4.5 расписания") == []


class TestAReferenceWithABookInFrontOfItIsStillGuarded:
    def test_a_reference_that_really_vanished_is_caught(self):
        issues = validate_translation(
            source="<p>What is promised to anyone who believes, as stated in John 3:14-16?</p>",
            translated="<p>Was wird jedem versprochen, der glaubt, wie die Stelle es beschreibt?</p>",
            source_locale="en",
            target_locale="de",
        )
        assert "verse_reference_lost" in blocking(issues)

    def test_a_different_verse_is_not_the_same_reference(self):
        issues = validate_translation(
            source="<p>What does the passage promise, as stated in John 3:16 exactly?</p>",
            translated="<p>Was verspricht die Stelle, wie in Johannes 3,17 beschrieben?</p>",
            source_locale="en",
            target_locale="de",
        )
        assert "verse_reference_lost" in blocking(issues)

    def test_the_target_language_may_print_it_its_own_way(self):
        # The translation side stays a loose scan of the digits on
        # purpose: no alias list here knows the word Johannes, and
        # demanding a recognised book name on that side would report
        # every correct German reference as lost.
        issues = validate_translation(
            source="<p>What does the passage promise, as stated in John 3:14-16 exactly?</p>",
            translated="<p>Was verspricht die Stelle, wie in Johannes 3,14–16 beschrieben?</p>",
            source_locale="en",
            target_locale="de",
        )
        assert blocking(issues) == set()
