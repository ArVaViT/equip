"""Parse Bible verse references from running text, in all four languages.

Recognizes printed forms like:
* ``Acts 1:8``, ``Acts 1.8``
* ``Acts 1:8-10`` (single chapter range)
* ``Деян. 1:8``, ``Деяния 1:8``, ``Деяния Апостолов 1:8``
* ``(Деян. 20:28)``, ``(Acts 1:8)`` (parenthesized)
* ``1 Cor. 13:4-7``, ``1 Кор. 13:4-7``, ``1-е Коринтян 13:4-7``
* ``Apg. 1,8``, ``Apostelgeschichte 1,8``, ``1. Mose 1,1``
* ``Дії 1:8``, ``Матвія 5:9``

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

from app.services.bible.books import all_aliases, find_book, written_as_a_book_name

# One space, however the author's tools wrote it. Word keeps a citation
# on one line by putting a non-breaking space between the book and the
# chapter (``Ин. 3:16``, ``1 Кор. 13:4``), and the editor stores that
# character the way ``innerHTML`` serialises it — as the entity
# ``&nbsp;``, six characters that ``\s`` does not match. A course pasted
# from Word had every one of its citations skipped: no canonical verse
# was substituted, and the model was left to re-word Scripture, which is
# the one thing this whole layer exists to prevent. ``\s`` already covers
# the bare U+00A0; the entity forms are added beside it. The ``#`` is
# escaped because this class ends up inside a VERBOSE pattern, where a
# bare ``#`` opens a comment.
_SPACE = r"(?:\s|&nbsp;|&\#160;|&\#xa0;)"
# The same three entities as a pattern to fold, for the book name that
# the match hands to ``find_book``: ``1&nbsp;Кор.`` is ``1 Кор.`` to the
# alias table only once the entity is a space again.
_SPACE_ENTITY = re.compile(r"&nbsp;|&#160;|&#xa0;", re.IGNORECASE)
# Between the number of a numbered book and its name. Four languages
# print that join four ways — ``1 Samuel``, ``1. Mose``, ``1Кор.``,
# ``1-е Коринтян`` — and ``books._normalize`` folds all four to
# ``"1 name"``, so the pattern built from a folded alias has to unfold
# them again. The two are a pair; the round-trip test walks every alias
# through both.
_NUMBER_JOIN = rf"{_SPACE}*[.\-]?{_SPACE}*(?:ше|ге|тє|е)?{_SPACE}*"
# Between the words of a multi-word name (``Song of Solomon``, ``Дії
# апостолів``). Real whitespace, unlike the number join: the no-space
# spellings that exist (``songofsolomon``) are declared aliases in their
# own right.
_WORD_JOIN = rf"{_SPACE}+"
# Which apostrophe an author's keyboard produced is not a difference
# worth failing on — ``Об'явлення`` and ``Об’явлення`` are one word.
_APOSTROPHE_CLASS = "['’ʼ‘`]"
_ALIAS_TOKENS = re.compile(r"[\s.\-]+")


def _alias_pattern(alias: str) -> str:
    """One normalized alias as a regex that matches the ways it is
    actually printed. Tolerant about the punctuation inside a name and
    strict about its letters."""
    tokens = [t for t in _ALIAS_TOKENS.split(alias) if t]
    escaped = [re.escape(t).replace("'", _APOSTROPHE_CLASS) for t in tokens]
    if len(escaped) > 1 and tokens[0] in ("1", "2", "3", "4", "5"):
        return escaped[0] + _NUMBER_JOIN + _WORD_JOIN.join(escaped[1:]) + r"\.?"
    return _WORD_JOIN.join(escaped) + r"\.?"


def _build_book_pattern() -> str:
    """Build a non-capturing alternation of every known book alias,
    longest-first so regex matching prefers ``Деяния Апостолов`` over
    ``Деяния`` when both could match. Each alias is expanded into its
    printed variants, then optionally followed by a literal ``.`` so
    ``Acts.`` and ``Acts`` both succeed."""
    return "(?:" + "|".join(_alias_pattern(a) for a in all_aliases()) + ")"


_BOOK_RE = _build_book_pattern()

_REF_PATTERN = re.compile(
    rf"""
    (?<!\w)
    (?P<book>{_BOOK_RE})
    {_SPACE}+
    (?P<chapter>\d+)
    [:.,]
    (?P<verse_start>\d+)
    (?:{_SPACE}*[-–—]{_SPACE}*(?P<verse_end>\d+))?
    """,
    re.VERBOSE | re.UNICODE | re.IGNORECASE,
)

# Three notes on that pattern, each of them a bug that was there before.
#
# ``(?<!\w)``: without it the alternation matches inside a longer word,
# and "Facts 1:8" parsed as Acts 1:8. Harmless-looking until the alias
# table grew two-letter German forms, at which point every word ending
# in "am" became Amos.
#
# ``,`` as the chapter/verse separator: German prints ``Joh 3,16``, and
# so does the Russian typographic convention on occasion. No whitespace
# is allowed after it, deliberately — "Genesis 1, 8 verses later" is a
# sentence, not a citation, and the space is the only thing telling the
# two apart.
#
# A verse *list* (``Joh 3,16.18`` — verses 16 and 18, not a range) is
# read as its first verse and the rest is left standing in the text.
# We look up one passage, so 16 is the answer; and swallowing ".18" into
# the span would mean ``_localize_ref_tail`` rewrote the citation
# without it, quietly dropping a verse the author cited.


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
    indices into the original string, useful for surgical replacement.

    ``book_named`` is ``False`` when the author wrote only the numbers
    and the book came from somewhere else — see ``parse_bare_references``.
    It exists so nothing re-prints a citation with a book name the author
    deliberately left out: a lesson inside the book of Acts writes
    ``(1:8)`` and rewriting that to ``(Apg. 1,8)`` would be an edit, not
    a localization.
    """

    ref: BibleRef
    span: tuple[int, int]
    raw_text: str
    book_named: bool = True


# A citation with no book in front of it: ``(1:8)``, ``(28:30–31)``,
# ``(2,42)``. Parenthesised, and only parenthesised — that is the whole
# guard. Bare digits with a colon between them are a time of day, a
# score, a ratio and a chapter of Acts, and nothing in the string tells
# the four apart; inside parentheses, standing on their own, in prose
# that cites Scripture, they are a citation.
_BARE_REF_PATTERN = re.compile(
    r"""
    \(\s*
    (?P<chapter>\d{1,3})
    [:,]
    (?P<verse_start>\d{1,3})
    (?:\s*[-–—]\s*(?P<verse_end>\d{1,3}))?
    \s*\)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class BareReference:
    """A citation that names chapter and verse and no book.

    Measured over the live catalogue on 2026-08-22: 196 of them in the
    Russian sources of the three published courses, against 13
    blockquotes whose citation names its book. A course *about* the book
    of Acts stops writing "Acts" after the first page, exactly as its
    reader stops reading it — and every one of those 196 was invisible to
    a parser that requires a book name, so the verse beside it was never
    recognised as a quotation and went to the model to be re-worded.

    Which book it means is not decided here. ``chapter`` and
    ``verse_start`` are facts about the string; the book is a guess, and
    the caller resolves it against the books the surrounding document
    names and then checks the words. See
    ``substitution._bare_reference_candidates``.
    """

    chapter: int
    verse_start: int
    verse_end: int | None
    span: tuple[int, int]
    raw_text: str


def parse_bare_references(text: str) -> list[BareReference]:
    """Every parenthesised book-less citation in ``text``, in order.

    A reference that *does* name its book is not returned twice: the
    parenthesis around ``(Деян. 1:8)`` holds a book name, so the pattern
    here — which allows nothing between the opening paren and the first
    digit — does not match it.
    """
    if not text:
        return []
    out: list[BareReference] = []
    for m in _BARE_REF_PATTERN.finditer(text):
        verse_end_raw = m.group("verse_end")
        verse_end = int(verse_end_raw) if verse_end_raw else None
        verse_start = int(m.group("verse_start"))
        if verse_end is not None and verse_end < verse_start:
            continue
        out.append(
            BareReference(
                chapter=int(m.group("chapter")),
                verse_start=verse_start,
                verse_end=verse_end,
                span=m.span(),
                raw_text=m.group(0),
            )
        )
    return out


def parse_references(text: str, locale: str | None = None) -> list[ParsedReference]:
    """Find every Bible reference in ``text`` and return them in order
    of first appearance. Skips matches whose book name doesn't resolve
    via ``find_book`` (defence-in-depth — the regex already only allows
    declared aliases).

    ``locale`` is the language ``text`` is written in, where the caller
    knows it. It settles ``1 Цар.``, which is 1 Samuel to a Russian
    reader and 1 Kings to a Ukrainian one; everything else reads the
    same in every language.
    """
    if not text:
        return []
    out: list[ParsedReference] = []
    for m in _REF_PATTERN.finditer(text):
        book_raw = _SPACE_ENTITY.sub(" ", m.group("book"))
        # An alias that is also an ordinary word has to be written as a
        # book name to be read as one — otherwise "The ratio is 1:2" is
        # Isaiah and "am 10:30 Uhr" is Amos. See ``books.py``.
        if not written_as_a_book_name(book_raw):
            continue
        canonical = find_book(book_raw, locale)
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


__all__ = [
    "BareReference",
    "BibleRef",
    "ParsedReference",
    "parse_bare_references",
    "parse_references",
]
