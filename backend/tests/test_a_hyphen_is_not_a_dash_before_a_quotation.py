# ruff: noqa: RUF001
"""A truncated word in quotation marks came back opened at both ends.

Found by running the pass over the live catalogue on 2026-08-21. Two
German chapter blocks teach how to look a verse up by a word, and both
say the same thing:

    nicht nach dem häufigen: „Senf-“, nicht „Korn“.

``„Senf-“`` is a word cut short inside quotation marks, which is
ordinary German — it is the stem you type into a concordance. The pass
returned ``„Senf-„``: an opening mark where the quotation ends.

The cause is that the opening test reads the single character before the
mark, and a dash is in the set of characters that open one. That is
right for a dash used as punctuation — ``— „Komm her“`` is the dialogue
dash German and Ukrainian both set — and wrong for a hyphen, which is
not punctuation at all but the tail of a word that has been cut off.
One character cannot tell them apart.

Two more characters can, and only one of them is needed: punctuation
stands apart from the word in front of it, a hyphen is welded to it. So
a dash opens a quotation only when whitespace, or the start of the
block, precedes the dash itself.

The classes below pin the fix, the production line it was found on, and
each of the things the fix had to leave standing.
"""

from __future__ import annotations

import pytest

from app.services.translation.typography import normalize_typography

# Verbatim from ``content_versions``, German, ``chapter_block.content``,
# rows d0ab8044 and 24d1d26b — the two rows the whole pass changed and
# should not have.
PRODUCTION_LINE = "nicht nach dem häufigen: „Senf-“, nicht „Korn“."
PRODUCTION_LIST_ITEM = (
    "<li><strong>Konkordanz</strong> — ein Wortverzeichnis mit einer Liste von Fundstellen. "
    "Suchen Sie nach dem seltenen Wort einer Phrase, nicht nach dem häufigen: „Senf-“, nicht „Korn“.</li>"
)
PRODUCTION_PARAGRAPH = (
    "<p>Sie erinnern sich nur an die Worte? Suchen Sie nach dem <strong>seltenen</strong> Wort "
    "aus dem Satz, nicht nach dem häufigen: „Senf-“, nicht „Korn“.</p>"
)


def _marks(text: str) -> list[str]:
    return [c for c in text if c in '«»„“”"']


class TestAHyphenEndingAWordDoesNotOpenAQuotation:
    def test_the_line_from_production_comes_back_exactly_as_written(self) -> None:
        assert normalize_typography(PRODUCTION_LINE, "de", content_kind="html") == PRODUCTION_LINE

    def test_the_list_item_it_was_found_in_is_untouched(self) -> None:
        # The em dash in this one is German's own parenthetical dash and
        # is already an en dash away from correct; what must not move is
        # the mark after ``Senf-``.
        once = normalize_typography(PRODUCTION_LIST_ITEM, "de", content_kind="html")
        assert _marks(once) == ["„", "“", "„", "“"]

    def test_the_paragraph_form_of_the_same_sentence_is_untouched_too(self) -> None:
        assert normalize_typography(PRODUCTION_PARAGRAPH, "de", content_kind="html") == PRODUCTION_PARAGRAPH

    def test_the_truncated_word_still_closes_when_the_marks_are_wrong_to_begin_with(self) -> None:
        # The mark has to be *written* as a closing one, not merely left
        # alone: a row that arrives from the model with straight quotes
        # is the ordinary case, and it must land on ``„Senf-“``.
        assert normalize_typography('nicht nach dem häufigen: "Senf-", nicht "Korn".', "de") == PRODUCTION_LINE

    @pytest.mark.parametrize("dash", ["-", "–", "—"])
    def test_any_dash_welded_to_the_word_before_it_closes(self, dash: str) -> None:
        text = f'Er nannte es "Senf{dash}" und ging.'
        assert _marks(normalize_typography(text, "de")) == ["„", "“"]

    def test_the_ukrainian_marks_behave_the_same_way(self) -> None:
        assert normalize_typography('шукайте "гірчич-", а не "зерно".', "uk") == "шукайте «гірчич-», а не «зерно»."


class TestWhatTheHyphenRuleMustNotBreak:
    """Every one of these worked before the change. The first is what
    the dash was in the opening set *for*, and is the guard the fix
    comes closest to breaking."""

    def test_a_dash_standing_free_still_opens_a_quotation(self) -> None:
        # The dialogue dash. This is the case the dash entries in
        # ``_OPENING_CONTEXT`` exist for, and the one a rule that simply
        # deleted them would lose.
        assert _marks(normalize_typography('— "Komm her", sagte er.', "de")) == ["„", "“"]

    def test_a_dash_at_the_very_start_of_the_string_still_opens_one(self) -> None:
        # Nothing at all before the dash reads as whitespace, because
        # the start of the text is a place a quotation may begin.
        assert _marks(normalize_typography('—"Komm her"', "de")) == ["„", "“"]

    def test_a_dash_opening_a_block_still_opens_a_quotation(self) -> None:
        # The block reset empties the character before the mark; it has
        # to empty the one before *that* as well, or the full stop that
        # ended the paragraph above reaches across the boundary and
        # makes the dialogue dash look welded to it.
        html = '<p>Vorher.</p><p>— "Komm her"</p>'
        assert _marks(normalize_typography(html, "de", content_kind="html")) == ["„", "“"]

    def test_a_dash_after_a_newline_still_opens_a_quotation(self) -> None:
        assert _marks(normalize_typography('Vorher.\n— "Komm her"', "de")) == ["„", "“"]

    def test_both_kinds_of_dash_in_one_sentence_are_told_apart(self) -> None:
        # The whole rule in one string: the free dash opens, the welded
        # one closes, and neither decision leaks into the other.
        text = '— "Senf-" ist der Stamm, sagte er.'
        assert normalize_typography(text, "de") == "– „Senf-“ ist der Stamm, sagte er."

    def test_the_verse_that_opens_a_block_still_gets_its_opening_mark(self) -> None:
        # The block-boundary reset from ``test_a_quotation_that_opens_a
        # _block``, re-asserted here because the fix touches the same
        # loop.
        html = "<p>Vorher.</p><blockquote>“Doch weil ihr an Christi Leiden teilhabt, freut euch.“</blockquote>"
        assert _marks(normalize_typography(html, "de", content_kind="html")) == ["„", "“"]

    def test_an_unbalanced_mark_after_a_hyphen_is_still_left_alone(self) -> None:
        # The odd-count guard is upstream of the opening test and stays
        # upstream: three marks cannot pair, so the string keeps every
        # one of them, hyphen or no hyphen.
        text = 'Das Brett ist 5" breit, das „Senf-“ Beispiel folgt.'
        assert normalize_typography(text, "de") == text

    def test_the_inch_mark_on_its_own_is_still_left_alone(self) -> None:
        assert normalize_typography('Das Brett ist 5" breit.', "de") == 'Das Brett ist 5" breit.'

    def test_english_is_unaffected_because_its_marks_are_the_same_character(self) -> None:
        text = 'Look for the rare word: "mustard-", not "seed".'
        assert normalize_typography(text, "en") == text

    def test_english_keeps_its_dash_before_a_quotation_too(self) -> None:
        assert normalize_typography('— "Come here"', "en") == '— "Come here"'

    @pytest.mark.parametrize(
        "text",
        [
            PRODUCTION_LINE,
            PRODUCTION_LIST_ITEM,
            PRODUCTION_PARAGRAPH,
            '— "Komm her", sagte er.',
            '— "Senf-" ist der Stamm.',
            '<p>Vorher.</p><p>— "Komm her"</p>',
        ],
    )
    def test_the_second_pass_changes_nothing(self, text: str) -> None:
        once = normalize_typography(text, "de", content_kind="html")
        assert normalize_typography(once, "de", content_kind="html") == once
