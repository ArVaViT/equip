# ruff: noqa: RUF002
# German and Ukrainian fixtures quoted from production.
"""A note to the choirmaster, printed where the psalm should be.

The defect
----------
A psalm may carry a heading — "To the choirmaster. A Psalm of David." —
and the editions disagree about whether that heading is a verse. English
does not number it, and every reference on this platform is written in
English numbering. Elberfelder numbers it. So a Daily Challenge question
about Psalm 51:1 reached the German reader on 2026-08-22 as

    Ps. 51,1 besagt: „(Dem Vorsänger. Ein Psalm von David,“ Dieser Vers
    verbindet die Bitte um Gnade direkt mit Gottes Güte und
    Barmherzigkeit.

— an explanation about a plea for mercy, and no plea for mercy anywhere
on the page. Four of the twelve psalms a reader can reach were in that
state: 8:1, 19:1, 22:1 and 51:1.

Five more were not empty but prefixed, because where the heading is too
short to be its own verse Elberfelder prints it inside verse 1 in
parentheses::

    Ps. 23,1 („(Ein Psalm von David.) Der HERR ist mein Hirte, mir wird
    nichts mangeln.“)

Two separate mistakes with one origin, and they are fixed in two places:
the numbering in ``psalm_numbering``, the parenthesis in
``api_source._without_edition_heading``.

Ukrainian is the interesting one
--------------------------------
Куліш looks like the same case — its Psalm 51:1 also opens with the
choirmaster's rubric — and it is not. It merges the heading into verse 1
rather than numbering it, so its verse numbers are already the
platform's own. Verified against the live API on 2026-08-22: asked for
Psalm 51:3 it answers «Знаю бо переступи мої», the third verse in
English numbering. Shifting Ukrainian would have quoted the wrong verse
in nine psalms to fix the punctuation of nine others.
"""

from __future__ import annotations

import pytest

from app.services.bible.api_source import _without_edition_heading
from app.services.bible.psalm_numbering import (
    SUPERSCRIPTION_NUMBERING_LOCALES,
    remap_psalm,
    renumber_between,
    superscription_verses,
)
from app.services.bible.references import BibleRef


class TestTheTableSaysWhichPsalmsHaveOne:
    @pytest.mark.parametrize(
        ("chapter", "verses"),
        [
            (1, 0),  # no heading at all
            (23, 0),  # heading shares verse 1 with "The LORD is my shepherd"
            (91, 0),
            (103, 0),
            (110, 0),
            (121, 0),
            (139, 0),
            (3, 1),
            (8, 1),
            (19, 1),
            (22, 1),
            (51, 2),  # two verses of heading: the rubric, then Nathan and Bathsheba
            (52, 2),
            (54, 2),
            (60, 2),
        ],
    )
    def test_a_named_psalm_has_the_heading_the_synodal_text_marks(self, chapter: int, verses: int) -> None:
        assert superscription_verses(chapter) == verses

    def test_a_psalm_the_septuagint_merges_is_not_read_as_a_long_heading(self) -> None:
        # Hebrew 10 is not a separate psalm in the Slavic tradition and
        # its first verse is Slavic 9:22. Read as an offset that is
        # twenty-one; read as a count of pieces it is what it is, one
        # piece and no heading.
        assert superscription_verses(10) == 0
        assert superscription_verses(115) == 0


class TestTheTableIsDerivedAndStaysDerived:
    def test_the_checked_in_table_still_matches_the_synodal_text_it_came_from(self) -> None:
        # A table that is typed drifts from its source in silence. This
        # is the ``--check`` mode of the script that writes it, run
        # where drift fails a build instead of a reading.
        from scripts.derive_psalm_superscription_verses import build

        assert {int(chapter): offset for chapter, offset in build().items()} == {
            chapter: superscription_verses(chapter) for chapter in range(1, 151) if superscription_verses(chapter)
        }


class TestTheGermanReferenceMoves:
    @pytest.mark.parametrize(
        ("chapter", "verse", "expected"),
        [
            (8, 1, 2),  # "HERR, unser Herr, wie herrlich ist dein Name"
            (19, 1, 2),  # "Die Himmel erzählen die Herrlichkeit Gottes"
            (22, 1, 2),  # "Mein Gott, mein Gott, warum hast du mich verlassen"
            (51, 1, 3),  # "Sei mir gnädig, o Gott"
        ],
    )
    def test_a_psalm_whose_heading_is_a_verse_is_asked_for_one_verse_later(
        self, chapter: int, verse: int, expected: int
    ) -> None:
        # All four confirmed against the live API on 2026-08-22 at the
        # shifted number.
        assert remap_psalm(BibleRef("psalms", chapter, verse), "de") == BibleRef("psalms", chapter, expected)

    def test_a_range_moves_with_both_of_its_ends(self) -> None:
        assert remap_psalm(BibleRef("psalms", 22, 1, 5), "de") == BibleRef("psalms", 22, 2, 6)

    def test_a_psalm_without_a_numbered_heading_does_not_move(self) -> None:
        ref = BibleRef("psalms", 23, 1)
        assert remap_psalm(ref, "de") == ref

    def test_nothing_outside_the_psalter_moves(self) -> None:
        ref = BibleRef("acts", 1, 8)
        assert remap_psalm(ref, "de") == ref


class TestUkrainianIsNotGerman:
    def test_kulish_numbers_the_psalms_the_way_the_reference_does(self) -> None:
        # Measured, not inferred from the language or from the rubric
        # showing up in its verse 1.
        assert "uk" not in SUPERSCRIPTION_NUMBERING_LOCALES
        assert set(SUPERSCRIPTION_NUMBERING_LOCALES) == {"de"}

    @pytest.mark.parametrize("chapter", [8, 19, 22, 51])
    def test_a_ukrainian_psalm_reference_is_left_where_the_author_wrote_it(self, chapter: int) -> None:
        ref = BibleRef("psalms", chapter, 1)
        assert remap_psalm(ref, "uk") == ref


class TestTheThreeSystemsAgreeWithEachOther:
    def test_a_russian_psalm_reference_reaches_the_german_edition_at_its_own_number(self) -> None:
        # The Russian author writes the Synodal number; the German
        # edition prints its own. Both shifts compose.
        assert renumber_between(
            BibleRef("psalms", 21, 2),
            source_locale="ru",
            target_locale="de",
        ) == (BibleRef("psalms", 22, 2),)

    def test_an_english_reference_reaches_the_german_edition_at_its_own_number(self) -> None:
        assert renumber_between(
            BibleRef("psalms", 22, 1),
            source_locale="en",
            target_locale="de",
        ) == (BibleRef("psalms", 22, 2),)

    def test_a_german_number_naming_the_heading_answers_to_no_english_verse(self) -> None:
        # Elberfelder's Psalm 22:1 is the heading, and the reference
        # system does not number the heading. There is no English verse
        # to offer, and offering the nearest one would be a guess.
        assert renumber_between(BibleRef("psalms", 22, 1), source_locale="de", target_locale="en") == ()


class TestTheHeadingPrintedInsideVerseOne:
    @pytest.mark.parametrize(
        ("printed", "expected"),
        [
            (
                "(Ein Psalm von David.) Der HERR ist mein Hirte, mir wird nichts mangeln.",
                "Der HERR ist mein Hirte, mir wird nichts mangeln.",
            ),
            ("(Von David.) Preise den HERRN, meine Seele!", "Preise den HERRN, meine Seele!"),
            ("(Ein Stufenlied.) Ich hebe meine Augen auf zu den Bergen.", "Ich hebe meine Augen auf zu den Bergen."),
            (
                "(Dem Vorsänger. Von David, ein Psalm.) HERR! Du hast mich erforscht und erkannt.",
                "HERR! Du hast mich erforscht und erkannt.",
            ),
        ],
    )
    def test_the_editions_own_parentheses_are_read_as_the_heading(self, printed: str, expected: str) -> None:
        assert _without_edition_heading(printed, BibleRef("psalms", 1, 1)) == expected

    def test_a_heading_with_nothing_behind_it_is_left_alone(self) -> None:
        # Cutting here would hand the reader an empty verse, which is
        # worse than a rubric. This case cannot arise once the numbering
        # is right, and the rule does not depend on that being true.
        printed = "(Dem Vorsänger. Ein Psalm von David.)"
        assert _without_edition_heading(printed, BibleRef("psalms", 1, 1)) == printed

    def test_a_verse_that_is_not_the_first_keeps_everything_it_was_sent(self) -> None:
        printed = "(Ein Psalm von David.) Der HERR ist mein Hirte."
        assert _without_edition_heading(printed, BibleRef("psalms", 23, 2)) == printed

    def test_a_book_that_is_not_the_psalter_keeps_everything_it_was_sent(self) -> None:
        printed = "(Dies geschah, damit erfüllt würde.) Und er sprach zu ihnen."
        assert _without_edition_heading(printed, BibleRef("matthew", 1, 1)) == printed

    def test_a_ukrainian_heading_carrying_no_parentheses_is_left_alone(self) -> None:
        # Куліш prints the same rubric with nothing marking where it
        # ends. The psalm is still behind it, which is more than the
        # German reader had; cutting at a guessed sentence boundary is
        # the edit this layer refuses to make.
        printed = "Псальма Давидова. Господь пастирь мій, не мати му недостатку."
        assert _without_edition_heading(printed, BibleRef("psalms", 23, 1)) == printed
