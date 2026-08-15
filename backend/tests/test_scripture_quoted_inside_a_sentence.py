# ruff: noqa: RUF001
# Russian prose fixtures; single Cyrillic letters are words here.
"""A verse quoted mid-sentence is still a verse.

The substitution layer only ever looked at ``<blockquote>``. Everything
else went to the model as ordinary prose, and the system prompt tells
the model — correctly — to leave quoted Scripture untouched rather than
recite it from memory. Between the two rules, a quotation that was not
in a blockquote survived the translation in its original language.

With two languages that was almost invisible: an English verse inside
Russian prose looks like a citation. With German it is simply an
untranslated sentence. Production, 2026-08-15, a Daily Challenge
explanation translated into German:

    Johannes 3:17 besagt: 'For God did not send his Son into the
    world to condemn the world, but in order that the world…'

German sentence, English verse, and the reference not localized either.
The Daily Challenge explanations are the worst case — they quote
constantly and carry no markup at all for a blockquote to live in.

These tests pin the fix: a quotation next to a reference is recognised
wherever it sits, and it is replaced with the target edition's own
words rather than translated or left behind.
"""

from __future__ import annotations

import pytest

from app.services.bible.references import BibleRef
from app.services.bible.store import lookup
from app.services.bible.substitution import post_substitute, pre_substitute


def _verse(book: str, chapter: int, verse: int, locale: str) -> str:
    text = lookup(BibleRef(book, chapter, verse), locale)
    assert text is not None, f"{book} {chapter}:{verse} missing from the {locale} bundle"
    return text


class TestTheQuoteIsFound:
    def test_when_the_reference_introduces_it(self):
        verse = _verse("john", 3, 16, "ru")
        text = f"Ин. 3:16 говорит: «{verse}» — это сердце Евангелия."

        markered, subs = pre_substitute(text, "ru")

        assert len(subs) == 1
        assert verse not in markered
        assert subs[0].marker in markered

    def test_when_the_reference_follows_it(self):
        verse = _verse("john", 3, 16, "en")
        text = f'The centre of the gospel: "{verse}" (John 3:16).'

        markered, subs = pre_substitute(text, "en")

        assert len(subs) == 1
        assert verse not in markered

    def test_a_paraphrase_is_left_alone(self):
        # The author's own words are the author's own words. Replacing a
        # paraphrase with the edition would put words in their mouth.
        text = "Ин. 3:16 говорит, что Бог по любви отдал Сына ради спасения мира."

        markered, subs = pre_substitute(text, "ru")

        assert subs == []
        assert markered == text

    def test_a_quotation_far_from_the_reference_is_not_claimed_by_it(self):
        verse = _verse("john", 3, 16, "ru")
        filler = "Дальше идёт длинный абзац, который никак не связан с этой ссылкой. " * 3
        text = f"Ин. 3:16 — важный стих. {filler} А вот другая цитата: «{verse}»"

        _, subs = pre_substitute(text, "ru")

        assert subs == []

    def test_prose_with_no_reference_is_untouched(self):
        text = "Он сказал: «Это очень длинная цитата, но она не из Писания вовсе»."

        markered, subs = pre_substitute(text, "ru")

        assert subs == []
        assert markered == text


class TestTheReaderGetsTheirOwnEdition:
    def test_the_verse_arrives_in_the_target_language(self):
        russian = _verse("john", 3, 16, "ru")
        english = _verse("john", 3, 16, "en")
        text = f"Ин. 3:16 говорит: «{russian}»"

        markered, subs = pre_substitute(text, "ru")
        final = post_substitute(markered, subs, "en")

        assert english in final
        assert russian not in final

    def test_the_reference_is_localized_with_it(self):
        russian = _verse("john", 3, 16, "ru")
        text = f"Ин. 3:16 говорит: «{russian}»"

        markered, subs = pre_substitute(text, "ru")
        final = post_substitute(markered, subs, "en")

        assert "John 3:16" in final
        assert "Ин. 3:16" not in final

    def test_a_target_the_platform_cannot_look_up_keeps_the_author(self):
        # No API key in tests, so German resolves to nothing. The
        # author's own quotation survives — honestly odd beats silently
        # wrong, the same rule the blockquote path has always followed.
        russian = _verse("john", 3, 16, "ru")
        text = f"Ин. 3:16 говорит: «{russian}»"

        markered, subs = pre_substitute(text, "ru")
        final = post_substitute(markered, subs, "de")

        assert russian in final
        assert subs[0].marker not in final


class TestBothShapesInOneDocument:
    def test_a_blockquote_and_an_inline_quote_are_both_replaced(self):
        acts = _verse("acts", 1, 8, "ru")
        john = _verse("john", 3, 16, "ru")
        html = f"<blockquote>«{acts}» (Деян. 1:8).</blockquote><p>И ещё: Ин. 3:16 говорит: «{john}»</p>"

        markered, subs = pre_substitute(html, "ru")

        assert len(subs) == 2
        assert acts not in markered
        assert john not in markered

    def test_the_markers_are_independent(self):
        acts = _verse("acts", 1, 8, "ru")
        john = _verse("john", 3, 16, "ru")
        html = f"<blockquote>«{acts}» (Деян. 1:8).</blockquote><p>И ещё: Ин. 3:16 говорит: «{john}»</p>"

        markered, subs = pre_substitute(html, "ru")
        final = post_substitute(markered, subs, "en")

        assert _verse("acts", 1, 8, "en") in final
        assert _verse("john", 3, 16, "en") in final


class TestTheMarkerNeverReachesAReader:
    @pytest.mark.parametrize("target", ["en", "ru", "de", "uk"])
    def test_no_marker_survives_post_substitute(self, target: str):
        verse = _verse("john", 3, 16, "ru")
        text = f"Ин. 3:16 говорит: «{verse}»"

        markered, subs = pre_substitute(text, "ru")
        final = post_substitute(markered, subs, target)

        assert "VERSE_" not in final
