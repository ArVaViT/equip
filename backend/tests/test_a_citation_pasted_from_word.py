"""A verse quoted in Word and pasted into a lesson.

Word leaves two marks on a citation that the substitution layer did not
survive until 2026-09-05, both confirmed against the real ``pre_substitute``
on the day the first live teacher's course was due:

* The space between the book and the chapter is non-breaking, and the
  editor stores that character as the entity ``&nbsp;``. The reference
  regex asked for ``\\s+`` there, so ``Ин.&nbsp;3:16`` was not a citation
  at all — the canonical verse was never substituted, and the model was
  left to re-word Scripture, the one thing this layer exists to prevent.
* A citation the author set in bold — ``<strong>(Ин. 3:16)</strong>`` —
  lost its opening tag to the marker: the walk back from the book name
  stopped at the ``(`` and left ``<strong>`` in the verse text. Source
  ``strong`` × 2, translation ``strong`` × 1; the validator parked the
  row as ``markup_mismatch`` and the course stayed ``publishing``.

The markup below is TipTap's own: a blockquote holding one paragraph.
"""

from __future__ import annotations

import re

import pytest

from app.services.bible.references import BibleRef, parse_references
from app.services.bible.store import lookup, reset_cache
from app.services.bible.substitution import post_substitute, pre_substitute


@pytest.fixture(autouse=True)
def _reset_bible_cache():
    reset_cache()
    yield
    reset_cache()


def _tags(html: str) -> list[str]:
    """The tag list the translation validator compares — names only, in order."""
    return [m.group(1).lower() for m in re.finditer(r"<(/?[a-zA-Z][a-zA-Z0-9]*)", html)]


def _john_3_16() -> tuple[str, str]:
    ru = lookup(BibleRef("john", 3, 16), "ru")
    en = lookup(BibleRef("john", 3, 16), "en")
    assert ru and en
    return ru, en


class TestTheNonBreakingSpaceWordPuts:
    @pytest.mark.parametrize(
        "written",
        [
            "Ин.&nbsp;3:16",
            "Ин.&#160;3:16",
            "Ин.&#xa0;3:16",
            "Ин.\xa03:16",
        ],
    )
    def test_between_book_and_chapter(self, written: str) -> None:
        parsed = parse_references(written, "ru")
        assert [p.ref for p in parsed] == [BibleRef("john", 3, 16)]
        # The span covers what the author wrote, entity and all — that is
        # what gets rewritten into the target locale later.
        assert parsed[0].raw_text == written

    def test_inside_a_numbered_book_name(self) -> None:
        # Russian typography puts the non-breaking space between the
        # number and the name too, and Word obliges.
        parsed = parse_references("1&nbsp;Кор.&nbsp;13:4", "ru")
        assert [p.ref for p in parsed] == [BibleRef("1corinthians", 13, 4)]

    def test_around_the_range_dash(self) -> None:
        parsed = parse_references("1&nbsp;Кор.&nbsp;13:4&nbsp;–&nbsp;7", "ru")
        assert [p.ref for p in parsed] == [BibleRef("1corinthians", 13, 4, 7)]

    def test_a_plain_space_still_works(self) -> None:
        assert [p.ref for p in parse_references("Ин. 3:16", "ru")] == [BibleRef("john", 3, 16)]

    def test_the_verse_is_substituted(self) -> None:
        ru, en = _john_3_16()
        html = f"<blockquote><p>«{ru}» (Ин.&nbsp;3:16)</p></blockquote>"
        markered, subs = pre_substitute(html, "ru")
        assert [s.ref for s in subs] == [BibleRef("john", 3, 16)]
        assert ru not in markered
        final = post_substitute(markered, subs, "en")
        assert en in final
        assert "(John 3:16)" in final

    def test_the_verse_text_itself_may_carry_them(self) -> None:
        # Word does the same inside the quotation. The similarity ratio
        # is measured on the words, not on how the spaces were spelled.
        ru, en = _john_3_16()
        html = f"<blockquote><p>«{ru.replace(' ', '&nbsp;')}» (Ин.&nbsp;3:16)</p></blockquote>"
        markered, subs = pre_substitute(html, "ru")
        assert [s.ref for s in subs] == [BibleRef("john", 3, 16)]
        assert en in post_substitute(markered, subs, "en")


class TestACitationSetInBold:
    def test_bold_around_the_parentheses(self) -> None:
        ru, en = _john_3_16()
        html = f"<blockquote><p>«{ru}» <strong>(Ин. 3:16)</strong></p></blockquote>"
        markered, subs = pre_substitute(html, "ru")
        assert len(subs) == 1
        assert _tags(markered) == _tags(html)
        assert "<strong>(Ин. 3:16)</strong>" in markered
        final = post_substitute(markered, subs, "en")
        assert _tags(final) == _tags(html)
        assert f'"{en}" <strong>(John 3:16)</strong>' in final

    def test_bold_inside_the_parentheses(self) -> None:
        ru, en = _john_3_16()
        html = f"<blockquote><p>«{ru}» (<strong>Ин. 3:16</strong>)</p></blockquote>"
        markered, subs = pre_substitute(html, "ru")
        assert len(subs) == 1
        assert _tags(markered) == _tags(html)
        final = post_substitute(markered, subs, "en")
        assert _tags(final) == _tags(html)
        assert f'"{en}" (<strong>John 3:16</strong>)' in final

    def test_the_marker_still_gets_its_space_before_a_bold_tail(self) -> None:
        # The author's ``» <strong>`` had a space; the marker swallows
        # the verse text and its trailing whitespace, and the tail must
        # not be glued to the verse — that read as ``…life.<strong>(``.
        ru, _ = _john_3_16()
        html = f"<blockquote><p>«{ru}» <strong>(Ин. 3:16)</strong></p></blockquote>"
        markered, subs = pre_substitute(html, "ru")
        assert f"{subs[0].marker} <strong>(Ин. 3:16)</strong>" in markered

    def test_an_unbolded_citation_is_unchanged_by_the_fix(self) -> None:
        ru, en = _john_3_16()
        html = f"<blockquote><p>«{ru}» (Ин. 3:16).</p></blockquote>"
        markered, subs = pre_substitute(html, "ru")
        assert len(subs) == 1
        assert _tags(markered) == _tags(html)
        assert f'"{en}" (John 3:16).' in post_substitute(markered, subs, "en")
