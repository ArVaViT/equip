"""Asking a Septuagint-numbered bible for a Hebrew psalm gets an answer.

That is the whole danger. The two numbering systems disagree from Psalm
10 to Psalm 147, and a bible following the other one does not say "no
such psalm" — it returns a *different* psalm, fluent and well-formed,
and nothing anywhere reports a problem.

The platform's references are Hebrew-numbered because English editions
are. `verse_of_the_day` knew that and translated them. The substitution
layer — which serves every quoted verse in every course and every Daily
Challenge explanation — did not, and asked the Russian edition for
Hebrew numbers directly.

Checked against the live API on 2026-08-15: Psalm 23:1 in Russian came
back as "Господня земля и всё, что наполняет её". That is Hebrew 24.
The shepherd psalm, quoted to Russian readers as the earth being the
Lord's, everywhere it appeared.
"""

from __future__ import annotations

import pytest

from app.services.bible.psalm_numbering import SEPTUAGINT_LOCALES, remap_psalm, remap_usfm
from app.services.bible.references import BibleRef


class TestTheRussianEditionCountsDifferently:
    def test_the_shepherd_psalm_is_asked_for_by_its_own_number(self):
        # Hebrew 23 is Septuagint 22. Ask for 23 and you get Hebrew 24.
        remapped = remap_psalm(BibleRef("psalms", 23, 1), "ru")
        assert remapped == BibleRef("psalms", 22, 1)

    def test_a_range_keeps_its_shape(self):
        remapped = remap_psalm(BibleRef("psalms", 23, 1, 6), "ru")
        assert remapped == BibleRef("psalms", 22, 1, 6)

    @pytest.mark.parametrize("chapter", [1, 5, 8, 148, 149, 150])
    def test_the_psalms_both_systems_agree_on_are_untouched(self, chapter: int):
        ref = BibleRef("psalms", chapter, 1)
        assert remap_psalm(ref, "ru") == ref

    @pytest.mark.parametrize("chapter", [9, 10, 114, 115, 116, 147])
    def test_a_split_psalm_is_refused_rather_than_guessed(self, chapter: int):
        # One system splits what the other joins. No per-verse mapping is
        # truthful, so the honest answer is "this edition cannot be asked
        # for this reference" and the caller keeps the author's quotation.
        assert remap_psalm(BibleRef("psalms", chapter, 1), "ru") is None


class TestEveryoneElseIsLeftAlone:
    @pytest.mark.parametrize("locale", ["en", "de", "uk"])
    def test_hebrew_numbered_editions_pass_through(self, locale: str):
        ref = BibleRef("psalms", 23, 1)
        assert remap_psalm(ref, locale) == ref

    def test_ukrainian_is_not_assumed_to_be_slavic_about_it(self):
        # Куліш numbers the Hebrew way. Assuming otherwise because the
        # language is Slavic would have been reasonable and wrong — it
        # was measured, not inferred.
        assert "uk" not in SEPTUAGINT_LOCALES
        assert set(SEPTUAGINT_LOCALES) == {"ru"}

    @pytest.mark.parametrize("book", ["john", "genesis", "revelation"])
    def test_nothing_outside_the_psalms_is_touched(self, book: str):
        ref = BibleRef(book, 3, 16)
        assert remap_psalm(ref, "ru") == ref


class TestTheUsfmSpelling:
    """The verse-of-the-day walk speaks USFM strings end to end. Same
    rule, one definition — two copies would drift into quoting
    different psalms on different pages."""

    def test_it_shifts(self):
        assert remap_usfm("PSA.23.1", "ru") == "PSA.22.1"

    def test_it_refuses_a_split_psalm(self):
        assert remap_usfm("PSA.116.1", "ru") is None

    def test_it_leaves_other_books_alone(self):
        assert remap_usfm("JHN.3.16", "ru") == "JHN.3.16"

    @pytest.mark.parametrize("locale", ["en", "de", "uk"])
    def test_it_leaves_other_editions_alone(self, locale: str):
        assert remap_usfm("PSA.23.1", locale) == "PSA.23.1"

    def test_a_malformed_reference_is_passed_through_rather_than_raising(self):
        # Never the reason a page fails to render.
        assert remap_usfm("PSA.oops", "ru") == "PSA.oops"


def test_the_two_spellings_agree():
    """The regression that matters: one rule, two call shapes."""
    for chapter in (1, 9, 23, 51, 113, 116, 147, 150):
        by_ref = remap_psalm(BibleRef("psalms", chapter, 1), "ru")
        by_string = remap_usfm(f"PSA.{chapter}.1", "ru")
        if by_ref is None:
            assert by_string is None, chapter
        else:
            assert by_string == f"PSA.{by_ref.chapter}.1", chapter
