# ruff: noqa: RUF003
# The edition names in the prose are Cyrillic because that is their name.
"""Hebrew and Septuagint number the Psalms differently, and the difference is silent.

A bible that follows the other system does not answer "no such psalm" —
it answers a *different psalm*, in fluent prose, with the right shape.
Ask a Septuagint-numbered edition for Psalm 23 and it returns "The earth
is the Lord's", which is Hebrew 24, and nothing anywhere reports a
problem.

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

The chapter rule is not enough
------------------------------
The first fix here subtracted one from the chapter across two bands, and
that is the rule everyone quotes. Measured against the live edition on
2026-08-16, it is wrong in three ways at once:

* **the verse moves too.** Hebrew 34:8 is not 33:8 but 33:9, because the
  superscription is unnumbered in Hebrew and numbered in the Slavic
  tradition. Ask for 33:8 and you get the previous line — again, fluent,
  plausible, and not what was cited.
* **the shift is not constant inside a psalm.** Psalm 18 verse 1 shifts
  by nothing and its other forty-nine verses by one.
* **agreeing on the chapter does not mean agreeing on the verse.** Psalm
  3 has the same number in both systems and its verses are still off by
  one; the old ``1-8`` identity band quoted every one of them wrongly.

So the mapping is a table, verse by verse, derived from the markers the
Synodal text carries for exactly this purpose — see
``scripts/derive_psalm_numbering.py``. A reference absent from the table
is one where the two systems agree: Psalms 1, 2, 148, 149 and 150.

The table also settles the psalms the band rule had to refuse. Hebrew 10
is not a separate psalm in the Slavic tradition — Hebrew 10:1 is Slavic
9:22 — and Hebrew 116 is split, its first verse landing at 114:1. Those
used to answer ``None``, which meant a Russian reader was shown the
author's untranslated verse instead.

Which editions are which was measured, not assumed — see
``SEPTUAGINT_LOCALES``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from app.services.bible.references import BibleRef

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

_TABLE_PATH: Final = Path(__file__).resolve().parent / "data" / "psalm_hebrew_to_septuagint.json"

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


@lru_cache(maxsize=1)
def _table() -> dict[str, tuple[int, int]]:
    raw: dict[str, str] = json.loads(_TABLE_PATH.read_text(encoding="utf-8"))
    parsed: dict[str, tuple[int, int]] = {}
    for hebrew, septuagint in raw.items():
        chapter, verse = septuagint.split(".")
        parsed[hebrew] = (int(chapter), int(verse))
    return parsed


def _lookup(chapter: int, verse: int) -> tuple[int, int]:
    """Where ``chapter:verse`` lands, identical numbering if unlisted."""
    return _table().get(f"{chapter}.{verse}", (chapter, verse))


def remap_psalm(ref: BibleRef, locale: LocaleCode | str) -> BibleRef | None:
    """Return ``ref`` as ``locale``'s edition numbers it.

    ``None`` means "this edition cannot be asked for this reference":
    the only remaining case is a range whose ends fall in two different
    psalms once remapped, which happens where the Slavic tradition
    splits a Hebrew psalm and no single reference can name the span. The
    caller treats that the way it treats any other absence — keep the
    author's own quotation, or move to the next candidate.

    Everything that is not a psalm, and every locale that numbers them
    the Hebrew way, passes through untouched.
    """
    if locale not in SEPTUAGINT_LOCALES or ref.book != "psalms":
        return ref

    chapter, verse_start = _lookup(ref.chapter, ref.verse_start)

    verse_end: int | None = None
    if ref.verse_end is not None:
        end_chapter, verse_end = _lookup(ref.chapter, ref.verse_end)
        if end_chapter != chapter:
            return None

    return BibleRef(book=ref.book, chapter=chapter, verse_start=verse_start, verse_end=verse_end)


def remap_usfm(ref: str, locale: LocaleCode | str) -> str | None:
    """The same rule, for callers holding a USFM string (``PSA.23.1``).

    The verse-of-the-day walk speaks USFM end to end and never builds a
    ``BibleRef``. It had its own copy of this logic — correct, and one
    edit away from disagreeing with the copy that serves everything
    else about which psalms are which.
    """
    if locale not in SEPTUAGINT_LOCALES or not ref.startswith("PSA."):
        return ref
    parts = ref.split(".")
    if len(parts) < 3:
        return ref
    try:
        chapter = int(parts[1])
        verses = [int(piece) for piece in parts[2].split("-")]
    except ValueError:
        return ref
    if not verses:
        return ref

    mapped = [_lookup(chapter, verse) for verse in verses]
    if len({chapter for chapter, _ in mapped}) > 1:
        return None
    return f"PSA.{mapped[0][0]}." + "-".join(str(verse) for _, verse in mapped)


__all__ = ["SEPTUAGINT_LOCALES", "remap_psalm", "remap_usfm"]
