"""A citation pointing at a chapter the book does not have.

    3. Mose 34,1 besagt: „Und Mose stieg von den Ebenen Moabs auf den
    Berg Nebo…“

Leviticus ends at chapter 27. So this is not a misspelling and not a
matter of taste — it is an address that was never written. A German
reader following it finds nothing, and the verse standing beside it in
the lesson is Deuteronomy 34:1, which is what the English source cited.

That is how the live row got there: the model translated the book name
*Deuteronomy* as *3. Mose*, and every check that could have caught it
was looking elsewhere. ``book_name_not_printed_here`` asks whether the
language prints this spelling, and German prints ``3. Mose`` — for
Leviticus. ``proper_name_substituted`` is about people. Nothing asked
whether the numbers behind the name were possible.

Measured over every reader-reachable row on 2026-08-22: one hit, and it
is the row above. Which is also why the check earns its keep cheaply —
one regex decides that a row has no reference at all, and the source is
not read unless the translation has already failed.
"""

from __future__ import annotations

from app.services.bible.store import chapters_in
from app.services.translation.validation import validate_translation

_ISSUE = "reference_to_a_chapter_that_does_not_exist"


def _codes(source: str, translated: str, *, source_locale: str = "en", target_locale: str = "de") -> list[str]:
    return [
        issue.code
        for issue in validate_translation(
            source=source,
            translated=translated,
            source_locale=source_locale,
            target_locale=target_locale,
            content_kind="plain",
        )
    ]


class TestTheChapterCountsThemselves:
    def test_the_books_this_defect_is_about(self) -> None:
        """Read off the English bundle rather than written down a second
        time. If these ever drift, the bundle is wrong and much more than
        this check is affected."""
        assert chapters_in("leviticus") == 27
        assert chapters_in("deuteronomy") == 34
        assert chapters_in("psalms") == 150
        assert chapters_in("obadiah") == 1

    def test_something_that_is_not_a_book_has_no_count(self) -> None:
        assert chapters_in("the-gospel-of-thomas") is None


class TestTheLiveRow:
    def test_the_german_row_is_named_and_blocks(self) -> None:
        issues = validate_translation(
            source='Deuteronomy 34:1 states, "And Moses went up from the plains of Moab..."',
            translated="3. Mose 34,1 besagt: „Und Mose stieg von den Ebenen Moabs...“",
            source_locale="en",
            target_locale="de",
            content_kind="plain",
        )
        named = [i for i in issues if i.code == _ISSUE]
        assert named, "Leviticus has 27 chapters and the citation says 34"
        assert named[0].blocking is True
        assert "27" in named[0].detail

    def test_the_same_row_written_correctly_raises_nothing(self) -> None:
        assert _ISSUE not in _codes(
            'Deuteronomy 34:1 states, "And Moses went up from the plains of Moab..."',
            "5. Mose 34,1 besagt: „Und Mose stieg von den Ebenen Moabs...“",
        )


class TestWhatItMustNotSee:
    def test_an_ordinary_citation_is_silent(self) -> None:
        assert _ISSUE not in _codes(
            "Acts 1:8 is the programme of the book.",
            "Apostelgeschichte 1,8 ist das Programm des Buches.",
        )

    def test_the_last_chapter_of_a_book_is_not_one_past_it(self) -> None:
        """Leviticus 27 exists. An off-by-one here would flag the closing
        chapter of every book in the Bible."""
        assert _ISSUE not in _codes(
            "Leviticus 27:1 concerns vows.",
            "3. Mose 27,1 handelt von Gelübden.",
        )

    def test_a_source_that_already_carries_the_impossible_reference_is_not_the_translations_fault(self) -> None:
        """An author's own mistake, faithfully carried across. Reporting
        it here would park a translation for being accurate."""
        assert _ISSUE not in _codes(
            "Leviticus 34:1 is cited in the outline.",
            "3. Mose 34,1 wird in der Gliederung zitiert.",
        )

    def test_prose_with_no_citation_at_all_is_not_parsed(self) -> None:
        assert _ISSUE not in _codes(
            "The apostle writes about grace and truth.",
            "Der Apostel schreibt über Gnade und Wahrheit.",
        )

    def test_a_number_pair_that_is_not_a_reference_is_left_alone(self) -> None:
        """A clock is not a citation, which is the mistake
        ``_check_verse_refs`` was measured into fixing. The parser
        decides, not the regex — the regex only decides whether to ask
        the parser at all."""
        assert _ISSUE not in _codes(
            "The class meets at 2:30 and ends at 4:45.",
            "Der Kurs beginnt um 14:30 Uhr und endet um 16:45 Uhr.",
        )

    def test_a_psalm_past_the_psalter_is_named(self) -> None:
        """The Psalter ends at 150, and Psalm 151 is in some editions but
        not the reference system this platform counts by."""
        assert _ISSUE in _codes(
            "The Psalter closes with praise.",
            "Psalm 151,1 beschließt den Psalter.",
        )
