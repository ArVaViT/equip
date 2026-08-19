"""A corrupt bundle must behave like a missing one, never like a quotation.

`synodal-ru.json` ships misaligned: its book slugs have shifted, so
`romans.1.1` returns James, `jude.1.1` returns Hebrews, `3john.1.1` returns
Philemon, and eight books are absent. Verified on this checkout — 24 of 66
books disagree with the English bundle on verse count.

`post_substitute` inserts whatever `lookup` returns directly into a student's
blockquote. So before this guard, a Russian rendering of an English-authored
lesson quoting Romans 1:1 printed James 1:1 — silently, with no error, in a
Bible school. That is not a broken page; it is a confident false statement
about Scripture, which is the worst thing this product can say.

The guard does not repair the data. It makes a corrupt book indistinguishable
from a missing one, and missing is already safe: the caller falls back to the
author's own quotation, which was right to begin with.
"""

from __future__ import annotations

from app.services.bible.api_source import API_BIBLE_IDS, TRUSTED_BUNDLE_LOCALES
from app.services.bible.references import BibleRef
from app.services.bible.store import lookup
from app.services.bible.substitution import post_substitute


def _ref(book: str, chapter: int, verse: int) -> BibleRef:
    return BibleRef(book=book, chapter=chapter, verse_start=verse, verse_end=None)


def test_the_bundle_really_is_misaligned() -> None:
    # The premise, checked rather than asserted: each of these returns another
    # book's text. If this ever stops being true the bundle was fixed, and the
    # guard below should go with it.
    assert "Филимону" in (lookup(_ref("3john", 1, 1), "ru") or "")
    assert "Иаков" in (lookup(_ref("romans", 1, 1), "ru") or "")


def test_a_corrupt_quote_never_reaches_a_student() -> None:
    from app.services.bible.references import BibleRef
    from app.services.bible.substitution import Substitution

    sub = Substitution(
        marker="@@BIBLE_0@@",
        ref=BibleRef(book="romans", chapter=1, verse_start=1, verse_end=None),
        original_inner="Paul, a servant of Jesus Christ",
        ref_tail="",
    )
    out = post_substitute("<blockquote>@@BIBLE_0@@</blockquote>", [sub], "ru")

    # James must not appear where the lesson said Romans.
    assert "Иаков" not in out
    assert "Paul, a servant of Jesus Christ" in out


def test_english_is_unaffected() -> None:
    # The English bundle is the reference and must keep working, or the guard
    # has quietly turned Scripture substitution off for everybody.
    assert lookup(_ref("john", 3, 16), "en") is not None
    assert lookup(_ref("romans", 1, 1), "en") is not None


def test_the_corrupt_bundle_is_bypassed_entirely_for_russian() -> None:
    # The first guard compared verse counts per book. It caught `romans` and
    # missed `jude`, `3john` and `1kings`, because a shifted slug can land on a
    # book of the same length. Structure cannot detect this; only content can.
    # There is no honest way to certify any book in a file whose slugs moved.
    assert "ru" in API_BIBLE_IDS
    assert "ru" in API_BIBLE_IDS


def test_every_locale_reads_scripture_from_somewhere_defensible() -> None:
    # Why each locale is on the API path: `ru` because its bundle is
    # misaligned, `de` and `uk` because no bundle exists at all, and `en`
    # because its bundle — sound and complete — is the King James Version.
    # An editor reading the corpus found `spake`, `saith`, `unto` and `thee`
    # in 80 of 252 English explanations: Early Modern English quoted inside
    # a product whose every other sentence is contemporary. A file being
    # correct is not the same as it being the right book.
    assert set(API_BIBLE_IDS) == {"ru", "de", "uk", "en"}


def test_only_english_may_fall_back_to_its_file() -> None:
    # The fallback exists so a network failure does not leave a blank where
    # a verse belongs. It is English-only on purpose: archaic Scripture is
    # still Scripture, while the Russian bundle would confidently print
    # James where the lesson said Romans, and German and Ukrainian have
    # nothing to fall back to.
    assert set(TRUSTED_BUNDLE_LOCALES) == {"en"}
    assert "ru" not in TRUSTED_BUNDLE_LOCALES


def test_a_placeholder_is_not_a_verse() -> None:
    """`kjv-en.json` marks a versification gap with a literal `[]`.

    KJV numbers 3 John to fourteen verses; other traditions have fifteen, and
    the bundle keeps the key with `"[]"` as its text. Unguarded, a lesson
    citing 3 John 15 pasted `[]` into a student's blockquote where Scripture
    should be. One verse rather than the Russian bundle's thousands, and the
    same rule: a placeholder is an absence, and an absence is safe.
    """
    assert lookup(_ref("3john", 1, 15), "en") is None
    # And the verse before it, which is real, still resolves — the guard must
    # not have quietly disabled the book.
    assert lookup(_ref("3john", 1, 14), "en") is not None
