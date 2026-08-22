# ruff: noqa: RUF002
# «Стефан» beside «Степан» and «Лісій» beside «Лисий» is the subject of
# this module, not a typo. The two spellings differ by one letter on
# purpose.
"""A person called by a name the language does not print.

The defect
----------

A native Ukrainian editor read the live catalogue and found the first
martyr called two things inside one course. Eight rows of lesson prose
print «Стефан», which is what a Ukrainian Bible prints. Eight further
rows print «Степан» — and every one of those eight is an assessment
item:

    хто схвалив страту Степана?
    присутній при смерті Степана і схвалює її?
    На якій основній тезі побудована промова Степана в Діян. 7?

«Степан» is the ordinary Ukrainian given name Stepan. It is not the
first martyr, and no Ukrainian edition calls him by it: Куліш 1905, the
edition this platform serves, has «Стефана» at Acts 6:5, 7:59, 8:2,
11:19 and 22:20. So a student reads the lesson, learns the name, and is
then examined on a different one — with no way to recover the right
name from the wrong one, because nothing on the page carries both.

Why ``proper_names`` cannot say this
------------------------------------

``substituted_names`` asks whether the source named one *known* person
and the translation named a *different known* one. «Степан» is neither
half of that: it is the same man, misspelt. Widening that check until
it fires here would mean flagging "the name changed", and a name
legitimately changes in every row of a translated catalogue.

So this is the other question, and it is
``book_names.foreign_book_names``'s question asked about a person:

    *The translation names a person with a form this language does not
    print for them.*

The same two-table shape holds it up. ``proper_names._NAMES`` is what
each language prints; ``proper_names._NOT_PRINTED_HERE`` is what it does
not, registered into the same index so every other question still
resolves these spellings to the right person, and deliberately absent
from the printed table so this one can refuse them. Take «Степан» out
of the index altogether instead and the row reads as a name arriving
out of nowhere — the wrong diagnosis, and an accusation of putting
somebody there who was never named.

Literal, where everything else in ``proper_names`` is phonetic. That is
forced: ``_skeleton`` maps ``и`` and ``і`` to one letter so that
«Галилея» can meet «Галілея», and the price is that «Лисий» and «Лісій»
are the same word to it. One of those two is what Ukrainian prints.
Spelling is the whole subject here, so the spelling is what is read.

Conditioned on the source, exactly as the book check is
-------------------------------------------------------

Nothing is accused for looking unusual. The check fires only where the
Russian source *strictly* named the same person — an exact form from
the table, the same standard ``substituted_names`` demands of both
halves of its accusation, and for the same measured reason: read
loosely, a source side invents names out of ordinary words.

That condition is what makes the two riskiest rows safe. «Лисий» is an
ordinary Ukrainian adjective (*bald*) and «Лій» an ordinary Ukrainian
noun (*tallow*); a capitalised one of either, in a row whose Russian
source names Claudius Lysias, is the tribune and not the adjective.
Without the anchor this would be a spellchecker with opinions.

What it will not say
--------------------

* **A form nobody has read.** The table is closed and hand-checked, the
  same closure ``bible.books.not_printed_in`` declares. A novel
  invention is out of reach by design.
* **German ``Stephan``.** Measured: 14 German rows write *Stephans
  Rede*, *der Tod Stephans*, and it was tempting to call them the same
  defect. They are not. German prints that name for that man — the
  feast is der Stephanstag and the cathedral in Vienna is der
  Stephansdom — and a row claiming otherwise would have flagged
  fourteen rows of correct prose. Every entry in the table is a claim
  about a language, and a wrong claim does not misfire quietly.
* **German ``Serna`` for «Тавифа».** A real defect and a different one:
  «серна» is a Russian common noun (the gazelle the name means) carried
  into German untranslated. It is not a spelling of Dorcas, and the
  source that would have to anchor it does not name her either.
* **«Тавифа» → «Дорка».** Two names, so ``substituted_names`` already
  reports it — measured, on the live row.

Cost: no database, no model, one pass over the capitalised words.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from app.schemas.locale import LOCALE_CODES, LanguageNotInTable
from app.services.translation.proper_names import (
    capitalised_words,
    named_in,
    not_printed_in,
    printed_in,
)

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

#: Locale → casefolded spelling that language does not print → name.
#: Built once at import from the closed table.
_LISTED: Final[dict[str, dict[str, str]]] = {}


def _listed(locale: str) -> dict[str, str]:
    table = _LISTED.get(locale)
    if table is None:
        table = {form.casefold(): key for form, key in not_printed_in(locale)}
        _LISTED[locale] = table
    return table


def foreign_person_names(
    source: str,
    translated: str,
    *,
    source_locale: LocaleCode | str,
    target_locale: LocaleCode | str,
) -> list[tuple[str, str]]:
    """Every person in ``translated`` named with a spelling ``target_locale``
    does not print for them.

    Returns ``(printed, what this language prints)`` pairs, in the order
    they stand in the text, one per distinct spelling — the same shape
    ``book_names.foreign_book_names`` returns, because a reviewer reads
    the two sentences the same way.
    """
    if not source or not translated or source_locale == target_locale:
        return []
    if source_locale not in LOCALE_CODES or target_locale not in LOCALE_CODES:
        raise LanguageNotInTable(
            f"The proper-name table has no column for {source_locale!r} or "
            f"{target_locale!r}. It carries {', '.join(LOCALE_CODES)}. A pair "
            "it cannot read is a pair where a person may be named with a "
            "spelling the language does not have and nothing will say so, "
            "and an empty answer would look like a pass."
        )
    listed = _listed(str(target_locale))
    if not listed:
        # Nothing is written down for this language. Not the same as a
        # pass and not claimed to be one: three of the four served
        # languages have no row, because no editor has read a bad
        # spelling in them.
        return []

    found: dict[str, str] = {}
    for word, _offset in capitalised_words(translated, str(target_locale)):
        key = listed.get(word.casefold())
        if key is None or word in found:
            continue
        found[word] = key

    if not found:
        return []
    named = named_in(source, str(source_locale))
    return [(word, printed_in(key, str(target_locale)) or key) for word, key in found.items() if key in named]


__all__ = ["foreign_person_names"]
