# ruff: noqa: RUF003
# The edition names in the prose are Cyrillic because that is their name.
"""Hebrew and Septuagint number the Psalms differently, and the difference is silent.

From Psalm 10 to Psalm 147 the two systems disagree by one, because the
Septuagint folds Hebrew 9 and 10 into a single psalm. A bible that
follows the other system does not answer "no such psalm" — it answers a
*different psalm*, in fluent prose, with the right shape. Ask a
Septuagint-numbered edition for Psalm 23 and it returns "The earth is
the Lord's", which is Hebrew 24, and nothing anywhere reports a problem.

The platform's references are Hebrew-numbered, because English editions
are. So every lookup into a Septuagint-numbered edition has to be
translated first, and every one that is not is a quiet misquotation.

This lived inside ``verse_of_the_day`` and covered exactly one surface.
Meanwhile ``bible/api_source`` — which serves the substitution layer,
and through it every quoted verse in every course and every Daily
Challenge explanation — asked the Russian edition for Hebrew numbers
directly. Checked on 2026-08-15: Psalm 23:1 in Russian came back as
"Господня земля и всё, что наполняет её". The shepherd psalm, quoted as
the earth being the Lord's, to every Russian reader.

Which editions are which was measured, not assumed — see
``SEPTUAGINT_LOCALES``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from app.services.bible.references import BibleRef

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

# The two bands where a clean -1 offset holds: Hebrew 11-113 and
# 117-146. Outside them either the numbers agree (1-8, 148-150) or a
# psalm is split or joined and no per-verse mapping is honest.
_OFFSET_BANDS: Final[tuple[tuple[int, int], ...]] = ((11, 113), (117, 146))
_IDENTICAL_BANDS: Final[tuple[tuple[int, int], ...]] = ((1, 8), (148, 150))

#: Editions that number the Psalms the Septuagint way.
#:
#: Checked against the live API on 2026-08-15 at every reference where
#: the systems disagree, rather than inferred from the language. НРТ
#: answers Hebrew 23 with Hebrew 24's text and gives the shepherd psalm
#: at 22 — Septuagint. Luther 1912 and Куліш answer every probe the way
#: the Hebrew-numbered English edition does, so neither is remapped.
#:
#: The Ukrainian result is the reason this is measured: a Slavic edition
#: is not automatically Septuagint-numbered, and assuming it was would
#: have been reasonable, confident, and wrong.
SEPTUAGINT_LOCALES: Final[frozenset[str]] = frozenset({"ru"})


def _in(chapter: int, bands: tuple[tuple[int, int], ...]) -> bool:
    return any(low <= chapter <= high for low, high in bands)


def remap_psalm(ref: BibleRef, locale: LocaleCode | str) -> BibleRef | None:
    """Return ``ref`` as ``locale``'s edition numbers it.

    ``None`` means "this edition cannot be asked for this reference":
    Hebrew 9, 10, 114, 115, 116 and 147 are split or joined across the
    two systems, and no per-verse mapping is truthful. The caller
    treats that the way it treats any other absence — keep the author's
    own quotation, or move to the next candidate.

    Everything that is not a psalm, and every locale that numbers them
    the Hebrew way, passes through untouched.
    """
    if locale not in SEPTUAGINT_LOCALES or ref.book != "psalms":
        return ref
    if _in(ref.chapter, _IDENTICAL_BANDS):
        return ref
    if _in(ref.chapter, _OFFSET_BANDS):
        return BibleRef(
            book=ref.book,
            chapter=ref.chapter - 1,
            verse_start=ref.verse_start,
            verse_end=ref.verse_end,
        )
    return None


def remap_usfm(ref: str, locale: LocaleCode | str) -> str | None:
    """The same rule, for callers holding a USFM string (``PSA.23.1``).

    The verse-of-the-day walk speaks USFM end to end and never builds a
    ``BibleRef``. It had its own copy of this logic — correct, and one
    edit away from disagreeing with the copy that serves everything
    else about which psalms are which.
    """
    if locale not in SEPTUAGINT_LOCALES or not ref.startswith("PSA."):
        return ref
    try:
        _, chapter_str, verse_str = ref.split(".", 2)
        chapter = int(chapter_str)
    except (ValueError, IndexError):
        return ref
    if _in(chapter, _IDENTICAL_BANDS):
        return ref
    if _in(chapter, _OFFSET_BANDS):
        return f"PSA.{chapter - 1}.{verse_str}"
    return None


__all__ = ["SEPTUAGINT_LOCALES", "remap_psalm", "remap_usfm"]
