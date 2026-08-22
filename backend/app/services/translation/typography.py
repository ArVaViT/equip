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

**Every rule argues from evidence, and the shape of the text is not
evidence on its own.** That is the correction of 2026-08-20, and it came
from reading what this module does to German that is not about the
Bible. German writes its decimal separator as a comma and most German
book names are ordinary German nouns or ordinary German first names, so
``Markus 5,3 Millionen Euro`` was being republished as ``Mk. 5,3
Millionen Euro``; four to six digits is the shape of every postal code
and error code, so ``Postleitzahl 46032`` became ``46.032``; and English
Title Case was retyping ``git rebase -i`` as ``Git Rebase -I``, which is
a different command. Every one of those edits ships in the reader's own
language with its digits intact, so nothing downstream can see it.

Three courses are biblical today and the ones coming are not, so the
answer is not a list of words to avoid — it is that each rule now names
what would have to be true before it may act, and refuses when it is not:

* a book is renamed only on Cyrillic script, German's own abbreviation,
  a leading ordinal, or brackets holding nothing but the reference;
* a number is grouped only when a capitalised German noun or a unit sign
  follows it — a count is followed by what it counts, an identifier
  counts nothing;
* a title word is raised only when it is not part of a command line, a
  path, a file name or a backticked span.

Each of those costs something, and the cost is written down beside the
rule.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple

from app.schemas.locale import QUOTATION_MARKS, LanguageNotInTable
from app.services.bible.books import (
    display_book_name,
    find_book,
    find_book_written_in,
    written_as_a_book_name,
)

if TYPE_CHECKING:
    from collections.abc import Callable

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

# A backtick pair is what an author writes when there is no ``<code>``
# element to hand — in a chapter title, in a quiz option, in a sentence
# of prose. Inside it is code, and code is where a straight quote, a
# hyphen and a lower-case initial are all load bearing.
#
# The boundary test is what keeps this off the languages that type an
# apostrophe as a backtick: ``п`ять … ім`я`` has a letter welded to both
# marks, so neither opens a span, and the Ukrainian rule still gets to
# fix them. A span opens only where prose does not put an apostrophe —
# after a space or a bracket — and closes the same way.
_BACKTICK_SPAN_RE: Final[re.Pattern[str]] = re.compile(r"(?<!\w)`[^`\n]*`(?!\w)")

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
    for pattern in (_URL_RE, _ENTITY_RE, _BACKTICK_SPAN_RE):
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

# Whitespace, and the absence of any character at all. Named because
# two rules below need exactly this set: a quotation mark opens after
# it, and — see ``_opens_quotation`` — a dash is punctuation rather than
# part of a word when it stands after it.
_WHITESPACE_CONTEXT: Final[frozenset[str]] = frozenset({"", " ", "\t", "\n", "\r", "\xa0"})

# The three dashes. They belong to the opening set below, and they are
# the one entry in it that does not settle the question on its own.
#
# A dash *standing as punctuation* does open a quotation — the dialogue
# dash German and Ukrainian both set, ``— „Komm her“``, and the
# parenthetical ``Der Weg – „der schmale“ – endet hier``. A dash *welded
# to the word in front of it* is not punctuation at all: it is a hyphen,
# and the word it belongs to has simply been cut short. Production,
# 2026-08-21, a German lesson on looking a word up by its stem:
#
#     nicht nach dem häufigen: „Senf-“, nicht „Korn“.
#
# ``„Senf-“`` is a truncated word in quotation marks, which is ordinary
# German. The mark after the hyphen *closes* it — and the pass, reading
# the hyphen and nothing else, wrote ``„Senf-„``: an opening mark where
# a quotation ends, in the reader's own language, on the one line of the
# lesson that shows what to type into a concordance.
#
# One more character of context separates the two, and it is the
# character before the dash. Punctuation stands apart from the word in
# front of it; a hyphen is welded to it. So a dash opens a quotation
# only when whitespace — or the start of the block — precedes the dash
# itself.
#
# The tempting larger answer is to carry a *depth*: a quotation already
# open must close before another can open, which settles ``„Senf-“``
# without looking at the hyphen at all. It was measured over the live
# catalogue on 2026-08-21 and it is wrong, for a reason that has nothing
# to do with dashes: **depth cannot read a nested quotation**. German
# and Ukrainian both set an inner quotation in the same characters as
# the outer one, and the catalogue has them —
#
#     „(Dem Vorsänger, nach: „Hirschkuh der Morgenröte“. Ein Psalm…)“
#     «Чи справді Бог сказав: «Не їжте плодів…»?»
#
# — where alternating on a count turns the inner opening mark into a
# closing one and the inner closing mark into an opening one. The
# context rule reads both correctly, because ``: `` opens and a letter
# closes whatever the count says. Replacing it with depth repaired 30
# rows of one defect and broke 4 nested quotations; used only as a
# tie-break for dashes it repaired 3 rows and still carried the state.
# Neither is worth a cascade: a mistake in a positional rule stays in
# the character it was made on, while a mistake in a counted one
# inverts every mark after it in the block.
_DASH_CONTEXT: Final[frozenset[str]] = frozenset({"—", "–", "-"})

# A colon and an ellipsis are *not* in the set below, and the reason is
# worth stating because both look like they belong there.
#
# A colon does introduce a quotation — ``Er sagte: „Wort“`` — but every
# language this module points writes that colon with a **space** after
# it, and when the space is there the space is what the rule reads. The
# colon itself is therefore only ever consulted in the one shape where
# it is welded to the mark, ``sprach:„``, and that shape is not a
# quotation being introduced. It is a quotation being *closed* around a
# verse that happens to end in a colon:
#
#     2. Mose 20,1 besagt: „Und Gott redete alle diese Worte und sprach:„
#     Вихід 20:1 свідчить: «І глаголав Господь всї словеса оцї, глаголючи:«
#
# The same holds for the ellipsis a truncated verse ends in, ``Wort…„``.
# Counted over the whole catalogue on 2026-08-21: 34 quotation marks
# stand welded to a colon or an ellipsis, and by meaning every one of
# them closes. 28 were written as opening marks, in live German and
# Ukrainian rows, so the reader met a quotation that never visually
# ends. The other 6 are Russian, where the source already had the right
# mark — and the pass would have overwritten it with the wrong one the
# next time the row was touched, which is what makes this a live bug
# and not only a repair.
#
# So: a quotation mark opens when what precedes it is nothing,
# whitespace, an opening bracket, or a dash. Anything else — a letter, a
# comma, a full stop, a colon, an ellipsis — closes. Markup is
# transparent for this test, so ``<em>"`` reads as a quote at the start
# of a sentence rather than one after ``>``. The dashes are named
# separately above and composed in here so that the set and its one
# qualification cannot drift apart.
_OPENING_CONTEXT: Final[frozenset[str]] = (
    _WHITESPACE_CONTEXT | _DASH_CONTEXT | frozenset({"(", "[", "{", "/", "«", "„", "“", "‚", "‘", "*", "|"})
)

# Characters that cannot *begin* quoted text, and so cannot stand behind
# an opening mark. Read on one side of one branch — see
# ``_opens_quotation`` — never as a rule of its own.
#
# The tempting version applies this to every mark: an opening mark is
# welded to the text it introduces, so a mark followed by a space is
# closing. It was measured and it is wrong, on a live Ukrainian row that
# is currently *right*:
#
#     формулювати принцип « угодно Святому Духу і нам» як модель
#
# The stray space after ``«`` is sloppy, not a mis-pointed mark, and a
# general lookahead would answer it by turning an opening mark into a
# closing one — trading a cosmetic flaw for a real error. What precedes
# a mark stays the evidence; what follows is consulted only where the
# preceding character has already failed to settle the question.
_CANNOT_BEGIN_QUOTED_TEXT: Final[frozenset[str]] = _WHITESPACE_CONTEXT | frozenset(
    {",", ".", ";", "!", "?", ")", "]", "}"}
)

# A new block is a new place to start, and the character before it is not
# evidence about the character after it.
#
# The opening test reads what precedes a mark, and markup is transparent
# to it — which is right inside a paragraph (``<em>"`` opens a quotation)
# and wrong across one. A verse quoted in its own ``<blockquote>`` is
# preceded, in prose terms, by the full stop that ended the paragraph
# above; a full stop closes, so the mark that opened the quotation was
# written as a closing mark, and the one that closed it was written as a
# closing mark too.
#
# Production, 2026-08-20, a walkthrough written to look at exactly this:
# German served ``“Doch weil ihr…habt.“`` and Ukrainian ``»А як ви…
# веселитися»`` — the closing mark at both ends, in both languages, on
# the one line of a Bible lesson that is Scripture. The same sentence
# inside a paragraph came back correctly pointed, which is what made it
# visible: two shapes of the same quotation, one right and one wrong,
# decided by which side of a ``</p>`` it fell.
_BLOCK_ELEMENTS: Final[frozenset[str]] = frozenset(
    {
        "p",
        "div",
        "blockquote",
        "section",
        "article",
        "aside",
        "figure",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "br",
        "hr",
        "pre",
        "header",
        "footer",
        "main",
        "nav",
    }
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


def _opens_quotation(previous: str, before_previous: str, after: str) -> bool:
    """True when a quotation mark in this position is an opening one.

    ``previous`` is the character before the mark, ``before_previous``
    the one before that, ``after`` the one behind it — all as *written*
    by this pass, all empty where prose stops, and the outer two empty
    at the start of a block.

    ``previous`` decides on its own for every character but a dash. A
    dash is the one entry in ``_OPENING_CONTEXT`` that is ambiguous, so
    it is the one branch that reads its neighbours: the dash must stand
    apart from the word in front of it (or it is a hyphen, and ``„Senf-“``
    closes), and the mark must be welded to the text it would introduce
    (or there is no quotation for it to open, and ``auf meine Klage. –„``
    closes too). Both halves are the same principle — adjacency binds —
    read on the two sides of the same dash.
    """
    if previous in _DASH_CONTEXT:
        return before_previous in _WHITESPACE_CONTEXT and after not in _CANNOT_BEGIN_QUOTED_TEXT
    return previous in _OPENING_CONTEXT


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


def _marks_for(locale: LocaleCode) -> tuple[str, str]:
    """The pair ``locale`` sets a quotation in — and the only place this
    pass is allowed to learn it.

    Which mark to write is read off the *position*, never off the
    character that is already there. The tempting version maps character
    to character — ``«`` to ``„``, ``»`` to ``“``, ``”`` to ``“`` — and
    it is wrong twice over. U+201C *opens* in English and *closes* in
    German, so a table would turn the already-correct ``„Wort“`` into
    ``„Wort„`` on the second pass. And the seeded fuzz in the test file
    found the mirror of it: a ``»`` that happens to stand at the start of
    a string maps to ``“``, which then reads as an opening mark and maps
    again. Deciding from position alone makes a correctly-quoted string a
    fixed point by construction — an opening slot always holds the
    opening mark, a closing slot the closing one, and running the pass
    again finds both already there.

    The pair comes from ``schemas/locale.py``, which is also where
    ``bible/substitution.py`` reads it when it puts back the marks a
    canonical verse was quoted in. Two modules deciding separately what
    a German quotation mark looks like is one module too many — and it
    is why this asks the table by locale instead of branching on the
    locale by hand. The branch used to end in ``else: set it in «…»``,
    so a language nobody had written a rule for was quietly pointed like
    Russian, and every one of the module's own guards was satisfied by
    that: the string did change, it just changed into the wrong
    language's punctuation.
    """
    marks = QUOTATION_MARKS.get(locale)
    if marks is None:
        raise LanguageNotInTable(
            f"No quotation marks are recorded for {locale!r}, so this pass cannot "
            "point a translation into it. Add the pair to ``QUOTATION_MARKS`` in "
            "``app/schemas/locale.py`` — the same table ``bible/substitution.py`` "
            "reads, so the restored verse and the paraphrase beside it end up in "
            "the same marks. Naming the language somewhere is not enough: the "
            "marks are the rule."
        )
    return marks


def _english_apostrophe(char: str, before: str, after: str) -> str:
    """English is normalised to *straight* marks, and deliberately so.

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

    Only the *single* marks are decided here now. The double ones are
    the ordinary quotation path — ``QUOTATION_MARKS["en"]`` is a pair of
    the same character, and a language whose two marks are identical
    needs no reasoning about which slot a mark sits in. That equality is
    what "English is straight" means, said once in the table both this
    module and ``bible/substitution.py`` read, rather than twice.
    """
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


def _german_apostrophe(char: str, before: str, after: str) -> str:
    """``Paulus‘`` and ``Paulus'`` → ``Paulus’``.

    The German apostrophe is U+2019 and it is welded to the end of the
    word it belongs to — the genitive of a name that already ends in an
    s-sound (``Paulus’ Brief``, ``Petrus’ Wort``, ``Lukas’ Bericht``)
    and the elisions (``wie geht’s``). Both shapes are "letter, then
    mark", which is the whole test; the caller has already established
    with ``_german_apostrophe_allowed`` that no mark in this string is
    quoting instead.

    ``after`` goes unread — German's rule looks only backwards. The
    signature is the one every language's rule takes, so that
    ``_APOSTROPHE_RULES`` can hold them side by side and the caller
    never has to know which language it is holding.
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


def _anywhere(text: str, free: list[bool]) -> bool:
    """Most languages' apostrophe rule needs no whole-string permission."""
    return True


class _Apostrophe(NamedTuple):
    """What one language does with a single mark, and when it may.

    ``write`` decides one character from its neighbours. ``permitted``
    is asked once per string, for the languages where a single mark can
    be quoting instead of eliding and the whole string has to be left
    alone — German, and so far only German.
    """

    write: Callable[[str, str, str], str]
    permitted: Callable[[str, list[bool]], bool] = _anywhere


#: The single mark, per language. This is the table that used to be a
#: frozenset of locale codes, and the difference is the point of the
#: change: a name in a set proved that somebody had thought of the
#: language, not that anything here knew what to do with it. An entry
#: costs a function; membership cost a word.
#:
#: ``None`` is an entry and not a hole — Russian sets no apostrophe, and
#: recording that is what tells the next reader it was decided rather
#: than missed. A language absent altogether is refused by
#: ``_apostrophe_for``, where it used to fall past the end of an
#: if/elif chain and be pointed like Russian.
_APOSTROPHE_RULES: Final[dict[LocaleCode, _Apostrophe | None]] = {
    "ru": None,
    "uk": _Apostrophe(_ukrainian_apostrophe),
    "de": _Apostrophe(_german_apostrophe, _german_apostrophe_allowed),
    "en": _Apostrophe(_english_apostrophe),
}


def _apostrophe_for(locale: LocaleCode) -> _Apostrophe | None:
    if locale not in _APOSTROPHE_RULES:
        raise LanguageNotInTable(
            f"No apostrophe rule is recorded for {locale!r}. Add it to "
            "``_APOSTROPHE_RULES`` — and ``None`` is a legitimate answer, for a "
            "language that writes no apostrophe, as Russian does not. What is not "
            "legitimate is being absent: this pass would then have to guess, and "
            "the guess it used to make was Russian's."
        )
    return _APOSTROPHE_RULES[locale]


#: The single mark that can be read as a quotation mark here, and the
#: only one.
#:
#: The typewriter apostrophe, and not the curly forms, because the curly
#: forms are what the *apostrophe* rules in this module write. ``Paulus’``
#: is this pass's own output; reading it back as half a quotation would
#: make the pass answer one way on a string and another way on its own
#: result, which the seeded fuzz demonstrates in four characters. ``‚``
#: and ``‘`` are the German inner-quotation pair and are already a
#: standing reason for this module to keep its hands off a string
#: entirely — see ``_german_apostrophe_allowed``.
#:
#: Nothing is lost by the narrowness: all 47 live rows this exists for
#: carry the straight character, because they were translated from an
#: English source that types it.
_SINGLE_QUOTATION_MARK: Final[str] = "'"


def _single_marks_that_quote(text: str, free: list[bool], locale: LocaleCode) -> list[int]:
    """Positions of the single marks in ``text`` that are quoting.

    Empty unless *every* single mark in the string pairs cleanly, which
    is the same all-or-nothing that ``_quotes_balance`` applies to the
    double ones and for the same reason: one mark that will not pair is
    proof the reading is wrong, and there is no telling which one it is.

    A mark welded between two letters is not considered at all. That is
    an apostrophe in every language that writes one — ``ім’я``,
    ``п'ять``, ``don't`` — and it is the shape ``_ukrainian_apostrophe``
    already rules on.

    The rest have to alternate: opener, closer, opener, closer. An
    opener stands where a quotation opens and is welded to the text it
    introduces; a closer stands behind a word and is not welded to the
    next one. ``Paulus’ Brief`` offers a mark that reads as a closer and
    has no opener in front of it, so the string is abandoned and its
    genitive is left for ``_german_apostrophe``.

    English is not asked. Its two quotation marks are the same straight
    character and its inner quotation is the single mark, so a rule that
    turned ``'…'`` into ``"…"`` there would flatten a nesting the
    language actually uses. The three languages that set a distinct pair
    have no such use for it: measured over the live catalogue on
    2026-08-22, 27 German and 20 Ukrainian rows carry Scripture quoted
    in straight ASCII single marks — every one of them arrived from an
    English source that quotes that way, and not one is an inner
    quotation.
    """
    if locale == "en":
        return []
    # The prose, with the markup taken out. Neighbours are read off this
    # and not off ``text`` so that a mark sitting against a tag is read
    # against the word on the other side of it, which is what a reader
    # sees.
    prose = [index for index, ok in enumerate(free) if ok]
    at = {index: position for position, index in enumerate(prose)}

    def neighbour(position: int) -> str:
        return text[prose[position]] if 0 <= position < len(prose) else ""

    candidates: list[int] = []
    for index in prose:
        if text[index] != _SINGLE_QUOTATION_MARK:
            continue
        before, after = neighbour(at[index] - 1), neighbour(at[index] + 1)
        if before.isalpha() and after.isalpha():
            continue
        candidates.append(index)
    if not candidates or len(candidates) % 2:
        return []
    for position, index in enumerate(candidates):
        before = neighbour(at[index] - 1)
        before_before = neighbour(at[index] - 2)
        after = neighbour(at[index] + 1)
        # The same reading the double marks get, and deliberately the
        # same function. A single mark that is quoting is a quotation
        # mark; asking a second question about it is how the two answers
        # come apart, and they did: a mark behind a hyphen — ``Senf-'Wort'``
        # — satisfied a looser test here and then failed
        # ``_opens_quotation`` at the writing, so the string came out
        # ``Senf-“Wort“``, opened twice and never closed. That is the
        # defect ``scripts/repoint_unclosed_quotations.py`` exists to
        # mend, manufactured fresh.
        opening_here = _opens_quotation(before, before_before, after)
        closing_here = before not in _WHITESPACE_CONTEXT and not after.isalnum()
        if position % 2 == 0 and not opening_here:
            return []
        if position % 2 and not closing_here:
            return []
    return candidates


def _apply_quote_rules(text: str, free: list[bool], tags: list[_Tag], out: list[str], locale: LocaleCode) -> None:
    opening_mark, closing_mark = _marks_for(locale)
    apostrophe = _apostrophe_for(locale)
    # A language whose two marks are the same character cannot get one
    # of them backwards, so it needs no balance test: English's
    # straightening is a total mapping and safe on ``5" breit``. Where
    # the marks differ, the slot decides the character, and a string
    # whose marks cannot pair keeps every one of them — see
    # ``_quotes_balance``.
    repoint_quotes = opening_mark == closing_mark or _quotes_balance(text, free)
    # A pair of single marks doing a quotation's work gets the marks the
    # language quotes in. This is decided for the whole string before
    # anything is written, because it is a fact about the string: see
    # ``_single_marks_that_quote``.
    quoting_singles = {
        index: position % 2 == 0 for position, index in enumerate(_single_marks_that_quote(text, free, locale))
    }
    # And once decided, those positions stop being marks the apostrophe
    # rule may reason about. German's rule asks permission of the whole
    # string and refuses where any single mark is quoting — which is the
    # right answer for the marks left over, and would be the wrong one
    # for the pass as a whole, since the marks it is refusing on account
    # of are the ones about to become ``„…“``. Reading the string on the
    # second pass, where they already have, would then answer
    # differently: the seeded fuzz found a backtick inside a code span
    # that settled one way and then the other.
    prose = free if not quoting_singles else [ok and index not in quoting_singles for index, ok in enumerate(free)]
    apostrophes_allowed = apostrophe is not None and apostrophe.permitted(text, prose)
    # Where a block begins or ends, whatever stood before it stops being
    # context. Both edges count: ``</p>`` ends the sentence that was
    # running, ``<blockquote>`` starts a place that had none.
    boundaries = sorted(end for name, _closing, _start, end in tags if name in _BLOCK_ELEMENTS)
    next_boundary = 0
    previous = ""
    # The character before ``previous``. Read only when ``previous`` is
    # a dash, to tell a hyphen welded to a word from punctuation
    # standing on its own — it travels with ``previous`` and is reset
    # wherever ``previous`` is.
    before_previous = ""
    for index, char in enumerate(text):
        while next_boundary < len(boundaries) and boundaries[next_boundary] <= index:
            previous = ""
            before_previous = ""
            next_boundary += 1
        if not free[index]:
            continue
        before = text[index - 1] if index > 0 and free[index - 1] else ""
        after = text[index + 1] if index + 1 < len(text) and free[index + 1] else ""
        opening = _opens_quotation(previous, before_previous, after)
        # A mark standing directly against one this pass has just
        # written is not opening a quotation. Nothing separates them, so
        # either nothing would be quoted or the quotation in front has
        # only just ended.
        #
        # ``_opens_quotation`` cannot see this. It reads
        # ``_OPENING_CONTEXT``, and that set contains both of German's
        # marks — ``„`` because it opens, and ``“`` because it opens in
        # English. So a mark behind either of them looked like an
        # invitation to open another one, and the results were not even
        # stable: ``«<img src="a.png">»`` came back as
        # ``«<img src="a.png">«`` — the image is the whole quotation, so
        # no prose character stands between the marks — ``«»`` came back
        # as ``««``, and a German row ending ``map““`` settled at
        # ``map““`` on one pass and ``map“„`` on the next.
        #
        # A quotation opened twice and never closed is the defect
        # ``scripts/repoint_unclosed_quotations.py`` exists to mend, and
        # a pass that reads its own output differently from its input is
        # the one ``_marks_for`` refuses at length. This is both.
        if opening and previous in (opening_mark, closing_mark) and opening_mark != closing_mark:
            opening = False

        if index in quoting_singles:
            # What the pass already proved, not what this position looks
            # like now. ``_single_marks_that_quote`` read the whole
            # string and would have abandoned it unless the marks
            # alternate; writing anything but that alternation would
            # discard the proof and can only disagree with it.
            out[index] = opening_mark if quoting_singles[index] else closing_mark
        elif char in _QUOTE_CHARS:
            if repoint_quotes:
                out[index] = opening_mark if opening else closing_mark
        elif apostrophe is not None and apostrophes_allowed:
            out[index] = apostrophe.write(char, before, after)

        # Context for the *next* mark is what we just wrote, not what we
        # read. A straight ``"`` does not open a quotation and ``„`` does,
        # so reading the input would classify the same position
        # differently on a second pass and ``""`` would settle at ``„“``
        # once and ``„„`` the time after. Carrying the output forward
        # makes pass two see exactly what pass one saw.
        before_previous, previous = previous, out[index]


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


# A title may hold a command line, and a command line is not prose.
# ``Using git rebase -i to Clean Up a Branch`` came back as ``Using Git
# Rebase -I to Clean up a Branch`` — and ``-i`` and ``-I`` are different
# flags, so a reader who copies the heading runs a different command.
# Title Case's safety argument ("the worst it can do is capitalise a
# common noun") does not survive contact with code.
#
# So a run of non-space characters carrying a mark prose does not use is
# left exactly as its author wrote it: a leading ``-`` or ``/`` (a flag,
# a path), an underscore, ``=``, ``$``, ``@``, ``|``, ``~``, an inner
# slash, ``()``, or a dot welded between two characters (``app.py``,
# ``v1.2``, ``e.g.``).
_CODE_MARKS: Final[frozenset[str]] = frozenset("_\\=$@|~")
_WELDED_DOT_RE: Final[re.Pattern[str]] = re.compile(r"\w\.\w")


def _looks_like_code(run: str) -> bool:
    if len(run) > 1 and run[0] in "-/":
        return True
    if any(char in _CODE_MARKS for char in run):
        return True
    if "/" in run or "()" in run:
        return True
    return bool(_WELDED_DOT_RE.search(run))


def _space_runs(text: str, free: list[bool], start: int, end: int) -> list[tuple[int, int]]:
    """The span's runs of visible prose, split on whitespace and markup."""
    runs: list[tuple[int, int]] = []
    opened = -1
    for index in range(start, end):
        if free[index] and not text[index].isspace():
            if opened < 0:
                opened = index
            continue
        if opened >= 0:
            runs.append((opened, index))
            opened = -1
    if opened >= 0:
        runs.append((opened, end))
    return runs


def _code_runs(text: str, runs: list[tuple[int, int]]) -> set[int]:
    """Which runs the title rule may not touch.

    The code-shaped ones, and then leftwards from every flag: a command
    line reads from its flags back to the command that owns them, and
    every part of that command is lower case. ``git`` and ``rebase``
    belong to ``git rebase -i``; ``Using`` carries a capital already and
    stops the walk, as does the first word of the title itself.
    """
    protected = {index for index, (begin, stop) in enumerate(runs) if _looks_like_code(text[begin:stop])}
    for index in sorted(protected):
        begin, _ = runs[index]
        if text[begin] != "-":
            # A path is not a command. Only a flag owns the words to its
            # left, and ``/etc/hosts`` owns nothing.
            continue
        neighbour = index - 1
        # Never as far as the run that opens the title: a title's first
        # word is a title word whatever follows it, and a walk that ate
        # it turned ``running rm -rf on a volume`` into a heading with no
        # capital at all.
        while neighbour >= 1:
            run = text[runs[neighbour][0] : runs[neighbour][1]]
            if not run.isalnum() or not run.islower():
                break
            protected.add(neighbour)
            neighbour -= 1
    return protected


def _title_case_span(text: str, free: list[bool], out: list[str], start: int, end: int) -> None:
    runs = _space_runs(text, free, start, end)
    untouchable = [runs[index] for index in _code_runs(text, runs)]
    words = _title_words(text, free, start, end)
    for position, (indices, fresh) in enumerate(words):
        if any(begin <= indices[0] < stop for begin, stop in untouchable):
            continue
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
# The first version of this rule argued from the numbers alone: a word,
# a chapter, a comma and a verse was a citation. That reading is wrong
# in German, and wrong in the most ordinary way there is. **German
# writes its decimal separator as a comma**, so ``Wort 5,3`` is not a
# rare shape a citation happens to share — it is how German writes every
# number that is not a whole one. And most German book names are also
# ordinary German first names or ordinary German nouns: Markus, Daniel,
# Ruth, Titus, Johannes, Richter, Prediger, Genesis. Put the two
# together and the pass was republishing
#
#     Markus 5,3 Millionen Euro Umsatz   →   Mk. 5,3 Millionen Euro
#     Daniel 3,4 Prozent stimmten zu     →   Dan. 3,4 Prozent
#     Ruth 2,1 Jahre nach dem Umzug      →   Rut 2,1 Jahre
#
# in the reader's own language, with every digit intact — so no
# validator downstream could see anything wrong. This module runs after
# the model, on every German string, and it renamed a person.
#
# The platform serves three biblical courses today and will serve others
# that are not, so the fix cannot be a list of German words to avoid.
# The name is simply never evidence by itself. Something in the span has
# to prove it is a citation:
#
# **To touch the span at all** — even just to repoint its numbers — the
# name must be one German itself prints (``find_book_written_in``), or
# Cyrillic. ``Rev.`` and ``Ex.`` are in the shared alias table and are
# not German; a German reader meets them as *Revision* and *Exemplar*,
# and ``Zeichnung Rev. 3:2`` is a drawing revision, not Revelation.
#
# **To rewrite the name**, one of four things has to be true:
#
# * It is written in **Cyrillic** — ``Ин. 3:16``, ``1 Кор. 13`` sitting
#   in a German table — and then a chapter alone is evidence enough.
#   There is no reading in which a Cyrillic word followed by a number is
#   German prose, and a reference left in the source language is the
#   single most obvious tell a translated page can carry.
# * It is already German's own **abbreviation**, give or take the
#   printed dot: ``Apg`` → ``Apg.``, ``Röm`` → ``Röm.``. An abbreviation
#   is not a German word, and the edit only ever restores a full stop.
# * It carries a **leading ordinal** — ``1. Korinther 13,4``,
#   ``2. Samuel 3,4``. German does not put an ordinal in front of a
#   first name and a decimal behind it.
# * It **stands alone inside brackets** — ``(Genesis 1,1)`` — with
#   nothing in the brackets but the name and its numbers. That is a
#   citation and cannot be read as anything else.
#
# Everything else keeps the spelling its author gave it, including every
# spelled-out German name in running prose. That is a real loss:
# ``Apostelgeschichte 1,8`` no longer converges on ``Apg. 1,8`` where it
# stands bare in a sentence, and the editor's count of 2026-08-20 says
# that is 48 references. It is the loss this rule chooses. An
# unabbreviated citation is a citation somebody may not love the look
# of; a renamed person is a factual error published in German.
#
# A German name in any of the four cases still needs a chapter *and* a
# verse, and still may not sit directly behind an article — ``die
# Apostelgeschichte 1,8`` is a noun phrase, and ``die Apg. 1,8`` is not
# something anybody would write.
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

# ``1. Korinther``, ``2. Samuel``, ``3. Johannes``. The ordinal belongs
# to the book, and German prose has no use for one in front of a first
# name that is followed by a decimal.
_DE_LEADING_ORDINAL: Final[re.Pattern[str]] = re.compile(r"^[1-5]\.?[  ]")

# A bracket that holds a reference and nothing else is a citation in any
# language and in any subject.
_BRACKET_PAIRS: Final[dict[str, str]] = {"(": ")", "[": "]"}


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


def _reads_as_german(form: str, slug: str) -> bool:
    """Whether this span may be edited at all.

    The name has to be one German itself prints, or Cyrillic. Everything
    else — an English or Latin abbreviation that the shared alias table
    happens to know — is a word this page's reader will read as German,
    and the numbers behind it are that word's numbers, not a chapter and
    a verse.
    """
    if any(_is_cyrillic(char) for char in form):
        return True
    return find_book_written_in(form, "de") == slug


def _spelled_the_same(one: str, other: str) -> bool:
    """Two printed forms differing only by the abbreviation dot or case."""
    return one.strip().rstrip(".").casefold() == other.strip().rstrip(".").casefold()


def _stands_alone_in_brackets(text: str, start: int, end: int) -> bool:
    """``(Genesis 1,1)`` — a bracket holding the reference and nothing else."""
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return before in _BRACKET_PAIRS and _BRACKET_PAIRS[before] == after


def _may_rename(text: str, span: tuple[int, int], form: str, slug: str, repointed: str, book: str, offset: int) -> bool:
    """Whether the evidence is strong enough to rewrite the book's name.

    Four ways in, and the name on its own is not one of them — see the
    note above. ``Markus``, ``Daniel``, ``Ruth`` and ``Titus`` reach
    every test here and fail all four, which is the whole point.
    """
    if any(_is_cyrillic(char) for char in form):
        # A Cyrillic name in German text is wrong whatever follows it;
        # a chapter number is only needed to know it is a citation.
        return True
    if "," not in repointed:
        # No verse. ``Apostelgeschichte 8`` may well be a sentence.
        return False
    if _preceding_word(book, offset).lower() in _DE_DETERMINERS:
        return False
    canonical = display_book_name(slug, "de")
    if canonical is not None and _spelled_the_same(form, canonical):
        return True
    if _DE_LEADING_ORDINAL.match(form):
        return True
    return _stands_alone_in_brackets(text, *span)


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
        if not _reads_as_german(form, slug):
            continue
        name_start = match.start("book") + offset
        canonical = display_book_name(slug, "de")
        if (
            canonical is not None
            and canonical != form
            and _may_rename(text, (name_start, num_end), form, slug, repointed, match.group("book"), offset)
        ):
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
#
# None of which was enough, because a run of four to six digits is also
# the shape of every identifier anybody writes down. The rule was
# grouping
#
#     Die Postleitzahl 46032 gehört zu Carmel.  →  46.032
#     Rufen Sie die Nebenstelle 4021 an.        →  4.021
#     Fehlercode 50012 bedeutet Zeitüberschreitung. →  50.012
#
# and a ZIP code with a thousands separator in it is not a typographic
# preference, it is a wrong number.
#
# What separates the two is not the digits, it is whether the number
# counts anything. **A count is followed by what it counts** — 3000
# *Menschen*, 5000 *Männer*, 144000 *Versiegelte*, 12500 *Euro* — and
# German capitalises every noun, without exception. An identifier counts
# nothing, so what follows it is a verb or a preposition, and those are
# lower case. That is the whole test, and it is worth stating what it
# deliberately is not: not a list of label words (*Nummer*, *Code*,
# *PLZ*, *Artikel*, *Nebenstelle*…). Such a list is unbounded —
# *Fehlercode*, *Bestellnummer*, *Zimmernummer*, *IBAN*, *ISBN*, *DIN* —
# and every course on a new subject would bring words nobody put in it.
# German orthography needs no list and does not rot.
#
# The cost is a count that stands at the end of its clause ("Es waren
# 3000.") or in front of an adjective ("5000 hungrige Männer"): those
# keep their bare digits. An ungrouped count reads slightly less German.
# A grouped ZIP code is wrong.
_DE_THOUSANDS_RE: Final[re.Pattern[str]] = re.compile(r"(?<![\d.,:/%–—-])\d{4,6}(?![\d.,:/%–—-])")
_DE_YEAR_RANGE: Final[range] = range(1000, 2100)

# What may stand in for the capitalised noun: the sign of the thing
# being counted, written where the noun would be.
_DE_UNIT_SIGNS: Final[frozenset[str]] = frozenset("€$£₴₽¥%‰")


def _counts_something(text: str, end: int) -> bool:
    """Whether a capitalised German noun — or a unit sign — follows."""
    rest = text[end:]
    if rest[:1] in {" ", "\xa0"}:
        rest = rest[1:]
    head = rest[:1]
    return bool(head) and (head.isupper() or head in _DE_UNIT_SIGNS)


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
        if not _counts_something(text, end):
            continue
        edits.append((start, end, f"{value:,}".replace(",", ".")))
    return _splice(text, edits)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def normalize_characters(text: str, locale: LocaleCode, content_kind: ContentKind | None = None) -> str:
    """The half of the pass that is one character for one.

    Exported for the test that pins the length invariant on it. The
    span layer above cannot hold that invariant and does not claim to.
    """
    free, tags = _prose_mask(text)
    out = list(text)
    _apply_quote_rules(text, free, tags, out, locale)
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

    Raises ``LanguageNotInTable`` for a language this pass has no rules
    for. It used to return the text untouched, which is the failure it
    is hard to see: a page that quietly keeps the source's punctuation
    looks like a page, and the frozenset that was supposed to prevent
    that could be satisfied by adding a word to it.
    """
    if not text:
        return text
    result = normalize_characters(text, locale, content_kind)
    if locale == "de":
        result = _normalize_german_references(result)
        result = _group_german_thousands(result)
    elif locale == "en":
        result = _space_english_dashes(result)
    return result


__all__ = ["normalize_characters", "normalize_typography"]
