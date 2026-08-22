# ruff: noqa: RUF001, RUF002
# «Дії» beside `Діїв.` and `Rut` beside `Ruth` is the subject of this
# module, not a typo. Cyrillic and Latin stand side by side by design.
"""A book of the Bible called by a name the language does not print.

The defect
----------

Native editors read the live catalogue and found one book printed
several ways inside one language. Ukrainian Acts appears as ``Дії`` and
also as ``Діїв.``, ``Ді.`` and ``Деянь`` — the last of those a Russian
stem wearing a Ukrainian ending. German cites ``3. Könige``, a book that
does not exist in a German Bible: Luther numbers Kings 1-2, having
numbered Samuel 1-2, and only the Slavonic tradition counts Samuel in
and reaches a third. Ukrainian does the same thing with ``3 Царів``.
A German explanation cites ``Mark 5,1`` — the English name — for a
question whose own text correctly says ``Markus 5,1``. A Ukrainian
question asks about ``Галатам 2:1`` and is answered by an explanation
citing ``Галатів 2:1``.

Every one of those passes ``validation.py``. The markup matches, the
markers came back, the digits survived, the language detector is
satisfied — a wrong book *name* is a word, and a word is the shape that
module says it is blind to.

Why the machine may rule here
-----------------------------

``glossary.py`` and ``consistency.py`` both stop short of ruling,
because ``Завіт`` and ``Заповіт`` are both defensible Ukrainian and
nothing local can pick between them. Book names are the one class where
that reservation does not apply. A language has spellings it prints and
spellings it does not; ``bible/books.py`` writes down which is which for
all four served languages, and ``find_book_written_in`` is the question
"would this language have printed this?" asked against that table.

So this is not a house-style rule. ``1. Mose`` and ``Genesis`` are both
real German and both pass; ``Rut`` and ``Ruth`` both pass; ``Псалтирь``
and ``Псалом`` both pass. What does not pass is a spelling no edition of
that language carries.

What it will not say, which is most of what it sees
---------------------------------------------------

The first version of this check flagged ``Isaiah`` in English prose. The
alias table it rested on held sixty-six English abbreviations and no
full names, so ``find_book_written_in("Isaiah", "en")`` was ``None`` and
the check read that ``None`` as an accusation. It is not one. ``None``
means *this table does not know the string*, and the overwhelmingly
common reason for that is that the string is not a book name at all, or
is a book name in a grammatical case nobody wrote down. Ukrainian
declines a book name in running prose — «Згідно з Ісаєю 7:1», «У Бутті
1:1», «книгою Чисел 13:2», «У Повторенні Закону 34:1» — and every one of
those is correct Ukrainian that a scan reading the word in front of the
numbers will offer up as an invented book.

Measured over the live catalogue, a scan like that reports fifty-seven
spans and roughly forty of them are ordinary declension. That is the
false positive this module exists to not make.

So nothing is accused on the strength of not being recognised. An
accusation needs a spelling this repository can name, and there are
exactly two ways to get one:

**It resolves to the book the source cited.** ``find_book`` reads all
four languages, so ``Руф`` (Russian), ``Mark`` (English) and ``Галатам``
(Russian) are all recognisable *as* books; ``find_book_written_in``
then says the target language does not print them. Both halves are
exact table lookups, and the reference is only looked at where the
Russian source cited that same chapter and verse — the anchor
``validation._check_verse_refs`` learned the hard way, which is what
keeps ``Der Kurs beginnt um 14:30`` from being a book called *um*.

**It is written down as not-printed.** ``Діїв.``, ``Ді.``, ``Деянь``,
``3. Könige``, ``3 Царів``, ``Hoheslied`` — spellings that resolve to
nothing anywhere, which is precisely why a table cannot refuse them and
precisely why they had to be read by a person and listed. That list is
``books.not_printed_in`` and it is closed. A genuinely novel invention
is out of reach by design, and saying so is cheaper than the check that
would guess at it.

Cost: no database, no model, one pass of two regexes per row.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from app.core.sanitize import strip_tags
from app.services.bible.books import (
    display_book_name,
    find_book,
    find_book_written_in,
    normalize_book_name,
    not_printed_in,
    written_as_a_book_name,
)
from app.services.bible.psalm_numbering import renumber_between
from app.services.bible.references import parse_references

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

#: A chapter-and-verse pair with up to three words in front of it. Not
#: built out of the alias table the way ``bible/references.py`` is,
#: because the strings that matter here are the ones the table does not
#: know; what the table decides is which of these words, if any, is
#: allowed to be called a book name.
#:
#: The optional leading ordinal is not decoration. German prints the
#: Pentateuch ``1. Mose`` … ``5. Mose`` and every language numbers
#: Samuel, Kings, Corinthians and Peter; without it the scan reads
#: ``1. Mose 1,1`` as a book called *Mose* and reports the correct
#: spelling as the defect.
_PRINTED_REFERENCE: Final[re.Pattern[str]] = re.compile(
    r"(?P<name>(?:[1-5]\s*\.?\s*)?(?:[^\W\d_][\w'’]*\.?\s+){0,2}[^\W\d_][\w'’]*\.?)\s*"
    r"(?P<chapter>\d{1,3})\s*[:,.]\s*(?P<verse>\d{1,3})"
)

#: Words and small numbers, with the full stop that an abbreviation
#: carries. The stop has to come along: ``written_as_a_book_name``
#: refuses ``Ді`` and accepts ``Ді.``, and that distinction is only
#: available to a caller that kept the character.
_TOKEN: Final[re.Pattern[str]] = re.compile(r"[^\W\d_][\w'’]*\.?|\d{1,3}\s*\.?", re.UNICODE)

#: How many tokens a not-printed spelling may span — ``3. Könige`` is
#: two and nothing written down is longer.
_MAX_TOKENS: Final[int] = 2

#: Locale → normalized not-printed spelling → slug. Built once.
_NOT_PRINTED: Final[dict[str, dict[str, str]]] = {}


def _not_printed(locale: str) -> dict[str, str]:
    table = _NOT_PRINTED.get(locale)
    if table is None:
        table = {normalize_book_name(form): slug for form, slug in not_printed_in(locale)}
        _NOT_PRINTED[locale] = table
    return table


def _plain(text: str) -> str:
    return strip_tags(text) if "<" in text else text


def _cited(source: str, source_locale: str, target_locale: str) -> dict[tuple[int, int], set[str]]:
    """Chapter and verse → the books the source cited there.

    A set rather than a slug: one row may cite ``Деян. 2:4`` and
    ``Ин. 2:4``, and a translation printing either at ``2:4`` is right.
    Psalm numbering moves between editions, so the reference is recorded
    under the numbers the *target* would print as well as its own.
    """
    found: dict[tuple[int, int], set[str]] = {}
    for reference in parse_references(_plain(source), source_locale):
        found.setdefault((reference.ref.chapter, reference.ref.verse_start), set()).add(reference.ref.book)
        for form in renumber_between(reference.ref, source_locale=source_locale, target_locale=target_locale):
            found.setdefault((form.chapter, form.verse_start), set()).add(reference.ref.book)
    return found


def _the_book_in(name: str, expected: set[str], locale: str) -> str | None:
    """The part of ``name`` that is a book name, or ``None``.

    Longest tail first, so ``Згідно з Дії апостолів 2:1`` gives back the
    whole title and not the last word of it. Three answers collapse into
    ``None`` and they are all the same answer — *say nothing*: no tail
    resolves (``Ісаєю``, ``Schlüsselstellen``), the tail that resolves
    names a different book than the source cited here, or it is one of
    the aliases that are also ordinary words and is not written as a
    name.
    """
    words = name.split()
    for start in range(len(words)):
        tail = " ".join(words[start:])
        slug = find_book(tail, locale)
        if slug is None:
            continue
        if slug not in expected or not written_as_a_book_name(tail):
            return None
        return tail
    return None


def _spans(text: str) -> list[tuple[str, str]]:
    """Every one- and two-token window of ``text``, as (raw, normalized)."""
    tokens = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(text)]
    windows: list[tuple[str, str]] = []
    for i in range(len(tokens)):
        for width in range(1, _MAX_TOKENS + 1):
            if i + width > len(tokens):
                break
            raw = text[tokens[i][1] : tokens[i + width - 1][2]]
            windows.append((raw.strip(), normalize_book_name(raw)))
    return windows


def foreign_book_names(
    source: str,
    translated: str,
    *,
    source_locale: LocaleCode | str,
    target_locale: LocaleCode | str,
) -> list[tuple[str, str]]:
    """Every book name in ``translated`` that ``target_locale`` does not print.

    Returns ``(printed, what this language prints)`` pairs, in the order
    they stand in the text, one per distinct spelling.
    """
    if not source or not translated or source_locale == target_locale:
        return []
    plain = _plain(translated)
    named: dict[str, str] = {}

    listed = _not_printed(str(target_locale))
    if listed:
        for raw, key in _spans(plain):
            slug = listed.get(key)
            if slug is not None and raw not in named and written_as_a_book_name(raw):
                named[raw] = display_book_name(slug, str(target_locale)) or slug

    expected = _cited(source, str(source_locale), str(target_locale))
    if expected:
        for match in _PRINTED_REFERENCE.finditer(plain):
            slugs = expected.get((int(match.group("chapter")), int(match.group("verse"))))
            if not slugs:
                continue
            printed = _the_book_in(match.group("name"), slugs, str(target_locale))
            if printed is None or printed in named:
                continue
            slug = find_book(printed, str(target_locale))
            if slug is None or find_book_written_in(printed, str(target_locale)) == slug:
                continue
            named[printed] = display_book_name(slug, str(target_locale)) or slug

    return sorted(named.items(), key=lambda pair: plain.find(pair[0]))


__all__ = ["foreign_book_names"]
