"""Parse Bible verse references from running text (RU + EN forms).

Recognizes printed forms like:
* ``Acts 1:8``, ``Acts 1.8``
* ``Acts 1:8-10`` (single chapter range)
* ``Деян. 1:8``, ``Деяния 1:8``, ``Деяния Апостолов 1:8``
* ``(Деян. 20:28)``, ``(Acts 1:8)`` (parenthesized)
* ``1 Cor. 13:4-7``, ``1 Кор. 13:4-7``

Returns ``ParsedReference`` instances each carrying a ``BibleRef`` plus
the ``(start, end)`` span in the source text — needed for surgical
substitution that doesn't disturb surrounding markup.

The regex is built at module import from the alias list in ``books.py``
so any alias declared there is automatically recognized; this avoids
the trap where a permissive ``\\w+`` book pattern eats preceding words
("See Acts 1:8" → matched "See Acts").

Cross-chapter ranges (``Acts 1:8-2:3``) are intentionally NOT supported
in this first cut: rare in Equip's content, parsing them blurs
into a "range walker" that materially complicates the lookup contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.bible.books import _BOOKS, find_book


def _build_book_pattern() -> str:
    """Build a non-capturing alternation of every known book alias,
    longest-first so regex matching prefers ``Деяния Апостолов`` over
    ``Деяния`` when both could match. Each alias is escaped, then
    optionally followed by a literal ``.`` so ``Acts.`` and ``Acts``
    both succeed."""
    seen: set[str] = set()
    aliases: list[str] = []
    for _slug, alias_tuple in _BOOKS:
        for a in alias_tuple:
            if a not in seen:
                seen.add(a)
                aliases.append(a)
    aliases.sort(key=len, reverse=True)
    return "(?:" + "|".join(re.escape(a) for a in aliases) + r")\.?"


_BOOK_RE = _build_book_pattern()

_REF_PATTERN = re.compile(
    rf"""
    (?P<book>{_BOOK_RE})
    \s+
    (?P<chapter>\d+)
    [:.]
    (?P<verse_start>\d+)
    (?:\s*[-–—]\s*(?P<verse_end>\d+))?
    """,
    re.VERBOSE | re.UNICODE | re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class BibleRef:
    """Canonical pointer to a Bible passage."""

    book: str
    chapter: int
    verse_start: int
    verse_end: int | None = None

    def __str__(self) -> str:
        if self.verse_end is None:
            return f"{self.book} {self.chapter}:{self.verse_start}"
        return f"{self.book} {self.chapter}:{self.verse_start}-{self.verse_end}"


@dataclass(frozen=True, slots=True)
class ParsedReference:
    """One reference detected in a string. ``span`` is the ``(start, end)``
    indices into the original string, useful for surgical replacement."""

    ref: BibleRef
    span: tuple[int, int]
    raw_text: str


def parse_references(text: str) -> list[ParsedReference]:
    """Find every Bible reference in ``text`` and return them in order
    of first appearance. Skips matches whose book name doesn't resolve
    via ``find_book`` (defence-in-depth — the regex already only allows
    declared aliases)."""
    if not text:
        return []
    out: list[ParsedReference] = []
    for m in _REF_PATTERN.finditer(text):
        book_raw = m.group("book")
        canonical = find_book(book_raw)
        if canonical is None:
            continue
        chapter = int(m.group("chapter"))
        verse_start = int(m.group("verse_start"))
        verse_end_raw = m.group("verse_end")
        verse_end = int(verse_end_raw) if verse_end_raw else None
        # Sanity: a range must go forwards. ``Acts 1:10-8`` is meaningless.
        if verse_end is not None and verse_end < verse_start:
            continue
        ref = BibleRef(
            book=canonical,
            chapter=chapter,
            verse_start=verse_start,
            verse_end=verse_end,
        )
        out.append(ParsedReference(ref=ref, span=m.span(), raw_text=m.group(0)))
    return out


__all__ = ["BibleRef", "ParsedReference", "parse_references"]
