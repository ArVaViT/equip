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

The rest of that first count:

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

The same editor read the whole of generation 8 on 2026-08-20 — 2,452
rows, de 819 / en 815 / uk 816 — and found four things the pass above
does not do. Those are the rules added below, with the counts that
argued for each:

1. **A German book is named three ways.** ``Apostelgeschichte 1,8``
   ×48, ``Apg. 1,8`` ×40, ``Apg 1,8`` ×44; ``1. Kor. 13,4`` ×6 against
   ``1. Korinther 13,4`` ×4. 13 of 46 German lesson blocks mix at least
   two forms and one block mixes all three.
2. **Russian abbreviations survive inside German.** ``<td>Ин. 3:16</td>``
   and ``<td>1 Кор. 13</td>`` sit in German tables. A reference written
   in the source language inside a translated document is the clearest
   possible tell there is.
3. **English titles mix Title Case and sentence case** — 35 against 11
   in chapter titles, inconsistently *within* every course; the
   recurring heading ``Check Yourself`` 9 / ``Check yourself`` 14; 7 of
   44 lesson blocks disagree with themselves inside their own ``<h2>``s;
   and a chapter called ``Appendix: course materials`` is referred to
   from another chapter as ``"Appendix: Course Materials."``
4. **Dashes and apostrophes.** German: 58 em dashes against 411 en
   dashes, where the em dash is not a German glyph at all; 35 typewriter
   apostrophes in ``Paulus'``, ``Petrus'``, ``Lukas'`` against 3 correct
   ``Stephanus’``. English: 163 spaced ``—``, 37 unspaced, 1 spaced
   ``–`` — three styles, sometimes in one paragraph.

None of that is a judgement call, which is why none of it belongs in a
prompt. A model asked to follow a typographic rule follows it most of
the time, and "most of the time" is what produced the counts above. A
function follows it every time, for the same input, for free, and can
be run again over the corpus tomorrow.

What makes this safe to put in the pipeline's hot path:

**It cannot reach markup.** Tags, attributes, entities, ``<code>`` and
``<pre>`` bodies and bare URLs are masked out before any rule runs, by
the same linear scan ``core.sanitize.strip_tags`` uses. The tag stream
of the output is byte-identical to the input's, and
``test_a_translation_betrayed_by_its_punctuation`` pins that.

**It is idempotent.** Applying it twice equals applying it once, which
is what makes it safe to re-run over stored translations rather than
only over new ones. Every rule that could break that — mapping ``“``
onto ``„`` when ``“`` is *also* the German closing mark — is decided
from position rather than from the character alone, so a
German-correct string is already a fixed point.

**It edits only what it has fully parsed.** The original version of
this module could promise something stronger: that it never changed the
length of a string, because every rule was one character for one. Rules
1, 2 and 4 cannot keep that promise — ``Apostelgeschichte 1,8`` is
seventeen characters longer than ``Apg. 1,8``, ``Ин.`` is not the same
width as ``Joh.``, and putting spaces around an em dash adds two. So
the pass is now two layers with two different guarantees, and the
weaker one is stated as narrowly as it can be:

* the **character layer** (quotation marks, apostrophes, the German
  dash glyph, English title casing) is still one character for one and
  still cannot change a string's length;
* the **span layer** (the German book name and its numbers, English
  dash spacing, German thousands) replaces a span it has parsed
  end to end — a reference whose every separator it could account for,
  a dash with a word on each side, a run of digits — with the canonical
  form of that same span, and touches nothing else.

Whitespace is never deleted by either layer, so a paragraph still
cannot be swallowed; the fuzz test asserts that alongside idempotence
and the untouched tag stream.

Where a rule cannot be applied with certainty, the text is left alone.
A wrong normalisation is worse than none: nobody re-reads a lesson to
check that its commas survived.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from app.schemas.locale import QUOTATION_MARKS
from app.services.bible.books import display_book_name, find_book, written_as_a_book_name

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode
    from app.services.translation.protocol import ContentKind


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

# name, is-closing, start, end-exclusive. Collected by the same scan
# that builds the mask, because the title rule needs to know where a
# heading begins and ``<h2[^>]*>`` is the quadratic pattern all over
# again.
_Tag = tuple[str, bool, int, int]


def _mask_span(free: list[bool], start: int, end: int) -> None:
    for index in range(start, min(end, len(free))):
        free[index] = False


def _scan_markup(text: str) -> tuple[list[bool], list[_Tag]]:
    """One linear pass: which indices are prose, and where the tags are."""
    free = [True] * len(text)
    tags: list[_Tag] = []
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
                return free, tags
            tag = text[index : end + 1]
            _mask_span(free, index, end + 1)
            name_match = _TAG_NAME_RE.match(tag)
            name = name_match.group(1).lower() if name_match else ""
            if name:
                tags.append((name, tag.startswith("</"), index, end + 1))
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
    return free, tags


def _prose_mask(text: str) -> tuple[list[bool], list[_Tag]]:
    """``free[i]`` is True when index ``i`` is prose a rule may rewrite."""
    free, tags = _scan_markup(text)
    for pattern in (_URL_RE, _ENTITY_RE):
        for match in pattern.finditer(text):
            _mask_span(free, match.start(), match.end())
    return free, tags


def _free_mask(text: str) -> list[bool]:
    return _prose_mask(text)[0]


def _splice(text: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply ``(start, end, replacement)`` spans, left to right.

    The only way the span layer is allowed to write. Overlapping edits
    are dropped rather than merged — two rules that disagree about the
    same characters is a bug, and the safe reading of a bug here is to
    keep what the author wrote.
    """
    if not edits:
        return text
    edits.sort(key=lambda edit: edit[0])
    out: list[str] = []
    cursor = 0
    for start, end, replacement in edits:
        if start < cursor:
            continue
        out.append(text[cursor:start])
        out.append(replacement)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


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

# Characters an author may type for an apostrophe. Rewritten only
# between two Cyrillic letters for Ukrainian, and only welded to a word
# for German — see the two functions below.
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

    The pair itself comes from ``schemas/locale.py``, which is also
    where ``bible/substitution.py`` reads it when it puts back the marks
    a canonical verse was quoted in. Two modules deciding separately what
    a German quotation mark looks like is one module too many.
    """
    return QUOTATION_MARKS["de"][0 if opening else 1]


def _cyrillic_quote(opening: bool) -> str:
    """Russian and Ukrainian both set ``«…»``. Positional for the same
    reason as ``_german_quote``, and read from the same table."""
    return QUOTATION_MARKS["ru"][0 if opening else 1]


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

    This is the decision ``QUOTATION_MARKS["en"]`` records, so that
    ``bible/substitution.py``, restoring the marks around a canonical
    verse, writes the same mark this function would have left standing —
    and the restored quotation is a fixed point of this pass rather than
    something it immediately rewrites.

    The guillemets belong in the same mapping, and their absence used to
    show. The source is Russian and sets ``«…»``; a quotation the
    substitution layer does not recognise travels to the model as
    ordinary prose and comes back with the author's marks still on it. So
    an English lesson could hold a restored verse in ``"…"`` and the same
    verse quoted again in ``«…»`` a few lines down — the very
    inconsistency the restoration exists to end. ``„`` is here for the
    same reason from the German direction. Straightening them is one
    character for one, like every other rule in this module, and cannot
    be got backwards.
    """
    if char in "“”«»„":
        return '"'
    if char in "‘’‚":
        return "'"
    return char


def _german_apostrophe_allowed(text: str, free: list[bool]) -> bool:
    """Whether this string's single marks can be read as apostrophes.

    Two ways they cannot. ``‚`` opens a German inner quotation and
    ``‘`` closes it, so one of those in the string makes every ``‘``
    ambiguous. And a straight ``'`` standing *before* a word rather than
    after one is somebody setting an English-style single quotation in
    German prose — ``'Wort'`` — where the second mark closes a pair and
    is not a genitive at all.

    Either way the answer is to leave the whole string's single marks
    where they are. 35 German strings carry a typewriter apostrophe
    welded to a name; none of them also quotes.
    """
    opening_run = False
    for index, char in enumerate(text):
        if not free[index]:
            continue
        if char == _GERMAN_SINGLE_OPEN:
            return False
        if char in _TYPEWRITER_APOSTROPHES or char == "’":
            before = text[index - 1] if index > 0 else ""
            after = text[index + 1] if index + 1 < len(text) else ""
            if not before.isalpha() and after.isalpha():
                opening_run = True
    return not opening_run


def _german_apostrophe(char: str, before: str) -> str:
    """``Paulus‘`` and ``Paulus'`` → ``Paulus’``.

    The German apostrophe is U+2019 and it is welded to the end of the
    word it belongs to — the genitive of a name that already ends in an
    s-sound (``Paulus’ Brief``, ``Petrus’ Wort``, ``Lukas’ Bericht``)
    and the elisions (``wie geht’s``). Both shapes are "letter, then
    mark", which is the whole test; the caller has already established
    with ``_german_apostrophe_allowed`` that no mark in this string is
    quoting instead.
    """
    if char not in _TYPEWRITER_APOSTROPHES or not before.isalpha():
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


def _apply_quote_rules(text: str, free: list[bool], out: list[str], locale: str) -> None:
    pair_quotes = _quotes_balance(text, free)
    apostrophes_allowed = locale == "de" and _german_apostrophe_allowed(text, free)
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
            if apostrophes_allowed:
                out[index] = _german_apostrophe(char, before)
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
# Dashes
# ---------------------------------------------------------------------------

# The em dash is not a German glyph. German sets a parenthetical with a
# *Gedankenstrich*, which is an en dash, and a range with the same en
# dash unspaced — 411 of the German rows already have it and 58 carry an
# em dash the source or the model brought in.
#
# Only the glyph is swapped, never the spacing around it. ``Wort—Wort``
# becomes ``Wort–Wort`` and not ``Wort – Wort``: an unspaced en dash is
# also how German joins a range, so the spacing carries meaning we
# cannot recover from the character alone, and guessing at it is exactly
# the kind of edit nobody would re-read.
_GERMAN_WRONG_DASH: Final[str] = "—"
_GERMAN_RIGHT_DASH: Final[str] = "–"


def _apply_german_dashes(text: str, free: list[bool], out: list[str]) -> None:
    for index, char in enumerate(text):
        if free[index] and char == _GERMAN_WRONG_DASH:
            out[index] = _GERMAN_RIGHT_DASH


# English keeps the em dash — that is the glyph English uses — and the
# argument is only about the spaces. The corpus votes 163 spaced against
# 37 unspaced and 1 lone spaced en dash, so spaced em dash wins on
# count; it is also the house style of every web publication this
# reads like, where the unspaced form belongs to print.
#
# The rule fires only on a dash with a word character hard on each side
# (allowing one ordinary space), which is the parenthetical use and
# nothing else. What that deliberately excludes: a hyphen, which is
# never touched at all; a dash opening a line or a list item, which has
# no word to its left; a dash against a quotation mark, ``"I—"``, where
# the interruption is the point; and any dash with digits on both sides,
# because ``1914–1918`` and ``Acts 8:26–40`` are ranges and a range is
# set tight in every English style there is.
_EN_DASH_RE: Final[re.Pattern[str]] = re.compile(r"(?<=\w) ?[–—] ?(?=\w)")
_EN_SPACED_DASH: Final[str] = " — "


def _space_english_dashes(text: str) -> str:
    free = _free_mask(text)
    edits: list[tuple[int, int, str]] = []
    for match in _EN_DASH_RE.finditer(text):
        start, end = match.span()
        if not all(free[index] for index in range(start, end)):
            continue
        if text[start - 1].isdigit() and text[end].isdigit():
            continue
        if match.group() != _EN_SPACED_DASH:
            edits.append((start, end, _EN_SPACED_DASH))
    return _splice(text, edits)


# ---------------------------------------------------------------------------
# English titles and headings
# ---------------------------------------------------------------------------

# Title Case, and the reason is not the count — though the count agrees,
# 35 Title Case chapter titles against 11 sentence case, and the one
# broken cross-reference in the corpus quotes the Title Case form of a
# title that is stored in sentence case. The reason is that Title Case
# is the only direction that is a *safe* function.
#
# Going to sentence case means lower-casing words, and a machine that
# lower-cases cannot tell ``Currents and Ministries`` from ``Paul's
# Letters`` or ``The Holy Spirit``: it would have to know which capitals
# are proper nouns, and getting that wrong writes ``paul`` into a
# chapter title. Going to Title Case only ever *raises* a word that is
# already lower case, plus lowers members of one closed list of function
# words — and no word on that list is ever a proper noun. The worst a
# bug here can do is capitalise a common noun, which is a style you
# might disagree with. The worst the other direction can do is
# misspell a name.
#
# Short words stay lower unless they are first, last, or the first word
# after a colon or a sentence end. The list is fixed here rather than
# derived, because "preposition" is not something this module can
# decide.
_SMALL_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "from",
        "if",
        "in",
        "into",
        "nor",
        "of",
        "off",
        "on",
        "onto",
        "or",
        "over",
        "per",
        "so",
        "the",
        "to",
        "up",
        "upon",
        "via",
        "vs",
        "with",
        "yet",
    }
)

# What makes the next word a "first" word again. Quotation marks are
# deliberately absent: the character layer rewrites those, and a rule
# that reads a character another rule is rewriting decides differently
# on the second pass.
_CAPITALISE_AFTER: Final[frozenset[str]] = frozenset({":", ".", "?", "!", ";", "(", "["})

_HEADING_TAGS: Final[frozenset[str]] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

_APOSTROPHE_IN_WORD: Final[frozenset[str]] = frozenset("'’ʼ`´")


def _heading_spans(tags: list[_Tag]) -> list[tuple[int, int]]:
    """The prose inside each ``<h1>``…``<h6>``.

    A heading that is never closed contributes nothing: without the
    closing tag there is no way to say where the title stops and the
    lesson starts, and title-casing a paragraph is the one outcome this
    rule must never have.
    """
    spans: list[tuple[int, int]] = []
    opened: tuple[str, int] | None = None
    for name, closing, start, end in tags:
        if name not in _HEADING_TAGS:
            continue
        if not closing:
            opened = (name, end)
        elif opened is not None and opened[0] == name:
            if opened[1] < start:
                spans.append((opened[1], start))
            opened = None
    return spans


def _title_words(text: str, free: list[bool], start: int, end: int) -> list[tuple[list[int], bool]]:
    """Split a title span into words, each flagged "starts a new phrase".

    A word is a run of letters, digits and in-word apostrophes. Digits
    are part of the run on purpose so that ``1st`` and ``5`` come out as
    one token each and can be skipped whole — a run of letters alone
    would see ``st`` and capitalise it.
    """
    words: list[tuple[list[int], bool]] = []
    current: list[int] = []
    fresh = True
    for index in range(start, end):
        char = text[index]
        if free[index] and (char.isalnum() or char in _APOSTROPHE_IN_WORD):
            current.append(index)
            continue
        if current:
            words.append((current, fresh))
            fresh = False
            current = []
        if char in _CAPITALISE_AFTER:
            fresh = True
    if current:
        words.append((current, fresh))
    return words


def _capitalised_inside(text: str, indices: list[int], head: int) -> bool:
    """Whether the word carries a capital anywhere but the front.

    ``THE``, ``McCoy``, ``iPhone``, ``eBay``. Every one of them was
    spelled that way on purpose, and every one of them comes out wrong
    if only the first letter is touched — ``tHE``, ``mcCoy``,
    ``IPhone``, ``EBay``. So a word shaped like that is not this rule's
    to change in either direction.
    """
    return any(text[index].isupper() for index in indices if index != head)


def _raise_initial(text: str, out: list[str], indices: list[int], head: int) -> None:
    """Upper-case a word's initial, or decline.

    ``str.upper`` is not length-preserving for every character in
    Unicode — German ``ß`` becomes ``SS`` — and this layer's whole claim
    is that it is. A character that does not have a one-character upper
    case is left as it stands.
    """
    if _capitalised_inside(text, indices, head):
        return
    upper = out[head].upper()
    if len(upper) == 1 and upper != out[head]:
        out[head] = upper


def _lower_small_word(text: str, out: list[str], indices: list[int], head: int) -> None:
    """Lower-case the initial of a function word, unless it is shouting."""
    if _capitalised_inside(text, indices, head):
        return
    lower = out[head].lower()
    if len(lower) == 1 and lower != out[head]:
        out[head] = lower


def _title_case_span(text: str, free: list[bool], out: list[str], start: int, end: int) -> None:
    words = _title_words(text, free, start, end)
    for position, (indices, fresh) in enumerate(words):
        if any(text[index].isdigit() for index in indices):
            continue
        letters = [index for index in indices if text[index].isalpha()]
        if not letters:
            continue
        head = letters[0]
        word = "".join(text[index] for index in indices).strip("".join(_APOSTROPHE_IN_WORD)).lower()
        is_last = position == len(words) - 1
        if fresh or is_last or word not in _SMALL_WORDS:
            _raise_initial(text, out, indices, head)
        else:
            _lower_small_word(text, out, indices, head)


def _apply_english_titles(
    text: str,
    free: list[bool],
    tags: list[_Tag],
    out: list[str],
    content_kind: ContentKind | None,
) -> None:
    """Title-case the titles and nothing else.

    Two things are a title and there is no third: a field the registry
    translates as ``content_kind="title"`` — a course, module, chapter,
    quiz or assignment name, which is the whole string — and the text
    inside a heading element of an HTML block. Prose is not reachable
    from either, which is the point: the same words that read as a
    heading read as a sentence one line down, and Title Case in a
    paragraph is worse than the inconsistency it fixes.
    """
    if content_kind == "title":
        _title_case_span(text, free, out, 0, len(text))
        return
    for start, end in _heading_spans(tags):
        _title_case_span(text, free, out, start, end)


# ---------------------------------------------------------------------------
# German Bible references: the book's name and its numbers
# ---------------------------------------------------------------------------

# German points a reference three ways, and all three are rules rather
# than preferences: a **comma** between chapter and verse (``Apg 8,26``),
# a **full stop** between verses of the same chapter (``Apg 8,26.30``),
# an **en dash** for a range (``Apg 8,26–40``). The Russian source uses a
# colon and a comma for the first two and a hyphen for the third, and
# that is what 94 German strings still carry.
#
# It also names the book one way, and that is the choice this module now
# makes for it: **the abbreviated form with the period**, ``Apg. 1,8``,
# ``1. Kor. 13,4``, ``Joh. 3,16``. Three arguments, in the order they
# matter:
#
# 1. It is what the platform itself prints. ``display_book_name`` is
#    already the form ``bible/substitution.py`` renders next to every
#    canonically quoted verse, so choosing it means the citation the
#    model wrote and the citation our own code wrote converge instead of
#    sitting three lines apart in two spellings. Anything else would
#    need the display table changed too.
# 2. It is what a German Bible prints in a citation. The Luther edition
#    the platform quotes from sets ``Apg.`` in its own cross-references.
# 3. It is the form that cannot be mistaken for prose, which matters
#    because prose legitimately spells the book out: "Die
#    Apostelgeschichte erzählt…" is a sentence about a book, not a
#    citation, and rewriting it would be a straightforward error.
#
# So a name is only ever rewritten when the numbers behind it prove it
# is a citation, and "prove" is graded by how much evidence the form
# itself already carries:
#
# * A name written in **Cyrillic** — ``Ин. 3:16``, ``1 Кор. 13`` sitting
#   in a German table — needs only a chapter. There is no reading in
#   which a Cyrillic word followed by a number is German prose, and a
#   reference left in the source language is the single most obvious
#   tell a translated page can carry.
# * A name written in **German** needs a chapter *and a verse*.
#   ``Apostelgeschichte 8`` is as likely to be the subject of a sentence
#   ("Apostelgeschichte 8 erzählt davon") as a citation, and the
#   counts the editor took are all chapter-and-verse. A chapter on its
#   own is left as it stands.
# * A German name directly after an article — ``die
#   Apostelgeschichte 1,8`` — is left alone as well, because ``die Apg.
#   1,8`` is not something anybody would write.
#
# Everything is settled by ``bible/books.py``, which reads Russian,
# English, German and Ukrainian names and writes any of them. Building
# the list here from anything else would give the platform two tables to
# keep in step.

# ``Mi.`` is Micah in a reference and Mittwoch in a timetable, and
# ``Mi. 8:30`` reads perfectly as a Wednesday. One ambiguous
# abbreviation is not worth a wrongly repointed time, and the full
# ``Micha`` still matches.
_AMBIGUOUS_DE_ABBREVIATIONS: Final[frozenset[str]] = frozenset({"mi"})

# ``die Apostelgeschichte 1,8`` is a noun phrase with a number after it,
# not a citation, and the abbreviation would read as a mistake there.
# Determiners only — a preposition ("in Apostelgeschichte 1,8") is
# exactly where the abbreviation belongs.
_DE_DETERMINERS: Final[frozenset[str]] = frozenset(
    {
        "der",
        "die",
        "das",
        "den",
        "dem",
        "des",
        "ein",
        "eine",
        "einer",
        "eines",
        "einem",
        "einen",
        "dieser",
        "diese",
        "dieses",
        "diesem",
        "diesen",
        "jener",
        "jene",
        "jenes",
        "seine",
        "seiner",
        "ihre",
        "ihrer",
        "unsere",
    }
)

# No chapter and no verse in the canon exceeds this (Psalm 119 has 176
# verses; Psalms has 150 chapters). A larger number is a year, a price,
# or a page — not a verse — and disqualifies the whole match.
_MAX_CHAPTER_OR_VERSE: Final[int] = 176

# One word of a printed book name: either an ordinal ("1", "1.") or a
# word that may carry an apostrophe (``Об'явлення``), a hyphen, and a
# trailing abbreviation dot. Up to four of them are captured, which
# covers the longest name any of the four languages prints (``Пісня над
# піснями``) with room for the words in front of it that the scan then
# drops one at a time.
_DE_BOOK_WORD: Final[str] = r"(?:[1-5]\.?|[^\W\d_](?:[^\W\d_]|['’ʼ`\-])*\.?)"

_DE_REFERENCE_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?<![\w.])(?P<book>{_DE_BOOK_WORD}(?:[  ]{_DE_BOOK_WORD}){{0,3}})"
    rf"[  ](?P<nums>\d(?:[\d:.,–—-]|;[ ])*\d|\d)"
)

_NUM_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\d+|;[ ]|.", re.DOTALL)


def _repoint_german_numbers(nums: str) -> str | None:
    """Re-point the numeric tail of a German reference, or refuse.

    Returns ``None`` when the tail is not a shape we are sure about —
    two separators in a row, a number too large to be a verse, a leading
    zero. Refusing is always an option here and is taken often: the cost
    of leaving ``10:1-23`` alone is one inconsistent reference, and the
    cost of getting it wrong is a citation that points somewhere else.

    A refusal disqualifies the *whole* match, name included. Being
    unsure the numbers are a reference is being unsure the word in front
    of them is a book, and ``Apg 8:2026`` keeps both its spelling and
    its colon for that reason.
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


def _book_candidates(book: str) -> list[tuple[int, str]]:
    """``(offset, form)`` for the captured words, longest first.

    The pattern cannot know where the words in front of the book end, so
    it captures up to four and this drops them one at a time. Longest
    first because ``1. Korinther`` must be preferred over ``Korinther``,
    which is not a name any language prints on its own.
    """
    candidates = [(0, book)]
    for match in re.finditer(r"[  ]+", book):
        start = match.end()
        if start < len(book):
            candidates.append((start, book[start:]))
    return candidates


def _resolve_book(book: str) -> tuple[int, str, str] | None:
    """The longest suffix of ``book`` that is a book name: offset, form, slug."""
    for offset, form in _book_candidates(book):
        if form.strip().rstrip(".").lower() in _AMBIGUOUS_DE_ABBREVIATIONS:
            continue
        if not written_as_a_book_name(form):
            continue
        slug = find_book(form, "de")
        if slug is not None:
            return offset, form, slug
    return None


def _preceding_word(book: str, offset: int) -> str:
    head = book[:offset].split()
    return head[-1] if head else ""


def _may_rename(form: str, repointed: str, book: str, offset: int) -> bool:
    """Whether the evidence is strong enough to rewrite the book's name."""
    if any(_is_cyrillic(char) for char in form):
        # A Cyrillic name in German text is wrong whatever follows it;
        # a chapter number is only needed to know it is a citation.
        return True
    if "," not in repointed:
        # No verse. ``Apostelgeschichte 8`` may well be a sentence.
        return False
    return _preceding_word(book, offset).lower() not in _DE_DETERMINERS


def _normalize_german_references(text: str) -> str:
    free = _free_mask(text)
    edits: list[tuple[int, int, str]] = []
    for match in _DE_REFERENCE_RE.finditer(text):
        num_start, num_end = match.span("nums")
        if not all(free[index] for index in range(match.start("book"), num_end)):
            continue
        nums = match.group("nums")
        repointed = _repoint_german_numbers(nums)
        if repointed is None:
            continue
        resolved = _resolve_book(match.group("book"))
        if resolved is None:
            continue
        offset, form, slug = resolved
        canonical = display_book_name(slug, "de")
        if canonical is not None and canonical != form and _may_rename(form, repointed, match.group("book"), offset):
            name_start = match.start("book") + offset
            edits.append((name_start, name_start + len(form), canonical))
        if repointed != nums:
            edits.append((num_start, num_end, repointed))
    return _splice(text, edits)


# ---------------------------------------------------------------------------
# German thousands
# ---------------------------------------------------------------------------

# ``3.000 Menschen`` and ``3000`` in the same quiz, describing the same
# crowd. German groups thousands with a full stop, so ``3.000`` is
# already right and ``3000`` is the one to fix — the direction matters,
# because ungrouping would be making German text less German to buy
# consistency.
#
# The exception that keeps this honest is the year. German writes
# ``1517`` and ``2026`` without a separator, always, and a four-digit
# number in that range is far more likely to be one than a count. So
# 1000–2099 is left alone in full, and with it every year this corpus
# can plausibly mention. What is left — 2300 evenings, 3000 at Pentecost,
# 5000 fed, 144000 sealed — is grouped the way a German Bible prints it.
#
# Everything adjacent to a digit, a separator, a dash or a slash is out
# of reach, which is what keeps the rule off verse numbers, decimals,
# ranges, ratios and ports.
_DE_THOUSANDS_RE: Final[re.Pattern[str]] = re.compile(r"(?<![\d.,:/%–—-])\d{4,6}(?![\d.,:/%–—-])")
_DE_YEAR_RANGE: Final[range] = range(1000, 2100)


def _group_german_thousands(text: str) -> str:
    free = _free_mask(text)
    edits: list[tuple[int, int, str]] = []
    for match in _DE_THOUSANDS_RE.finditer(text):
        start, end = match.span()
        if not all(free[index] for index in range(start, end)):
            continue
        value = int(match.group())
        if value in _DE_YEAR_RANGE:
            continue
        edits.append((start, end, f"{value:,}".replace(",", ".")))
    return _splice(text, edits)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Every served locale is handled. ``TestEveryLanguageIsPointed`` fails
# when one is added and forgotten, which is the same guard the book-name
# table gets in ``test_every_language_names_the_books`` — a locale that
# falls through here is not a crash, it is a page that quietly keeps the
# source's punctuation.
_HANDLED_LOCALES: Final[frozenset[str]] = frozenset({"de", "en", "ru", "uk"})


def normalize_characters(text: str, locale: LocaleCode, content_kind: ContentKind | None = None) -> str:
    """The half of the pass that is one character for one.

    Exported for the test that pins the length invariant on it. The
    span layer above cannot hold that invariant and does not claim to.
    """
    free, tags = _prose_mask(text)
    out = list(text)
    _apply_quote_rules(text, free, out, locale)
    if locale == "de":
        _apply_german_dashes(text, free, out)
    elif locale == "en":
        _apply_english_titles(text, free, tags, out, content_kind)
    return "".join(out)


def normalize_typography(
    text: str,
    locale: LocaleCode,
    content_kind: ContentKind | None = None,
) -> str:
    """Point a finished translation the way ``locale`` is written.

    Pure: no model, no network, no database. Idempotent. Leaves markup,
    attributes, URLs, entities and code untouched. ``content_kind`` is
    the caller's own description of the string — only ``"title"`` is
    consulted, and only for English, to know that the whole string is a
    heading rather than a paragraph.

    The stages are ordered rather than independent. The German name has
    to be settled before the numbers, because ``Ин. 3:16`` is a Russian
    abbreviation *and* a Russian colon and fixing only the second leaves
    ``Joh. 3:16`` — half-translated, which reads worse than untouched.
    """
    if not text or locale not in _HANDLED_LOCALES:
        return text
    result = normalize_characters(text, locale, content_kind)
    if locale == "de":
        result = _normalize_german_references(result)
        result = _group_german_thousands(result)
    elif locale == "en":
        result = _space_english_dashes(result)
    return result


__all__ = ["normalize_characters", "normalize_typography"]
