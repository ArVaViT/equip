# ruff: noqa: RUF002, RUF003
# Edition and psalm text quoted in the prose is Cyrillic because that is what it is.
"""Asking a Septuagint-numbered bible for a Hebrew psalm gets an answer.

That is the whole danger. The two numbering systems disagree, and a
bible following the other one does not say "no such psalm" — it returns
a *different* psalm, fluent and well-formed, and nothing anywhere
reports a problem.

The platform's references are Hebrew-numbered because English editions
are. `verse_of_the_day` knew that and translated them. The substitution
layer — which serves every quoted verse in every course and every Daily
Challenge explanation — did not, and asked the Russian edition for
Hebrew numbers directly.

Checked against the live API on 2026-08-15: Psalm 23:1 in Russian came
back as "Господня земля и всё, что наполняет её". That is Hebrew 24.
The shepherd psalm, quoted to Russian readers as the earth being the
Lord's, everywhere it appeared.

The first fix subtracted one from the chapter, which is the rule
everybody quotes and is not enough. Re-measured against the live
edition on 2026-08-16, the numbers below are what it actually answers:
the verse moves as well as the chapter, the shift is not constant
inside a psalm, and two psalms that share a number do not share their
verse numbers. Every expectation in this file was read off НРТ rather
than derived from the rule.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

from app.services.bible.psalm_numbering import SEPTUAGINT_LOCALES, remap_psalm, remap_usfm
from app.services.bible.references import BibleRef

TABLE_PATH = (
    Path(__file__).resolve().parent.parent / "app" / "services" / "bible" / "data" / "psalm_hebrew_to_septuagint.json"
)


class TestTheRussianEditionCountsDifferently:
    def test_the_shepherd_psalm_is_asked_for_by_its_own_number(self):
        # Hebrew 23 is Septuagint 22. Ask for 23 and you get Hebrew 24.
        assert remap_psalm(BibleRef("psalms", 23, 1), "ru") == BibleRef("psalms", 22, 1)

    def test_a_range_keeps_its_shape(self):
        assert remap_psalm(BibleRef("psalms", 23, 1, 6), "ru") == BibleRef("psalms", 22, 1, 6)

    @pytest.mark.parametrize(
        ("hebrew", "septuagint"),
        [
            # "Taste and see that the Lord is good" — the chapter shifts
            # by one and so does the verse, because the Slavic tradition
            # numbers the superscription the Hebrew leaves unnumbered.
            ((34, 8), (33, 9)),
            # "Create in me a clean heart": two heading verses here, so
            # the verse moves by two while the chapter moves by one.
            ((51, 10), (50, 12)),
            ((51, 1), (50, 3)),
            # "My God, my God, why have you forsaken me". Asking 21:1
            # returns "Начальнику хора. При появлении зари" — a heading
            # served as scripture, which is what the chapter-only rule
            # did here.
            ((22, 1), (21, 2)),
            ((42, 1), (41, 2)),
            # Same number in both systems, verses still shifted. The old
            # rule called Psalms 1-8 identical and quoted all of them
            # one verse early.
            ((3, 1), (3, 2)),
            ((8, 1), (8, 2)),
            # Hebrew 10 is not a separate psalm in the Slavic tradition:
            # it continues 9. This used to be refused outright.
            ((10, 1), (9, 22)),
            # Hebrew 116 is split across two Slavic psalms; its first
            # verse lands in the first of them.
            ((116, 1), (114, 1)),
            ((147, 1), (146, 1)),
            ((46, 10), (45, 11)),
            ((91, 1), (90, 1)),
            ((119, 105), (118, 105)),
        ],
    )
    def test_it_answers_what_the_edition_actually_holds(self, hebrew, septuagint):
        chapter, verse = hebrew
        assert remap_psalm(BibleRef("psalms", chapter, verse), "ru") == BibleRef("psalms", *septuagint)

    @pytest.mark.parametrize("reference", [(1, 1), (2, 1), (148, 6), (149, 1), (150, 6)])
    def test_the_psalms_both_systems_agree_on_are_untouched(self, reference):
        ref = BibleRef("psalms", reference[0], reference[1])
        assert remap_psalm(ref, "ru") == ref

    def test_a_range_that_would_straddle_two_psalms_is_refused(self):
        # Hebrew 116 becomes Slavic 114 and 115. A span across the seam
        # cannot be named by one reference, and inventing one would
        # quote the wrong half.
        assert remap_psalm(BibleRef("psalms", 116, 1, 19), "ru") is None


class TestEveryoneElseIsLeftAlone:
    @pytest.mark.parametrize("locale", ["en", "de", "uk"])
    def test_a_psalm_whose_heading_shares_verse_one_passes_through(self, locale: str):
        # Psalm 23's heading is not a verse of its own in any edition
        # served here, so its verse 1 is its verse 1 everywhere. This
        # used to be asserted of every psalm and every non-Russian
        # locale, which is the shape the superscription defect hid in —
        # see ``TestTheHeadingIsAVerseInSomeEditions``.
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

    def test_it_shifts_the_verse_too(self):
        assert remap_usfm("PSA.34.8", "ru") == "PSA.33.9"

    def test_a_psalm_that_used_to_be_refused_now_has_an_answer(self):
        assert remap_usfm("PSA.116.1", "ru") == "PSA.114.1"

    def test_a_range_across_the_seam_is_still_refused(self):
        assert remap_usfm("PSA.116.1-19", "ru") is None

    def test_a_range_within_one_psalm_moves_whole(self):
        assert remap_usfm("PSA.23.1-6", "ru") == "PSA.22.1-6"

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
    for chapter in (1, 9, 10, 23, 51, 113, 116, 147, 150):
        by_ref = remap_psalm(BibleRef("psalms", chapter, 1), "ru")
        by_string = remap_usfm(f"PSA.{chapter}.1", "ru")
        assert by_ref is not None
        assert by_string == f"PSA.{by_ref.chapter}.{by_ref.verse_start}", chapter


class TestTheTableItself:
    """What makes the table believable is its shape.

    Each Slavic psalm should receive an unbroken run of verses starting
    at 1, 2 or 3 — at 2 or 3 where that psalm's heading occupies the
    first verse or two, which the Hebrew numbering has nothing to map
    onto. A gap in the middle of a psalm, or a run starting at 4, would
    mean a verse had been read off the wrong marker; that is exactly how
    the two defects in the derivation were found, before any of this
    reached a reader.
    """

    def test_every_psalm_receives_an_unbroken_run(self):
        table: dict[str, str] = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
        landed: dict[int, set[int]] = collections.defaultdict(set)
        for septuagint in table.values():
            chapter, verse = septuagint.split(".")
            landed[int(chapter)].add(int(verse))

        for chapter, verses in sorted(landed.items()):
            ordered = sorted(verses)
            assert ordered[0] in (1, 2, 3), f"psalm {chapter} starts at {ordered[0]}"
            assert ordered == list(range(ordered[0], ordered[0] + len(ordered))), f"psalm {chapter} has a gap"

    def test_it_covers_the_whole_book(self):
        table: dict[str, str] = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
        chapters = {int(key.split(".")[0]) for key in table}
        # Psalms 1, 2, 148, 149 and 150 are numbered identically and are
        # deliberately absent: absent means identical.
        assert chapters == set(range(3, 148))
