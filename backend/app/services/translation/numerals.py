"""Numbers written as words, which nothing else checks.

`validation.py` checks digits, and carefully: a chapter-and-verse
reference must survive, a year must survive, a count must survive. It
has nothing to say about a number written as a word, because until now
nobody had looked.

Production had this, in a quiz answer, marked ok and served: the Russian
option «Двенадцать» — twelve — came back in German as *Fünf*. Five. In a
question about how many of something there are, which is the one place
where the number is the entire answer. It passed every structural check
(nothing malformed, length fine, language right) and it passed the
reviewer, because "Fünf" is a perfectly good German word in a perfectly
good sentence.

The check is deliberately narrow, and each limit is there to stop it
flagging correct prose:

* only the numbers a course actually counts with — up to twenty, then
  the round ones. Beyond that, prose stops saying "eighty-seven" and
  starts writing 87, which the digit check already covers;
* only whole words, so «сто» inside «стоит» is not a number;
* `one` and `один` are skipped entirely. They are articles, pronouns and
  intensifiers far more often than counts — "one of the disciples", "ein
  Buch", "один из них" — and a check that fires on those would flag half
  the catalogue;
* so are «сто» and «тысяча». Three letters with a permitted suffix
  matches «стоит», and a check that flags "es lohnt sich zu lesen" for
  losing a hundred is a check nobody will keep;
* and it only fires when the numeral IS the whole source string.

That last limit was measured, not chosen. Searching for numerals inside
prose was tried against all 8,492 short strings in production and
produced 61 hits, every one of them false: «двадцать» contains «два»,
«семьдесят» and «семье» both contain «семь», German "Sechzig" does not
contain "sechs", and the Ukrainian five written with a typewriter
apostrophe does not match the same word written with a typographic one.
Telling those apart needs morphology, not string matching.

What is left is narrow and exact, and it covers the case that actually
went wrong: a quiz option whose entire text is a number. That is where
the number IS the answer, and where «Двенадцать» coming back as *Fünf*
is not a nuance — it is a different answer to the question.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode


# Each row is one number in ru, en, de, uk. Where a language inflects the
# numeral, the base form is listed and the matcher allows a short suffix
# — "Zwölf"/"zwölfte", "двенадцать"/"двенадцати", "дванадцять"/
# "дванадцяти" all count as the same number being present.
class Numeral(NamedTuple):
    """One number in every language served. Named rather than positional
    so a reader can see which column is which, and so the type checker
    can too."""

    value: int
    ru: str
    en: str
    de: str
    uk: str


_NUMERALS: Final[tuple[Numeral, ...]] = tuple(
    Numeral(*row)
    for row in (
        (2, "два", "two", "zwei", "два"),
        (3, "три", "three", "drei", "три"),
        (4, "четыре", "four", "vier", "чотири"),
        (5, "пять", "five", "fünf", "п'ять"),
        (6, "шесть", "six", "sechs", "шість"),
        (7, "семь", "seven", "sieben", "сім"),
        (8, "восемь", "eight", "acht", "вісім"),
        (9, "девять", "nine", "neun", "дев'ять"),
        (10, "десять", "ten", "zehn", "десять"),
        (11, "одиннадцать", "eleven", "elf", "одинадцять"),
        (12, "двенадцать", "twelve", "zwölf", "дванадцять"),
        (13, "тринадцать", "thirteen", "dreizehn", "тринадцять"),
        (14, "четырнадцать", "fourteen", "vierzehn", "чотирнадцять"),
        (15, "пятнадцать", "fifteen", "fünfzehn", "п'ятнадцять"),
        (16, "шестнадцать", "sixteen", "sechzehn", "шістнадцять"),
        (17, "семнадцать", "seventeen", "siebzehn", "сімнадцять"),
        (18, "восемнадцать", "eighteen", "achtzehn", "вісімнадцять"),
        (19, "девятнадцать", "nineteen", "neunzehn", "дев'ятнадцять"),
        (20, "двадцать", "twenty", "zwanzig", "двадцять"),
        (30, "тридцать", "thirty", "dreißig", "тридцять"),
        (40, "сорок", "forty", "vierzig", "сорок"),
        (50, "пятьдесят", "fifty", "fünfzig", "п'ятдесят"),
        (60, "шестьдесят", "sixty", "sechzig", "шістдесят"),
        (70, "семьдесят", "seventy", "siebzig", "сімдесят"),
    )
)

_LOCALES: Final[frozenset[str]] = frozenset({"ru", "en", "de", "uk"})

#: Punctuation stripped before asking "is this string a number?" — an
#: answer option often ends in a full stop and is no less a number for
#: it.
_BARE: Final[re.Pattern[str]] = re.compile(r"[\s.,;:!?«»„“”\"'()\[\]]+")


# Ukrainian words carry an apostrophe, and the corpus now carries two of
# them: the typographic U+2019 that `typography.py` normalises to, and
# the typewriter U+0027 these tables were written with. Comparing the two
# spellings as different words made the register stop recognising
# the Ukrainian word for Pentecost the day typography shipped — a check
# quietly going blind, which is worse than a check that never existed.
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u02bc": "'", "\u2018": "'"})


def _fold_apostrophes(text: str) -> str:
    return text.translate(_APOSTROPHES)


def _word_pattern(word: str) -> re.Pattern[str]:
    # Strict at the start, forgiving at the end: a suffix is a form of
    # the numeral, a prefix usually makes it a different word.
    return re.compile(rf"(?<!\w){re.escape(_fold_apostrophes(word))}\w{{0,4}}", re.IGNORECASE)


_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    word: _word_pattern(word) for row in _NUMERALS for word in (row.ru, row.en, row.de, row.uk)
}


def numbers_lost(
    source: str,
    translation: str,
    *,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
) -> list[tuple[str, str]]:
    """Numerals the source spells out and the translation does not.

    Returns ``(source word, expected target word)`` pairs. Empty when
    every number the source counts with is present in the answer — in
    any form, since these languages decline.
    """
    if not source or not translation:
        return []
    if source_locale not in _LOCALES or target_locale not in _LOCALES or source_locale == target_locale:
        return []

    bare = _fold_apostrophes(_BARE.sub("", source)).strip().lower()
    missing: list[tuple[str, str]] = []
    for row in _NUMERALS:
        source_word: str = getattr(row, source_locale)
        # The numeral has to BE the string, not appear in it. See the
        # module docstring for the measurement behind that.
        if bare != _fold_apostrophes(source_word).lower():
            continue
        target_word: str = getattr(row, target_locale)
        if _PATTERNS[target_word].search(_fold_apostrophes(translation)):
            continue
        # The digit is an acceptable rendering of the word: "twelve" as
        # "12" says the same thing and reads fine in a short answer.
        if re.search(rf"(?<!\d){row.value}(?!\d)", translation):
            continue
        missing.append((source_word, target_word))
    return missing


__all__ = ["numbers_lost"]
