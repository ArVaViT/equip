# ruff: noqa: RUF001, RUF002
"""A verse in its own blockquote came back with two closing marks.

Found by reading production, not by a check. A walkthrough on 2026-08-20
served German `“Doch weil ihr an Christi Leiden teilhabt…habt.“` and
Ukrainian `»А як ви берете участь…веселитися»` — the closing mark at both
ends, in both languages, on the one line of a Bible lesson that is
Scripture rather than commentary.

The cause is that markup is transparent to the opening test, which is
right inside a paragraph and wrong across one. A `<blockquote>` opening
a quotation is preceded, in prose terms, by the full stop that ended the
paragraph above. A full stop closes. So the mark that opened the
quotation was written as a closing mark, and so was the one that closed
it — and a string with two closing marks reads as balanced, so nothing
downstream objected.

What made it visible was the contrast: the same sentence inside a
paragraph came back correctly pointed. Two shapes of one quotation,
decided by which side of a `</p>` it fell on.
"""

from __future__ import annotations

import pytest

from app.services.translation.typography import normalize_typography

DE_BLOCK = "<p>Vorher.</p><blockquote>“Doch weil ihr an Christi Leiden teilhabt, freut euch.“</blockquote>"
UK_BLOCK = "<p>Раніше.</p><blockquote>»А як ви берете участь у Христових стражданнях, радійте»</blockquote>"


def _marks(text: str) -> list[str]:
    return [c for c in text if c in '«»„“”"']


class TestAQuotationThatOpensABlock:
    def test_the_german_verse_from_production_gets_its_opening_mark(self) -> None:
        assert _marks(normalize_typography(DE_BLOCK, "de", content_kind="html")) == ["„", "“"]

    def test_the_ukrainian_verse_from_production_gets_its_opening_mark(self) -> None:
        assert _marks(normalize_typography(UK_BLOCK, "uk", content_kind="html")) == ["«", "»"]

    @pytest.mark.parametrize(
        "opener",
        ["<blockquote>", "<p>", "<li>", "<h3>", "<td>", "<div>"],
    )
    def test_any_block_is_a_fresh_place_to_start(self, opener: str) -> None:
        """Not just blockquote. A quotation opening a list item or a
        table cell is in the same position and was read the same way."""
        closer = f"</{opener[1:-1]}>"
        html = f"<p>Vorher.</p>{opener}“Geht hin“{closer}"
        assert _marks(normalize_typography(html, "de", content_kind="html")) == ["„", "“"]

    def test_a_quotation_inside_a_paragraph_is_unaffected(self) -> None:
        """The case that already worked, pinned so the fix cannot be a
        trade — this is what made the defect visible in the first place."""
        html = "<p>Er sagte: “Geht hin“ und ging.</p>"
        assert _marks(normalize_typography(html, "de", content_kind="html")) == ["„", "“"]


class TestWhatTheResetMustNotBreak:
    def test_a_quotation_that_closes_across_a_block_still_closes(self) -> None:
        """A quotation that opens in one paragraph and closes in the next
        keeps its closing mark closing. The reset says "a new block can
        begin a quotation", not "every mark after a block opens one" —
        the balance of the pair still decides."""
        html = "<p>Er sagte: „Geht hin</p><p>und kommt wieder.“</p>"
        assert _marks(normalize_typography(html, "de", content_kind="html")) == ["„", "“"]

    def test_an_already_correct_string_is_a_fixed_point(self) -> None:
        """Run twice, land in the same place — the property the module
        is built on, re-asserted across a block boundary."""
        html = "<p>Vorher.</p><blockquote>„Geht hin“</blockquote>"
        once = normalize_typography(html, "de", content_kind="html")
        assert once == html
        assert normalize_typography(once, "de", content_kind="html") == once

    def test_an_inch_mark_after_a_block_is_still_left_alone(self) -> None:
        """The odd-count guard is upstream of this and stays upstream:
        a lone mark cannot pair, so the string keeps every mark it has,
        block boundary or not."""
        html = '<p>Vorher.</p><p>Das Brett ist 5" breit.</p>'
        assert normalize_typography(html, "de", content_kind="html") == html

    def test_english_is_unchanged_because_its_marks_are_the_same_character(self) -> None:
        """English cannot get an opening mark backwards — both ends are
        U+0022 — so the reset must be a no-op there rather than a second
        rule with its own behaviour."""
        html = '<p>Before.</p><blockquote>"Go therefore"</blockquote>'
        assert _marks(normalize_typography(html, "en", content_kind="html")) == ['"', '"']
