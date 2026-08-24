"""The paragraph the editor puts inside a blockquote, and the marker that ate it.

A teacher presses the quote button, types a verse, and saves. TipTap
declares blockquote as ``content: "block+"``, so what reaches the API is

    <blockquote><p>Der HERR ist mein Hirte, mir wird nichts mangeln.</p></blockquote>

``pre_substitute`` replaces the blockquote's *inner* with a marker, and
that inner is the whole paragraph. The canonical verse is pasted back
bare, the translation ends up with one fewer paragraph than the source,
and ``validation._check_tags`` parks the row. In every target language.
On every retry — because the translation is right and only the shape is
wrong, so asking again produces the same answer.

Measured on production, 2026-08-24: two blocks quoting Psalm 23:1 in one
chapter, one with the wrapper and one without. The first parked in ru,
uk and en; the second came back translated with the reference renumbered
to «Пс. 22:1». Nothing else about them differed.

Why it had not been seen: the eighteen blockquotes in the live courses
carry no wrapper, because those courses were seeded by script rather
than typed into the editor.

Two shapes, two answers. One wrapper around the whole quotation is set
aside and put back, because that is provably the same document. More
structure than that — two verses as two paragraphs, a list, a nested
quote — declines the substitution entirely: the marker replaces one
span, so anything else would be flattened. The reader then gets the
model's rendering instead of the edition's, which is the trade this
layer already makes everywhere the canonical text cannot be had, and it
is a far smaller loss than a lesson that never publishes.
"""

from __future__ import annotations

import re

import pytest

from app.services.bible.substitution import _peel_wrapper, pre_substitute

_VERSE = "Der HERR ist mein Hirte, mir wird nichts mangeln."


def _tags(html: str) -> list[str]:
    return sorted(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", html))


class TestPeelingTheWrapper:
    def test_a_lone_paragraph_comes_apart_in_three_pieces(self) -> None:
        assert _peel_wrapper("<p>verse</p>") == ("<p>", "verse", "</p>")

    def test_attributes_travel_with_the_opening_tag(self) -> None:
        """A class on the paragraph is the author's, and putting the tag
        back without it would be a different document."""
        assert _peel_wrapper('<p class="lead">verse</p>') == ('<p class="lead">', "verse", "</p>")

    def test_a_div_is_a_wrapper_too(self) -> None:
        assert _peel_wrapper("<div>verse</div>") == ("<div>", "verse", "</div>")

    def test_bare_text_has_nothing_to_peel(self) -> None:
        assert _peel_wrapper("verse") == ("", "verse", "")

    def test_two_paragraphs_are_not_one_wrapper(self) -> None:
        """Greedy matching would read these as one ``<p>`` holding
        ``one</p><p>two``, and putting *that* back is not the document
        the author wrote."""
        assert _peel_wrapper("<p>one</p><p>two</p>") == ("", "<p>one</p><p>two</p>", "")

    def test_a_nested_paragraph_is_not_one_wrapper(self) -> None:
        assert _peel_wrapper("<p>outer <p>inner</p></p>") == ("", "<p>outer <p>inner</p></p>", "")

    def test_inline_markup_inside_is_left_where_it_is(self) -> None:
        assert _peel_wrapper("<p>the <strong>LORD</strong></p>") == ("<p>", "the <strong>LORD</strong>", "</p>")

    def test_what_comes_apart_goes_back_together(self) -> None:
        for inner in ("<p>verse</p>", "verse", "<p>one</p><p>two</p>", '<div class="x">verse</div>'):
            assert "".join(_peel_wrapper(inner)) == inner


class TestTheMarkerLeavesTheStructureAlone:
    @pytest.mark.parametrize(
        "html",
        [
            f"<h3>A</h3><blockquote><p>{_VERSE}</p></blockquote><p>(Psalm 23,1)</p>",
            f"<h3>A</h3><blockquote>{_VERSE}</blockquote><p>(Psalm 23,1)</p>",
            f'<blockquote class="q"><p>{_VERSE}</p></blockquote><p>(Psalm 23,1)</p>',
            f"<blockquote><p>{_VERSE} (Psalm 23,1)</p></blockquote>",
            "<blockquote><p>Der HERR ist mein Hirte.</p><p>Mir wird nichts mangeln.</p></blockquote><p>(Psalm 23,1)</p>",
        ],
    )
    def test_the_markered_html_has_the_tags_the_source_had(self, html: str) -> None:
        """The marker stands where the verse stood and nowhere else.

        Asserted on ``pre_substitute``'s own output rather than on a
        round trip, so it holds with or without a key in the
        environment: without one nothing substitutes, and the text comes
        back untouched, which satisfies this too.
        """
        markered, _subs = pre_substitute(html, "de")
        assert _tags(markered) == _tags(html)

    def test_a_quotation_of_two_paragraphs_is_declined_rather_than_flattened(self) -> None:
        """The one shape that cannot be preserved is refused outright.
        Without a key nothing substitutes anyway, so this asserts the
        thing that is true either way: the document is unchanged."""
        html = (
            "<blockquote><p>Der HERR ist mein Hirte.</p><p>Mir wird nichts mangeln.</p></blockquote><p>(Psalm 23,1)</p>"
        )
        markered, subs = pre_substitute(html, "de")
        assert subs == []
        assert markered == html
