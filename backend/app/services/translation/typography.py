"""Deterministic typography for a finished translation.

What gives a machine translation away is rarely the meaning. It is the
punctuation. A bilingual editor read the production corpus on
2026-08-19 and counted, in the German column alone, four ways of setting
the same Bible reference — sometimes inside one paragraph:

    Apg 8,26   (37)      Apg. 8,26   (52)      Apostelgeschichte 8   (49)

and 94 references still separating chapter from verse with a colon
(``10:1-23``, ``11:3``) against 274 with the comma German actually
uses. The colon is not a variant, it is the Russian source's notation
walking through the pipeline untranslated — and part of it is ours:
``bible/substitution.py::_localize_ref_tail`` renders every localized
reference as ``{book} {chapter}:{verse}``, so a German reader gets
``Apg. 8:26`` from our own code, correctly spelled and wrongly pointed.

The rest of the count:

* German — 4 genitive apostrophes (``Paulus``, ``Petrus``,
  ``Philippus``) set with U+2018, a *left* single quotation mark, where
  U+2019 belongs; 6 strings leaking the Russian ``«…»`` into German,
  which sets ``„…“``.
* English — 662 straight double quotes against 49 curly, 245 straight
  apostrophes against 29 curly, ``Peter's`` and ``Paul’s`` in the same
  paragraph, and 6 strings whose curly quotes do not balance at all.
* Ukrainian — the same words spelled both ways: ``п’ять``/``п'ять``,
  ``ім’я``/``ім'я``, 58 typographic against 163 typewriter. Ukrainian
  orthography wants U+2019. The Russian source contains no apostrophes
  and keeps 388 balanced ``«»`` pairs, so every one of these was
  introduced in translation.

None of that is a judgement call, which is why none of it belongs in a
prompt. A model asked to follow a typographic rule follows it most of
the time, and "most of the time" is what produced the counts above. A
function follows it every time, for the same input, for free, and can
be run again over the corpus tomorrow.

Two properties make this safe to put in the pipeline's hot path:

**It never changes the length of the string.** Every rule here is a
one-character-for-one-character substitution. Nothing can be inserted,
nothing can be deleted, no span can be reordered. A bug in this module
can therefore make a character wrong; it cannot make a paragraph
disappear. ``test_a_translation_betrayed_by_its_punctuation`` pins the
invariant.

**It is idempotent.** Applying it twice equals applying it once, which
is what makes it safe to re-run over stored translations rather than
only over new ones. Every rule that could break that — mapping ``“``
onto ``„`` when ``“`` is *also* the German closing mark — is decided
from position rather than from the character alone, so a
German-correct string is already a fixed point.

Where a rule cannot be applied with certainty, the text is left alone.
A wrong normalisation is worse than none: nobody re-reads a lesson to
check that its commas survived.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from app.services.bible.books import all_canonical_slugs, display_book_name

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode


# ---------------------------------------------------------------------------
# What must never be touched
# ---------------------------------------------------------------------------

# The corpus is TipTap HTML. A chapter block carries ``<img src>``,
# ``<iframe src>``, ``class="callout callout-info"`` — and an attribute
# is delimited by exactly the straight double quote this module rewrites
# for German and Russian. Turning ``class="callout"`` into
# ``class=„callout“`` does not degrade a page, it deletes it.
#
# So markup is masked out before any rule runs, by the same linear scan
# ``core.sanitize.strip_tags`` uses and for the same reason recorded
# there: the obvious ``<[^>]+>`` backtracks quadratically on text that
# is mostly ``<``, which a teacher can paste into a lesson body, and
# CodeQL is right to flag it.
_RAW_TEXT_ELEMENTS: Final[frozenset[str]] = frozenset({"code", "pre", "script", "style", "kbd", "samp"})

# A bare URL in prose is not prose. ``https://example.com/it's-here``
# keeps its straight apostrophe: rewriting it produces a link that 404s,
# and a broken link is invisible until a student clicks it. The trailing
# lookbehind stops the match short of sentence punctuation so that the
# full stop after a URL is still ordinary text.
_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:https?://|ftp://|mailto:|www\.)[^\s<>]*(?<![.,;:!?\"'“”„«»)\]}])",
    re.IGNORECASE,
)

# ``&quot;`` and ``&#39;`` are quotes the browser will render and the
# rules here cannot read. Masked so a rule never lands inside one.
_ENTITY_RE: Final[re.Pattern[str]] = re.compile(r"&(?:#\d{1,6}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")

_TAG_NAME_RE: Final[re.Pattern[str]] = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)")


def _mask_span(free: list[bool], start: int, end: int) -> None:
    for index in range(start, min(end, len(free))):
        free[index] = False


def _mask_markup(text: str, free: list[bool]) -> None:
    """Mark every index that belongs to markup rather than to prose."""
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "<" and index + 1 < length and (text[index + 1].isalpha() or text[index + 1] in "/!"):
            end = text.find(">", index + 1)
            if end == -1:
                # Unterminated tag: the rest of the string is markup, not
                # prose. Same call ``strip_tags`` makes.
                _mask_span(free, index, length)
                return
            tag = text[index : end + 1]
            _mask_span(free, index, end + 1)
            name_match = _TAG_NAME_RE.match(tag)
            name = name_match.group(1).lower() if name_match else ""
            index = end + 1
            if name in _RAW_TEXT_ELEMENTS and not tag.startswith("</") and not tag.endswith("/>"):
                # Everything up to the closing tag is code, not prose. A
                # snippet is the one place where a straight quote is load
                # bearing.
                close = text.lower().find(f"</{name}", index)
                _mask_span(free, index, length if close == -1 else close)
                index = length if close == -1 else close
            continue
        index += 1


def _free_mask(text: str) -> list[bool]:
    """``free[i]`` is True when index ``i`` is prose a rule may rewrite."""
    free = [True] * len(text)
    _mask_markup(text, free)
    for pattern in (_URL_RE, _ENTITY_RE):
        for match in pattern.finditer(text):
            _mask_span(free, match.start(), match.end())
    return free


# ---------------------------------------------------------------------------
# Quotation marks and apostrophes
# ---------------------------------------------------------------------------

# Every character that can act as a quotation mark. Counted — not
# rewritten — to decide whether a string is safe to touch at all.
_QUOTE_CHARS: Final[frozenset[str]] = frozenset('"«»„“”')

# A quotation mark opens when what precedes it is nothing, whitespace, an
# opening bracket, a dash, or a colon. Anything else — a letter, a comma,
# a full stop — closes. Markup is transparent for this test, so ``<em>"``
# reads as a quote at the start of a sentence rather than one after ``>``.
_OPENING_CONTEXT: Final[frozenset[str]] = frozenset(
    {"", " ", "\t", "\n", "\r", "\xa0", "(", "[", "{", "—", "–", "-", "/", ":", "«", "„", "“", "‚", "‘", "*", "|", "…"}
)

# German sets its secondary quotes ``‚…‘`` — the closing mark of which is
# U+2018, the very character the genitive-apostrophe rule wants to
# rewrite. When a string contains ``‚`` we cannot tell a closed inner
# quotation from a misspelled apostrophe, so we leave every U+2018 in
# that string alone. Four occurrences in production, none of them in a
# string that quotes.
_GERMAN_SINGLE_OPEN: Final[str] = "‚"

# Characters an author may type for the Ukrainian apostrophe. Rewritten
# only between two Cyrillic letters — see ``_ukrainian_apostrophe``.
_TYPEWRITER_APOSTROPHES: Final[frozenset[str]] = frozenset("'‘`ʼ´")

_CYRILLIC_START: Final[str] = "Ѐ"
_CYRILLIC_END: Final[str] = "ӿ"


def _is_cyrillic(char: str) -> bool:
    return _CYRILLIC_START <= char <= _CYRILLIC_END


def _quotes_balance(text: str, free: list[bool]) -> bool:
    """True when the quotation marks in the prose could form pairs.

    An odd count means one of them is not a quotation mark at all — an
    inch mark, a minutes mark, half a pair the author never closed. We
    cannot tell which, so a string that does not balance keeps every
    quotation mark it has. This is the guard that stops ``5" breit``
    from becoming ``5“ breit``.
    """
    count = sum(1 for index, char in enumerate(text) if free[index] and char in _QUOTE_CHARS)
    return count > 0 and count % 2 == 0


def _german_quote(opening: bool) -> str:
    """German sets ``„…“``. Which mark to write is read off the position,
    never off the character that is already there.

    The tempting version maps character to character — ``«`` to ``„``,
    ``»`` to ``“``, ``”`` to ``“`` — and it is wrong twice over. U+201C
    *opens* in English and *closes* in German, so a table would turn the
    already-correct ``„Wort“`` into ``„Wort„`` on the second pass. And
    the seeded fuzz in the test file found the mirror of it: a ``»`` that
    happens to stand at the start of a string maps to ``“``, which then
    reads as an opening mark and maps again. Deciding from position
    alone makes a correctly-quoted string a fixed point by
    construction — an opening slot always holds ``„``, a closing slot
    always holds ``“``, and running the pass again finds both already
    there.
    """
    return "„" if opening else "“"


def _cyrillic_quote(opening: bool) -> str:
    """Russian and Ukrainian both set ``«…»``. Positional for the same
    reason as ``_german_quote``."""
    return "«" if opening else "»"


def _english_quote(char: str) -> str:
    """English is normalised to *straight* quotes, and deliberately so.

    Both directions are defensible typography; only one is a safe
    function. Going curly means deciding, for each mark, whether it
    opens or closes — an inference, and the six English strings whose
    curly quotes already fail to balance are what a wrong inference
    looks like once it is stored. Going straight is a total mapping:
    every curly form has exactly one straight counterpart, no context is
    consulted, nothing can be got backwards, and the possessive in
    ``Peter's`` is the same character as the one in ``Jesus'`` whether
    it sits inside a word or at its end.

    It is also where the corpus already is: 662 straight double quotes
    against 49 curly, 245 straight apostrophes against 29. The 49 and
    the 29 are the anomaly, and this is the cheaper direction to make
    uniform.
    """
    if char in "“”":
        return '"'
    if char in "‘’":
        return "'"
    return char


def _german_apostrophe(char: str, before: str, has_single_open: bool) -> str:
    """``Paulus‘`` → ``Paulus’``: the German apostrophe is U+2019.

    Only when the mark is welded to the end of a word, and only when the
    string contains no ``‚`` that it could be closing instead.
    """
    if char != "‘" or has_single_open or not before.isalpha():
        return char
    return "’"


def _ukrainian_apostrophe(char: str, before: str, after: str) -> str:
    """``п'ять`` → ``п’ять``.

    Between two Cyrillic letters and nowhere else. The Ukrainian
    apostrophe is always word-internal, so this test is the whole rule —
    and it is what keeps a straight quotation mark, an English
    possessive in a borrowed phrase, and anything inside a URL out of
    reach.
    """
    if char not in _TYPEWRITER_APOSTROPHES:
        return char
    if _is_cyrillic(before) and _is_cyrillic(after):
        return "’"
    return char


def _apply_character_rules(text: str, free: list[bool], out: list[str], locale: str) -> None:
    pair_quotes = _quotes_balance(text, free)
    has_single_open = any(free[index] and char == _GERMAN_SINGLE_OPEN for index, char in enumerate(text))
    previous = ""
    for index, char in enumerate(text):
        if not free[index]:
            continue
        before = text[index - 1] if index > 0 and free[index - 1] else ""
        after = text[index + 1] if index + 1 < len(text) and free[index + 1] else ""
        opening = previous in _OPENING_CONTEXT

        if locale == "en":
            out[index] = _english_quote(char)
        elif char in _QUOTE_CHARS:
            if pair_quotes:
                out[index] = _german_quote(opening) if locale == "de" else _cyrillic_quote(opening)
        elif locale == "de":
            out[index] = _german_apostrophe(char, before, has_single_open)
        elif locale == "uk":
            out[index] = _ukrainian_apostrophe(char, before, after)

        # Context for the *next* mark is what we just wrote, not what we
        # read. A straight ``"`` does not open a quotation and ``„`` does,
        # so reading the input would classify the same position
        # differently on a second pass and ``""`` would settle at ``„“``
        # once and ``„„`` the time after. Carrying the output forward
        # makes pass two see exactly what pass one saw.
        previous = out[index]


# ---------------------------------------------------------------------------
# German Bible reference punctuation
# ---------------------------------------------------------------------------

# German points a reference three ways, and all three are rules rather
# than preferences: a **comma** between chapter and verse (``Apg 8,26``),
# a **full stop** between verses of the same chapter (``Apg 8,26.30``),
# an **en dash** for a range (``Apg 8,26–40``). The Russian source uses a
# colon and a comma for the first two and a hyphen for the third, and
# that is what 94 German strings still carry.
#
# The rule fires only where there is *evidence*: a recognised German book
# name or abbreviation immediately before the numbers. Without that,
# ``10:1-23`` is a colon between two numbers and could be a score, a
# ratio, a verse count, a time — and ``18:30`` most often is. Numbers
# with no book in front of them are never touched.

# Full Luther / Loccum book names. ``books.py`` carries the RU and EN
# aliases used for *parsing* Scripture out of prose and the German
# *short* forms used for display; the long forms have never been needed
# until now, and adding them to the shared alias list would widen what
# the verse-substitution pipeline matches. They stay local.
_DE_FULL_NAMES: Final[tuple[str, ...]] = (
    "1. Mose",
    "2. Mose",
    "3. Mose",
    "4. Mose",
    "5. Mose",
    "Genesis",
    "Exodus",
    "Levitikus",
    "Numeri",
    "Deuteronomium",
    "Josua",
    "Richter",
    "Rut",
    "Ruth",
    "1. Samuel",
    "2. Samuel",
    "1. Könige",
    "2. Könige",
    "1. Chronik",
    "2. Chronik",
    "Esra",
    "Nehemia",
    "Ester",
    "Esther",
    "Hiob",
    "Ijob",
    "Psalm",
    "Psalmen",
    "Sprüche",
    "Sprichwörter",
    "Prediger",
    "Kohelet",
    "Hoheslied",
    "Hohelied",
    "Jesaja",
    "Jeremia",
    "Klagelieder",
    "Hesekiel",
    "Ezechiel",
    "Daniel",
    "Hosea",
    "Joel",
    "Amos",
    "Obadja",
    "Jona",
    "Micha",
    "Nahum",
    "Habakuk",
    "Zefanja",
    "Zephanja",
    "Haggai",
    "Sacharja",
    "Maleachi",
    "Matthäus",
    "Markus",
    "Lukas",
    "Johannes",
    "Apostelgeschichte",
    "Römer",
    "1. Korinther",
    "2. Korinther",
    "Galater",
    "Epheser",
    "Philipper",
    "Kolosser",
    "1. Thessalonicher",
    "2. Thessalonicher",
    "1. Timotheus",
    "2. Timotheus",
    "Titus",
    "Philemon",
    "Hebräer",
    "Jakobus",
    "1. Petrus",
    "2. Petrus",
    "1. Johannes",
    "2. Johannes",
    "3. Johannes",
    "Judas",
    "Offenbarung",
)

# ``Mi.`` is Micah in a reference and Mittwoch in a timetable, and
# ``Mi. 8:30`` reads perfectly as a Wednesday. One ambiguous
# abbreviation is not worth a wrongly repointed time, and the full
# ``Micha`` still matches.
_AMBIGUOUS_DE_ABBREVIATIONS: Final[frozenset[str]] = frozenset({"Mi"})

# No chapter and no verse in the canon exceeds this (Psalm 119 has 176
# verses; Psalms has 150 chapters). A larger number is a year, a price,
# or a page — not a verse — and disqualifies the whole match.
_MAX_CHAPTER_OR_VERSE: Final[int] = 176


def _de_book_aliases() -> tuple[str, ...]:
    """Every German form that may stand in front of a reference.

    Built from ``books.display_book_name`` so the abbreviations cannot
    drift from the ones the platform itself prints — the same table
    ``test_every_language_names_the_books`` keeps complete.
    """
    names: set[str] = set(_DE_FULL_NAMES)
    for slug in all_canonical_slugs():
        abbreviation = display_book_name(slug, "de")
        if abbreviation:
            names.add(abbreviation.rstrip("."))
    names -= _AMBIGUOUS_DE_ABBREVIATIONS
    # Longest first so ``1. Joh`` is preferred over ``Joh`` where both
    # could match — the same ordering ``bible/references.py`` builds its
    # pattern with, and for the same reason.
    return tuple(sorted(names, key=len, reverse=True))


_DE_REF_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w])(?:"
    + "|".join(re.escape(alias) for alias in _de_book_aliases())
    + r")\.?[ \u00a0](?P<nums>\d(?:[\d:.,–—-]|;[ ])*\d|\d)"
)

_NUM_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\d+|;[ ]|.", re.DOTALL)


def _repoint_german_numbers(nums: str) -> str | None:
    """Re-point the numeric tail of a German reference, or refuse.

    Returns a string of exactly the same length, or ``None`` when the
    tail is not a shape we are sure about — two separators in a row, a
    number too large to be a verse, a leading zero. Refusing is always
    an option here and is taken often: the cost of leaving ``10:1-23``
    alone is one inconsistent reference, and the cost of getting it
    wrong is a citation that points somewhere else.
    """
    tokens = _NUM_TOKEN_RE.findall(nums)
    out: list[str] = []
    expect_number = True
    chapter_sep_done = False
    after_dash = False
    for token in tokens:
        if token[0].isdigit():
            if not expect_number:
                return None
            if len(token) > 3 or (len(token) > 1 and token[0] == "0") or int(token) > _MAX_CHAPTER_OR_VERSE:
                return None
            out.append(token)
            expect_number = False
            continue
        if expect_number:
            # Two separators with nothing between them. Not a reference.
            return None
        if token.startswith(";"):
            # ``Apg 10,1–23; 11,3`` — a second passage of the same book.
            # The group that follows starts at a chapter again.
            out.append(token)
            chapter_sep_done = False
            after_dash = False
            expect_number = True
            continue
        if token in "-–—":
            out.append("–")
            after_dash = True
            expect_number = True
            continue
        if token in ":,.":
            # The first separator of a group joins chapter to verse, and
            # so does the one after a dash (``8,26–9,3`` crosses a
            # chapter). Every other one is separating verses of the same
            # chapter, which German sets with a full stop — this is what
            # turns the source's ``8:26,30`` into ``8,26.30`` rather than
            # into the unreadable ``8,26,30``.
            out.append("," if not chapter_sep_done or after_dash else ".")
            chapter_sep_done = True
            after_dash = False
            expect_number = True
            continue
        return None
    if expect_number:
        return None
    return "".join(out)


def _apply_german_references(text: str, free: list[bool], out: list[str]) -> None:
    for match in _DE_REF_RE.finditer(text):
        start, end = match.span("nums")
        if not all(free[index] for index in range(match.start(), end)):
            continue
        repointed = _repoint_german_numbers(match.group("nums"))
        if repointed is None or repointed == match.group("nums"):
            continue
        for offset, char in enumerate(repointed):
            out[start + offset] = char


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Every served locale is handled. ``TestEveryLanguageIsPointed`` fails
# when one is added and forgotten, which is the same guard the book-name
# table gets in ``test_every_language_names_the_books`` — a locale that
# falls through here is not a crash, it is a page that quietly keeps the
# source's punctuation.
_HANDLED_LOCALES: Final[frozenset[str]] = frozenset({"de", "en", "ru", "uk"})


def normalize_typography(text: str, locale: LocaleCode) -> str:
    """Point a finished translation the way ``locale`` is written.

    Pure: no model, no network, no database. Idempotent. Never changes
    the length of the string. Leaves markup, attributes, URLs, entities
    and code untouched.
    """
    if not text or locale not in _HANDLED_LOCALES:
        return text
    free = _free_mask(text)
    out = list(text)
    _apply_character_rules(text, free, out, locale)
    if locale == "de":
        _apply_german_references(text, free, out)
    return "".join(out)


__all__ = ["normalize_typography"]
