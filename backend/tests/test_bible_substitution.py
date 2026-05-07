"""Tests for the Bible canonical-text substitution module.

The module's contract: when the translation pipeline gets a piece of
HTML from a teacher who quoted Scripture (RU or EN), the canonical
target-locale verse text should land in the translation — KJV English
for ``en``, Synodal Russian for ``ru``. When the author paraphrased
(similarity below 0.80), the substitution stays out of the way and the
existing "leave verse text untouched" prompt rule applies.
"""

from __future__ import annotations

import pytest

from app.services.bible.books import all_canonical_slugs, find_book
from app.services.bible.references import BibleRef, parse_references
from app.services.bible.store import is_locale_bundled, lookup, reset_cache
from app.services.bible.substitution import (
    Substitution,
    post_substitute,
    pre_substitute,
)


@pytest.fixture(autouse=True)
def _reset_bible_cache():
    reset_cache()
    yield
    reset_cache()


# ---------------------------------------------------------------------------
# books.py
# ---------------------------------------------------------------------------


def test_find_book_recognizes_acts_short_and_long_forms():
    assert find_book("Acts") == "acts"
    assert find_book("acts.") == "acts"
    assert find_book("Деян.") == "acts"
    assert find_book("Деяния") == "acts"
    assert find_book("Деяния Апостолов") == "acts"


def test_find_book_recognizes_numeric_prefix_books():
    assert find_book("1 Cor.") == "1corinthians"
    assert find_book("1 Кор.") == "1corinthians"
    assert find_book("2 Тим.") == "2timothy"
    assert find_book("3 John") == "3john"


def test_find_book_returns_none_for_unknown():
    assert find_book("Encyclopedia") is None
    assert find_book("") is None


def test_canon_lists_66_books():
    assert len(all_canonical_slugs()) == 66
    assert "acts" in all_canonical_slugs()
    assert "revelation" in all_canonical_slugs()


# ---------------------------------------------------------------------------
# references.py
# ---------------------------------------------------------------------------


def test_parse_acts_1_8_single_verse():
    refs = parse_references("See Acts 1:8 for the program.")
    assert len(refs) == 1
    assert refs[0].ref == BibleRef(book="acts", chapter=1, verse_start=8)


def test_parse_acts_1_8_to_10_range():
    refs = parse_references("Read Acts 1:8-10 carefully.")
    assert len(refs) == 1
    assert refs[0].ref == BibleRef(book="acts", chapter=1, verse_start=8, verse_end=10)


def test_parse_russian_short_form():
    refs = parse_references("Цитата (Деян. 20:28) важна.")
    assert len(refs) == 1
    assert refs[0].ref == BibleRef(book="acts", chapter=20, verse_start=28)


def test_parse_russian_long_form():
    refs = parse_references("Деяния Апостолов 1:8 — программа книги.")
    assert len(refs) == 1
    assert refs[0].ref.book == "acts"
    assert refs[0].ref.chapter == 1
    assert refs[0].ref.verse_start == 8


def test_parse_skips_unknown_book_words():
    # "Verse 1:8" is not a Bible book — must not produce a match.
    assert parse_references("Verse 1:8 of the song") == []


def test_parse_dotseparated_chapter_verse():
    refs = parse_references("In Acts 1.8 we read…")
    assert len(refs) == 1
    assert refs[0].ref.verse_start == 8


def test_parse_drops_inverted_range():
    # 10-8 is meaningless — drop it (likely a non-Bible match).
    assert parse_references("see Acts 1:10-8 hmm") == []


def test_parse_returns_position_span_for_substitution():
    text = "Read Acts 1:8 today."
    refs = parse_references(text)
    assert len(refs) == 1
    start, end = refs[0].span
    assert text[start:end] == "Acts 1:8"


# ---------------------------------------------------------------------------
# store.py
# ---------------------------------------------------------------------------


def test_is_locale_bundled():
    assert is_locale_bundled("ru")
    assert is_locale_bundled("en")


def test_lookup_acts_1_8_kjv_returns_canonical_en():
    text = lookup(BibleRef("acts", 1, 8), "en")
    assert text is not None
    assert "ye shall receive power" in text.lower()
    assert "uttermost part of the earth" in text.lower()


def test_lookup_acts_1_8_synodal_returns_canonical_ru():
    text = lookup(BibleRef("acts", 1, 8), "ru")
    assert text is not None
    assert "примете силу" in text.lower()
    assert "до края земли" in text.lower()


def test_lookup_range_joins_verses():
    text = lookup(BibleRef("john", 3, 16, 17), "en")
    assert text is not None
    assert "everlasting life" in text.lower()  # v16
    assert "might be saved" in text.lower()  # v17 — KJV phrasing


def test_lookup_returns_none_for_missing_verse():
    # Acts has 28 chapters; chapter 99 doesn't exist.
    assert lookup(BibleRef("acts", 99, 1), "en") is None


def test_lookup_unbundled_locale_returns_none():
    # ``uk`` is not in the bundled set; type checker would flag it but
    # the runtime path handles it.
    assert lookup(BibleRef("acts", 1, 8), "uk") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# substitution.py
# ---------------------------------------------------------------------------


def test_pre_substitute_canonical_synodal_quote_replaced_with_marker():
    """A blockquote whose text is the Synodal canonical, followed by a
    parenthesized reference, gets its inner text swapped for a marker."""
    canonical_ru = lookup(BibleRef("acts", 1, 8), "ru")
    assert canonical_ru is not None
    html = f"<p>Programa knigi:</p><blockquote>«{canonical_ru}»</blockquote><p> (Деян. 1:8). Это центральный стих.</p>"
    out, subs = pre_substitute(html, "ru")
    assert len(subs) == 1
    assert subs[0].ref == BibleRef("acts", 1, 8)
    # Marker is in the output; original verse text is gone.
    assert subs[0].marker in out
    assert "примете силу" not in out
    # The parenthesized reference itself is preserved.
    assert "(Деян. 1:8)" in out


def test_pre_substitute_paraphrase_left_alone():
    """An author-paraphrased quote (low similarity) should NOT be
    marker-substituted — the existing 'leave verse untouched' prompt
    rule remains in charge for those."""
    html = "<blockquote>«Идите по всему миру и говорите всем людям обо Мне»</blockquote> (Деян. 1:8)"
    out, subs = pre_substitute(html, "ru")
    assert subs == []
    assert out == html


def test_pre_substitute_no_reference_left_alone():
    canonical_ru = lookup(BibleRef("acts", 1, 8), "ru")
    assert canonical_ru is not None
    html = f"<blockquote>{canonical_ru}</blockquote><p>Без ссылки на главу.</p>"
    out, subs = pre_substitute(html, "ru")
    assert subs == []
    assert out == html


def test_post_substitute_replaces_marker_with_target_canonical():
    """End-to-end: marker token put in by pre_substitute is replaced
    by the target-locale canonical text in post_substitute."""
    sub = Substitution(
        marker="VERSE_test1234",
        ref=BibleRef("acts", 1, 8),
        original_inner="но вы примете силу…",
    )
    translated = (
        "<p>Program of the book:</p>"
        "<blockquote>«VERSE_test1234»</blockquote>"
        "<p> (Acts 1:8). This is the central verse.</p>"
    )
    out = post_substitute(translated, [sub], "en")
    assert "ye shall receive power" in out.lower()
    # No leftover marker remains in the rendered page.
    assert "VERSE_test1234" not in out


def test_post_substitute_falls_back_to_source_when_target_missing():
    """If the target locale lookup misses (exotic verse not in the
    bundled file), fall back to the original source text rather than
    leaving a raw marker in the rendered page."""
    sub = Substitution(
        marker="VERSE_falls_back",
        ref=BibleRef("acts", 99, 1),  # nonexistent
        original_inner="оригинальный текст",
    )
    out = post_substitute("Body VERSE_falls_back end.", [sub], "en")
    assert out == "Body оригинальный текст end."


def test_marker_survives_postgres_text_column():
    """Postgres TEXT rejects NUL bytes outright; the v1 marker used
    \\x00 fences and the verse text leaked into production. Guard the
    invariant: produced markers must contain no NUL bytes (and no other
    Postgres-forbidden control chars)."""
    from app.services.bible.substitution import _marker_token

    for _ in range(50):
        marker = _marker_token()
        assert "\x00" not in marker, "NUL marker would be stripped by Postgres TEXT"
        # ASCII-printable only is a stronger invariant — keeps logs and
        # diff tools happy without further escaping.
        assert marker.isascii() and marker.isprintable(), marker


def test_full_roundtrip_synodal_to_kjv():
    """The headline scenario: teacher writes Russian Synodal in a
    blockquote, student reads in EN — they should see KJV English in
    place of the Russian source."""
    canonical_ru = lookup(BibleRef("acts", 1, 8), "ru")
    canonical_en = lookup(BibleRef("acts", 1, 8), "en")
    assert canonical_ru and canonical_en
    source_html = f"<p>Программа книги Деяний:</p><blockquote>«{canonical_ru}»</blockquote><p>(Деян. 1:8). Это план."

    markered, subs = pre_substitute(source_html, "ru")
    assert len(subs) == 1

    # In the real pipeline, ``markered`` is sent to Gemini for ru→en.
    # Here we mock the translator: keep the marker, translate the
    # surrounding text. This checks that markers survive a Gemini-like
    # round-trip with prose changes around them.
    translated_html = markered.replace("Программа книги Деяний:", "Programme of the book of Acts:").replace(
        "Это план.", "This is the plan."
    )

    final = post_substitute(translated_html, subs, "en")
    assert canonical_en in final
    assert canonical_ru not in final
    assert "VERSE_" not in final


def test_pre_substitute_reference_inside_blockquote():
    """Real-world Synodal-style citation: the parenthesized reference
    sits at the end of the blockquote text (not after the closing tag).
    Substitution must still detect, replace the verse text with a
    marker, and preserve the citation tail so the reader still sees
    ``(Acts 20:28)`` next to the canonical English verse.
    """
    canonical_ru = lookup(BibleRef("acts", 20, 28), "ru")
    assert canonical_ru is not None
    html = f"<blockquote>«{canonical_ru}» (Деян. 20:28).</blockquote>\n<p>Это пастырское наставление.</p>"
    out, subs = pre_substitute(html, "ru")
    assert len(subs) == 1
    assert subs[0].ref == BibleRef("acts", 20, 28)
    # Russian verse text is gone, but the reference notation stays.
    assert "пасти Церковь" not in out
    assert "(Деян. 20:28)" in out


def test_full_roundtrip_synodal_with_reference_inside():
    """End-to-end: author wrote Synodal with citation inside the
    blockquote → student in EN sees KJV with the (Acts ...) marker
    surviving Gemini's locale transformation of the book name."""
    canonical_ru = lookup(BibleRef("acts", 20, 28), "ru")
    canonical_en = lookup(BibleRef("acts", 20, 28), "en")
    assert canonical_ru and canonical_en
    source_html = f"<blockquote>«{canonical_ru}» (Деян. 20:28).</blockquote>"
    markered, subs = pre_substitute(source_html, "ru")
    assert len(subs) == 1
    # Mock Gemini: localize the citation prefix the way it really does.
    translated = markered.replace("Деян.", "Acts")
    final = post_substitute(translated, subs, "en")
    assert canonical_en in final
    assert canonical_ru not in final
    assert "(Acts 20:28)" in final


def test_full_roundtrip_kjv_to_synodal():
    """Inverse direction — author wrote KJV, student reads RU."""
    canonical_en = lookup(BibleRef("acts", 1, 8), "en")
    canonical_ru = lookup(BibleRef("acts", 1, 8), "ru")
    assert canonical_en and canonical_ru
    source_html = (
        f"<p>Programme of the Book of Acts:</p>"
        f"<blockquote>{canonical_en}</blockquote>"
        f"<p>(Acts 1:8). This is the central verse."
    )
    markered, subs = pre_substitute(source_html, "en")
    assert len(subs) == 1
    final = post_substitute(markered, subs, "ru")
    assert canonical_ru in final
    assert canonical_en not in final
