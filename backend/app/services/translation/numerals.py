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

* only whole words, so «сто» inside «стоит» is not a number;
* `one` and `один` are skipped entirely. They are articles, pronouns and
  intensifiers far more often than counts — "one of the disciples", "ein
  Buch", "один из них" — and a check that fires on those would flag half
  the catalogue;
* and it only fires when the source string is nothing but the number.

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

How far the table goes, and why
-------------------------------

It used to stop at seventy, on the grounds that a course counts with
small numbers and round ones. That was a statement about the three
biblical courses that existed, not about the check. A course on
arithmetic, money or physics counts with eighty, ninety, a hundred and a
thousand, and the check was silent on every one of them. It no longer
is: 80, 90, 100 and 1000 are in the table.

«Сто» and «тысяча» used to be excluded too, because three letters with a
permitted suffix matches «стоит», and a check that flags "es lohnt sich
zu lesen" for losing a hundred is a check nobody keeps. That objection
was inherited from the version of this check that searched inside prose,
and it does not survive the whole-string rule. Re-measured against the
live catalogue: a substring rule would look at 306 Russian rows for
«сто» and swallow «стоит» (153), «стоят» (60), «стороны» (56),
«столбец», «столько»; the whole-string rule looks at 2, and both of them
are the number. So «сто» is in, and «тысяча» with it.

What the widening was measured to cost: against 11,149 live translation
pairs the check goes from reading 150 rows as a number to reading 159,
and flags nothing either way. The nine are three spelling ninety and six
spelling a hundred — «Сто», "One hundred", "A hundred" — and all nine
are translated correctly. No new hits, false or true. The rows for
eighty and a thousand match nothing today, exactly as the shipped rows
for forty, fifty and eighteen match nothing today; the table describes
the numbers a course may count with, not the numbers this term's courses
happened to use.

What is deliberately still uncovered
------------------------------------

*Zero and one.* One is an article in every language served. Zero has two
Russian spellings, «ноль» and «нуль», both correct, and an answer of
"zero" is legitimately rendered «жодного», "keine", "none" — the check
would have to know that a word meaning *none* is the number, and it does
not.

*Compounds — «сорок два», "seventy-two".* Not from lack of trying: they
were measured, and they are where the false hits live. German glues them
(*zweiundsiebzig*, *einundzwanzig*), so a word-boundary search for
«семьдесят» cannot find «siebzig» inside the compound and reports a loss
that did not happen. Every compound in the live catalogue is translated
correctly and every one of them would have been flagged.

*Fractions — «две трети».* Both halves decline independently and the
denominator is an ordinal («трети», *Drittel*, "thirds"). That is
morphology, which is the line this module does not cross.

*The number with a tail — «Двенадцать процентов».* This was the widening
most worth having, and it was measured the same way the whole-string
rule was: allow the numeral to be the first token of an option of at
most three tokens. Against the live catalogue that produces 12 hits,
and all 12 are correct translations — «Шесть утра» → «Шоста ранку» (the
Ukrainian says six o'clock with an ordinal), "Two hundred" → «Двісті»
(which contains no «два»), «Двадцать одно» → *Einundzwanzig*,
"Seventy-two" → *Zweiundsiebzig*. Twelve false, zero true. This check
blocks, so a false hit is a correct page not served; the rule stays.

A language this table cannot read
---------------------------------

Narrow is not the same as absent, and the difference has to be visible.
A language whose numbers are not written down here is **refused**, at
import for the table and at the call for a lookup. It used to be
ignored: an unlisted locale made ``numbers_lost`` return ``[]`` on
every string it was ever given, which is the same value it returns when
a translation is perfect.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple

from app.schemas.locale import LOCALE_CODES, LanguageNotInTable

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode


# Each row is one number in ru, en, de, uk. Where a language inflects the
# numeral, the base form is listed and the matcher allows a short suffix
# — "Zwölf"/"zwölfte", "двенадцать"/"двенадцати", "дванадцять"/
# "дванадцяти" all count as the same number being present.
class Numeral(NamedTuple):
    """One number in every language served. Named rather than positional
    so a reader can see which column is which, and so the type checker
    can too.

    The fields after ``value`` *are* the roster: they are named for the
    locale codes and checked against ``LOCALE_CODES`` at import. That is
    deliberate — the module used to carry a separate frozenset of the
    languages it handled, which is the kind of list that goes stale
    without a sound. ``numbers_lost`` returned ``[]`` for anything
    missing from it, which reads exactly like "this translation kept all
    of its numbers"."""

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
        (80, "восемьдесят", "eighty", "achtzig", "вісімдесят"),
        (90, "девяносто", "ninety", "neunzig", "дев'яносто"),
        (100, "сто", "hundred", "hundert", "сто"),
        (1000, "тысяча", "thousand", "tausend", "тисяча"),
    )
)


def _verify_every_number_is_spelled_in_every_language(locales: tuple[str, ...]) -> None:
    """Refuse to load a table that spells its numbers in fewer languages
    than the platform serves.

    At **import**, and for the same reason as the register's row check:
    the rows are positional. ``Numeral`` already refuses a row of the
    wrong width — ``Numeral(*row)`` raises on the spot — so the only
    hole left is the class itself falling behind the roster, and that
    hole used to be papered over by a hand-written ``_LOCALES``
    frozenset that had to be remembered separately. It never would have
    been. A locale missing from it made ``numbers_lost`` return ``[]``
    for every string, forever, and a translation that turns «двенадцать»
    into *Fünf* passed.

    Names *and* order are checked, because a field is read by name here
    and written by position in the rows above: fields in a different
    order from ``LOCALE_CODES`` would put the German word in the
    Ukrainian column and every check would still pass.
    """
    spelled = Numeral._fields[1:]
    if spelled == locales:
        return
    raise LanguageNotInTable(
        f"``Numeral`` spells its numbers in {spelled} and this platform serves "
        f"{locales}. Add a field per missing language to ``Numeral``, in the order "
        f"of ``LOCALE_CODES``, and the word to all {len(_NUMERALS)} rows of "
        "``_NUMERALS``. A language with no column here is not checked less "
        "strictly, it is not checked at all: «двенадцать» coming back as *Fünf* "
        "is what this table was written for."
    )


_verify_every_number_is_spelled_in_every_language(LOCALE_CODES)

#: The languages this table spells its numbers in — the fields of
#: ``Numeral``, which the line above has just checked against the
#: roster. Read from the rows rather than listed again: the list that
#: was here before is the one that went stale in silence.
_SPELLED_IN: Final[tuple[str, ...]] = Numeral._fields[1:]


def _require_a_column_for(locale: str) -> None:
    """Refuse to answer about a language whose numbers are not written here."""
    if locale not in _SPELLED_IN:
        raise LanguageNotInTable(
            f"The numeral table has no {locale!r} column; it spells its numbers in "
            f"{', '.join(_SPELLED_IN)}. Add the field to ``Numeral`` and the "
            "word to every row, or stop asking it about a language nobody serves. "
            "Answering 'no numbers were lost' about a language this table cannot "
            "read is the failure it is here to prevent."
        )


#: One word, for the purpose of asking "is this string a number?". An
#: answer option often ends in a full stop and is no less a number for
#: it, so punctuation around the word is not part of it — but the
#: apostrophe inside «п'ять» is, and stripping it would leave Ukrainian
#: numerals unrecognisable. Apostrophes are folded to one spelling
#: first, so only U+0027 needs to appear here.
_WORD: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")

#: Longer than any string that could be nothing but a number, with a
#: leading "one" and punctuation around it, and by a wide margin.
_LONGEST_NUMERAL_STRING: Final[int] = 64

#: Words meaning *one* that may stand in front of a numeral without
#: changing it: "one hundred", "a thousand", «одна тысяча». Every word
#: here multiplies by one, so dropping it cannot turn one number into
#: another — which is why "zwei" is not on the list and "zweihundert"
#: stays out of scope.
_LEADING_ONE: Final[frozenset[str]] = frozenset(
    {"a", "an", "one", "ein", "eine", "einen", "один", "одна", "одне", "одно", "одну"}
)

#: Words a numeral may be glued to the back of. German writes a hundred
#: and a thousand as part of the word — *einhundert*, *zweitausend* — so
#: insisting on a word boundary in front of them would report a loss
#: that did not happen. Being generous here can only ever make the check
#: miss something, never make it flag correct text, which is the
#: direction to be generous in.
_GLUED: Final[frozenset[str]] = frozenset({"hundert", "tausend"})

#: Digit-group separators. German writes a thousand as "1.000", Russian
#: as "1 000"; both say what «тысяча» says.
_GROUP_SEPARATOR: Final[str] = r"[\s.,']?"


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
    # the numeral, a prefix usually makes it a different word. Except
    # for the words German glues to the back of another — see `_GLUED`.
    left = "" if word in _GLUED else r"(?<!\w)"
    return re.compile(rf"{left}{re.escape(_fold_apostrophes(word))}\w{{0,4}}", re.IGNORECASE)


_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    word: _word_pattern(word) for row in _NUMERALS for word in (row.ru, row.en, row.de, row.uk)
}


def _longest_first(locale: str) -> re.Pattern[str]:
    """Whichever numeral of ``locale`` is written at a given position.

    Alternatives are tried in order, so the longest spelling wins: at the
    start of "achtzig" this answers *achtzig* and not *acht*. That is the
    whole point of it — see `_reads_as`.
    """
    words = sorted({_fold_apostrophes(getattr(row, locale)) for row in _NUMERALS}, key=len, reverse=True)
    return re.compile("|".join(re.escape(word) for word in words), re.IGNORECASE)


_LONGEST: Final[dict[str, re.Pattern[str]]] = {locale: _longest_first(locale) for locale in _SPELLED_IN}


def _digit_pattern(value: int) -> re.Pattern[str]:
    digits = str(value)
    head, groups = digits[: len(digits) % 3 or 3], digits[len(digits) % 3 or 3 :]
    parts = [head] + [groups[i : i + 3] for i in range(0, len(groups), 3)]
    return re.compile(rf"(?<!\d){_GROUP_SEPARATOR.join(parts)}(?!\d)")


_DIGITS: Final[dict[int, re.Pattern[str]]] = {row.value: _digit_pattern(row.value) for row in _NUMERALS}


def _reads_as(translation: str, word: str, locale: str) -> bool:
    """Is ``word`` — that number, not another — written in ``translation``?

    The suffix the matcher allows is there for declension: «двенадцати»
    is twelve. It is not there to let one number stand in for another,
    and in German it would: *acht* plus a three-letter suffix is
    *achtzig*, which is not eight, it is eighty. So each match is read
    back with every numeral of the language in hand, longest first, and
    only counts if the word written there is the one being looked for.
    """
    folded = _fold_apostrophes(translation)
    target = _fold_apostrophes(word).casefold()
    for match in _PATTERNS[word].finditer(folded):
        written = _LONGEST[locale].match(folded, match.start())
        if written is not None and written.group(0).casefold() == target:
            return True
    return False


def _spelled_number(source: str, locale: str) -> str | None:
    """The numeral ``source`` consists of, if that is all it consists of.

    A leading word meaning one is allowed through — "one hundred" is a
    hundred — and nothing else is. See the module docstring for what
    letting a second word in was measured to cost.

    The length guard is not a rule about numbers, it is about work: this
    is called for every string translated, including chapter blocks of
    HTML, and splitting one of those into words to discover it is not
    «сто» is a waste. The longest string this can say yes to is
    «одиннадцать» with punctuation around it.
    """
    if len(source) > _LONGEST_NUMERAL_STRING:
        return None
    words = [word.casefold() for word in _WORD.findall(_fold_apostrophes(source))]
    while len(words) > 1 and words[0] in _LEADING_ONE:
        words = words[1:]
    if len(words) != 1:
        return None
    return words[0]


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
    _require_a_column_for(source_locale)
    _require_a_column_for(target_locale)
    if source_locale == target_locale:
        return []

    spelled = _spelled_number(source, source_locale)
    if spelled is None:
        return []
    missing: list[tuple[str, str]] = []
    for row in _NUMERALS:
        source_word: str = getattr(row, source_locale)
        # The numeral has to BE the string, not appear in it. See the
        # module docstring for the measurement behind that.
        if spelled != _fold_apostrophes(source_word).casefold():
            continue
        target_word: str = getattr(row, target_locale)
        if _reads_as(translation, target_word, target_locale):
            continue
        # The digit is an acceptable rendering of the word: "twelve" as
        # "12" says the same thing and reads fine in a short answer.
        if _DIGITS[row.value].search(translation):
            continue
        missing.append((source_word, target_word))
    return missing


__all__ = ["numbers_lost"]
