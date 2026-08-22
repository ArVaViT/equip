# ruff: noqa: RUF001, RUF002
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
        # Half a page of unrelated prose. Real citations put a clause
        # between reference and quotation, not a paragraph.
        filler = "Дальше идёт длинный абзац, который никак не связан с этой ссылкой. " * 6
        text = f"Ин. 3:16 — важный стих. {filler} А вот другая цитата: «{verse}»"

        _, subs = pre_substitute(text, "ru")

        assert subs == []

    def test_each_quotation_takes_the_nearest_reference(self):
        john = _verse("john", 3, 16, "ru")
        acts = _verse("acts", 1, 8, "ru")
        text = f"Ин. 3:16 говорит: «{john}» А в Деян. 1:8 сказано: «{acts}»"

        _, subs = pre_substitute(text, "ru")

        assert [sub.ref.book for sub in subs] == ["john", "acts"]

    def test_a_quotation_in_another_edition_is_still_that_verse(self):
        # The Daily Challenge generator quotes wording close to but not
        # identical with the bundled edition — 0.79 against KJV for
        # John 3:17, under the blockquote bar by a hair. Refusing there
        # means the German reader gets the English sentence, which is
        # the worse outcome by a wide margin.
        quoted = (
            "For God did not send his Son into the world to condemn the world, "
            "but in order that the world might be saved through him."
        )
        text = f"John 3:17 states, '{quoted}'"

        _, subs = pre_substitute(text, "en")

        assert len(subs) == 1

    def test_a_reference_inside_the_quotation_is_not_a_pairing(self):
        # «…слова из Ин. 3:16…» — the citation quoted along with the
        # verse, not a reference the quotation hangs off.
        text = "Он писал: «здесь идёт длинная цитата, где упомянут Ин. 3:16 внутри самой цитаты»"

        _, subs = pre_substitute(text, "ru")

        assert subs == []

    def test_prose_with_no_reference_is_untouched(self):
        text = "Он сказал: «Это очень длинная цитата, но она не из Писания вовсе»."

        markered, subs = pre_substitute(text, "ru")

        assert subs == []
        assert markered == text


class TestAnApostropheIsNotAClosingMark:
    """A double mark is closed by a double mark and a single mark by a
    single one. One pattern holding all of them in both classes reads
    ``…a centurion of Augustus' band."`` as a quotation that ends at the
    apostrophe, replaces the part in front of it with the whole verse,
    and leaves the two words behind the apostrophe to be translated on
    their own. Production, 2026-08-22, the Ukrainian explanation of
    Acts 27:1::

        «Як же присуджено, щоб плисти нам в Італию, то передано Павла і
        деяких инших вязників сотникові, на ймя Юлию, Августової роти.'
        загін»

    ``загін`` is "band". The German row of the same question ends
    ``…von der Schar des Augustus. Trupp.“``.
    """

    def test_a_possessive_does_not_close_a_quotation_a_double_mark_opened(self):
        verse = _verse("acts", 27, 1, "en")
        text = f'Acts 27:1 states, "{verse}" This identifies Julius.'

        markered, subs = pre_substitute(text, "en")

        assert len(subs) == 1
        assert subs[0].original_inner == verse
        assert "band" not in markered.replace(verse, "")

    def test_a_possessive_does_not_open_one_either(self):
        # ``Israel's oppression`` used to open a span that ran to the
        # next apostrophe in the paragraph.
        text = "Judges 6:1 explains Israel's oppression, and the reader's attention is drawn to it."

        markered, subs = pre_substitute(text, "en")

        assert subs == []
        assert markered == text

    def test_a_possessive_inside_a_single_quoted_verse_stays_inside_it(self):
        verse = _verse("genesis", 12, 1, "en")
        assert "father's" in verse
        text = f"Genesis 12:1 states, '{verse}' This verse outlines the command."

        _markered, subs = pre_substitute(text, "en")

        assert [sub.original_inner for sub in subs] == [verse]


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
