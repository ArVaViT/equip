# ruff: noqa: RUF001, RUF002, RUF003
# The rules here are about characters: an en dash inside a verse range
# and a Cyrillic book name in the comment explaining it are the
# subject matter, not typos.
"""Structural validation of a translation against its source.

Why this exists
---------------

Before this module, ``status='ok'`` on a ``content_versions`` row meant
"the HTTP call did not raise". ``gemini._parse_response`` checks the
*envelope* — are there candidates, are there parts, did ``finishReason``
say STOP, is the text non-empty — and nothing at all checks what came
back. A response that dropped a scripture marker, lost half the HTML,
answered in the wrong language, or politely explained that it could not
translate the passage is a perfectly well-formed envelope, and the whole
platform reads its ``ok`` as "this translation is good".

That gap is what makes the publishing rule unenforceable. "Do not
publish until every language is translated **and checked**" needs
something that can say *checked*, and a status that means "no exception
was raised" cannot.

What this can and cannot do
---------------------------

It checks the promises the system prompt makes, and only those:
markers, markup, placeholders, numbers, language, length, and the
model talking to us instead of translating. Every one of them is a
property of the *pair* (source, translation) that can be decided
mechanically.

Four checks reach past shape into meaning, and each can only do it
where meaning has been written down in a table: ``_check_glossary``
against the register, ``_check_proper_names`` against the biblical
persons and places, ``_check_person_names`` against the form each
language prints for one of them, and ``_check_book_names`` against the
printed name of each book of the Bible in each served language. None
judges wording. Each asks a question with one answer — did this term
survive, is this the same name, would this language have printed this
spelling — and that is the whole of what "meaning" means here.

It does not judge whether the translation is *good*. Nothing local can:
research on this is consistent that quality in the general case is not
measurable without a reader of the language. What it does is catch the
failures that are structural, and those are the ones that silently
corrupt a lesson — a lost verse marker leaves a student reading
``EQVa3f9c2`` where scripture should be.

The output is advisory to the caller: a list of issues, each with a
code and a sentence. The orchestrator decides what to do with them —
today, park the row as ``needs_review`` instead of ``ok``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from app.core.sanitize import strip_tags
from app.services.bible.psalm_numbering import renumber_between
from app.services.bible.references import parse_references
from app.services.language_detection import (
    carries_language,
    detect_locale,
    script_letters,
    shares_script,
)

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode
    from app.services.bible.references import BibleRef
    from app.services.translation.protocol import ContentKind

# Sentinels from ``app.services.bible.substitution``. Both spellings are
# matched: rows written before the prefix changed still carry ``VERSE_``,
# and they must keep validating the same way.
# These stand in for canonical scripture during the model call and are
# restored afterwards; one that does not come back means a student
# reads the raw token where the verse belongs.
_MARKER_RE: Final[re.Pattern[str]] = re.compile(r"(?:EQV|VERSE_)[0-9a-f]+")

# Tag names only — attributes get rewritten by translation (an
# ``alt=""`` legitimately changes language), the structure must not.
_TAG_NAME_RE: Final[re.Pattern[str]] = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)")

# Tags that decorate a word rather than hold the document up. The list
# is closed, short, and named rather than inferred: a tag that is not on
# it keeps the veto, so a shape nobody thought about fails safe.
#
# ``<a>`` and ``<img>`` are deliberately absent even though they sit
# inside a sentence — a lost link is a lost destination and a lost image
# is lost content, neither of which is decoration. So are ``<sup>`` and
# ``<sub>``: in H₂O the tag *is* the meaning. See ``_check_tags``.
_EMPHASIS_TAGS: Final[frozenset[str]] = frozenset({"b", "em", "i", "span", "strong"})

# The placeholder shapes rule 4 of the system prompt promises to keep.
_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(
    r"\{[a-zA-Z_][a-zA-Z0-9_]*\}"  # {variable}
    r"|%\([a-zA-Z_][a-zA-Z0-9_]*\)[sdifr]"  # %(name)s
    r"|%[sdifr]"  # %s
    r"|\[\d+\]"  # [1]
)

# Chapter-and-verse references ("1:26", "3.16"), and only those.
#
# Bare integers were checked here first, and a run over the production
# corpus showed why they cannot be: the source table lists "3–4 Царств"
# and the correct English is "1–2 Kings" — the Slavic and English
# traditions number the books of Kings differently, so a faithful
# translation legitimately changes the digits. Years and counts move
# for related reasons.
#
# This is now used on the *translation* side only, where the question is
# "do these digits appear anywhere" and a book name cannot be required —
# a German Bible prints Johannes 3,16 and the alias list does not know
# the word Johannes. What the source side may call a reference is
# decided by ``parse_references``, which insists on a book name; see
# ``_check_verse_refs`` for the clock that got a course parked.
_VERSE_REF_RE: Final[re.Pattern[str]] = re.compile(r"\d+\s*[:.,]\s*\d+(?:\s*[-–—‑−]\s*\d+)?")

# The largest chapter and verse there are: Psalm 119 has 176 verses, and
# the Psalter ends at 150. Anything past those is a number that merely
# looks like a reference.
_MAX_CHAPTER: Final[int] = 150
_MAX_VERSE: Final[int] = 176

# The fence the user prompt wraps content in. If either shape comes
# back, the model echoed the scaffolding instead of translating inside
# it — including the defanged form the prompt builder writes.
_FENCE_MARKERS: Final[tuple[str, ...]] = ("===BEGIN", "===END", "===_BEGIN", "===_END")

# Below this many characters, a length ratio says nothing: "Ja" against
# "Yes" is a 1.5x expansion and perfectly correct.
_MIN_CHARS_FOR_RATIO: Final[int] = 40

# German runs long against English, English runs short against Russian.
# These bounds are deliberately loose — they are here to catch a
# truncated paragraph or an appended explanation, not to police style.
_MIN_LENGTH_RATIO: Final[float] = 0.4
_MAX_LENGTH_RATIO: Final[float] = 2.5

# Below this, an unchanged string is ordinary: proper nouns, "Amen",
# numerals, a title that is a name. Above it, identical output means
# the model returned its input.
_MIN_CHARS_FOR_IDENTITY: Final[int] = 25

# Same-script pairs measured apart at every length the catalogue holds:
# the detector may withhold a lesson over one of these however short the
# string is. Membership is earned by measurement and nothing else — a
# pair that has not been measured gets the floor below, because burying
# correct work is the expensive direction and "we have not looked" is
# not evidence of safety. ``_check_language`` carries the table.
_PAIRS_TOLD_APART_AT_ANY_LENGTH: Final[frozenset[frozenset[str]]] = frozenset({frozenset({"de", "en"})})

# ...and how much text every other same-script pair needs behind it
# first. Cross-script needs none.
_MIN_LETTERS_FOR_A_CLOSE_PAIR: Final[int] = 30

# Content kinds whose text is a single short answer or heading, where
# an expansion is itself the failure the prompt warns about.
_SHORT_KINDS: Final[frozenset[str]] = frozenset({"title", "quiz_option"})
_SHORT_KIND_MAX_RATIO: Final[float] = 3.0

# …and only when the growth is also large in absolute terms. A quiz
# titled "Q" renders as "Вопрос" in Russian: six times the length, and
# obviously fine. Production had exactly that row.
_SHORT_KIND_MIN_GROWTH_CHARS: Final[int] = 40


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One structural defect found in a translation.

    ``code`` is stable and greppable — it goes into logs and, once the
    review queue exists, into a filter. ``detail`` is the sentence a
    human reads when deciding what to do with the row.
    """

    code: str
    detail: str
    #: Blocking issues keep the row out of the reader's hands: something
    #: is lost, wrong, or in the wrong language, and serving it would be
    #: worse than showing nothing. Non-blocking ones earn a retry (the
    #: model is not deterministic, and a second pass often comes back
    #: clean) and are then served anyway, because an imperfect sentence
    #: still teaches and a blank does not.
    #:
    #: Two kinds end up non-blocking. One is style — the translation is
    #: correct but reads as translated. The other is a real defect the
    #: check cannot tell apart from correct output: ``untranslated_run``
    #: cannot distinguish a bibliography from an untranslated clause,
    #: ``psalm_numbering_not_localised`` rests on inferring an edition
    #: from a locale, ``verse_reference_lost`` cannot tell the book of
    #: Judges from a bench of them, and ``wrong_language`` on a short
    #: same-script string is the detector guessing. A check that is
    #: sometimes wrong may name what it saw; it may not withhold the
    #: lesson over it.
    #:
    #: ``emphasis_lost`` is neither: it is right about what it saw and
    #: still does not block, because a sentence that lost its ``<em>``
    #: is a sentence, and this module withholds a page only when
    #: serving it would be worse than serving nothing.
    blocking: bool = True
    #: Advisory issues are named and not acted on. The distinction is
    #: not severity — it is whether a second attempt could carry
    #: information the first did not have.
    #:
    #: ``glossary_term_missing`` is the case that needed it. The
    #: register was already in the first prompt; the model read it and
    #: chose another word. Sending the same instruction back under
    #: "your previous attempt had these problems" adds no fact, only
    #: pressure — and where the model was right to decline (a grace
    #: period, a Minister of Finance) the pressure is pressure toward
    #: the wrong word, which ``_rank`` then prefers because it counts
    #: the complaint as a defect the retry fixed. So the issue is
    #: reported, logged and counted, and it neither spends a retry nor
    #: stands in front of the editorial review — the one reader in this
    #: pipeline that can tell the two cases apart.
    advisory: bool = False


def _markers(text: str) -> list[str]:
    return sorted(_MARKER_RE.findall(text))


def tag_names(text: str) -> list[str]:
    """Every tag name in ``text``, sorted — the document's structure as
    this module defines it.

    Public because it is no longer only ours. ``translation/html_split``
    cuts a long block into pieces and has to satisfy itself that the
    reassembled whole has the structure the source had; if it decided
    that by its own reckoning of "same tags", a piece could pass there
    and the document still be parked here. One definition, imported.
    """
    return sorted(name.lower() for name in _TAG_NAME_RE.findall(text))


def _placeholders(text: str) -> list[str]:
    return sorted(_PLACEHOLDER_RE.findall(text))


def _is_a_reference(chapter: str, verse: str) -> bool:
    """Whether this number pair can be a chapter and a verse at all.

    Broadening the separator to ``[:.,]`` — so that a German
    "Johannes 3,16" compares equal to "John 3:16" — swept in every other
    thing written as two numbers with a comma or a dot between them:

        "closes on August 15, 2026"   ->  15:2026
        "about 1,000 households"      ->  1:000

    Both were then reported as references the translation had lost, and
    a row parked at ``needs_review`` with an unchanged source hash is
    never retried — so one date in an announcement silently retired a
    correct translation. A year is past the end of the Psalter and a
    thousands group has a leading zero; neither is a verse.
    """
    if verse.startswith("0") and len(verse) > 1:
        return False
    try:
        return int(chapter) <= _MAX_CHAPTER and int(verse) <= _MAX_VERSE
    except ValueError:
        return False


def _verse_refs(text: str) -> list[str]:
    """Chapter-and-verse pairs, in a form the languages can be compared in.

    A German Bible prints Johannes 3,16 where an English one prints John
    3:16 — same verse, different punctuation, and the prompt now asks
    for the target language's own form. Comparing the raw strings made
    every correctly-localized German reference look like a lost one, and
    parked the row for review. The separator is normalised away; the
    numbers are what has to survive.
    """
    refs = []
    for raw in _VERSE_REF_RE.findall(text):
        canonical = _canonical_ref_form(raw)
        chapter, _, rest = canonical.partition(":")
        verse = rest.split("-", 1)[0]
        if _is_a_reference(chapter, verse):
            refs.append(canonical)
    return sorted(refs)


def _canonical_ref_form(ref: str) -> str:
    """One shape for a reference, whatever punctuation a language uses.

    Two conventions differ across the languages served, and both cost a
    production row before this existed: German separates chapter from
    verse with a comma (Johannes 3,16), and every language but English
    tends to render a verse range with an en dash (3,14–16 against
    3:14-16). Neither is a lost reference. Only the numbers are.
    """
    normalised = re.sub(r"\s+", "", ref).replace(",", ":").replace(".", ":")
    # Every dash a language or a model might use for a range: en dash,
    # em dash, non-breaking hyphen, minus. A model reaches for U+2011 so
    # the range does not break across a line, and the check read the
    # result as a lost reference.
    for dash in ("–", "—", "‑", "−"):
        normalised = normalised.replace(dash, "-")
    return normalised


def _normalised_for_identity(text: str) -> str:
    return " ".join(strip_tags(text).lower().split())


#: Code is not prose and is not translated. A ``<pre>`` block that comes
#: back identical is a correct translation, not an untranslated one.
#:
#: ``<code>`` and its siblings were added on 2026-08-19: a lesson block
#: that is nothing but a code sample does not always arrive wrapped in
#: ``<pre>``, and an inline ``<code>SELECT * FROM courses</code>`` reads
#: to the language detector as fluent English.
_CODE_SPAN_RE: Final[re.Pattern[str]] = re.compile(
    r"<(pre|code|kbd|samp|var)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)


def _words_for_runs(text: str) -> list[str]:
    """Words of prose, with markup, code and sentinels removed.

    Markers stand in for canonical scripture and are identical on both
    sides by design; a placeholder is meant to survive verbatim; a code
    block is not prose. None of them is evidence of anything.
    """
    without_code = _CODE_SPAN_RE.sub(" ", text)
    plain = _PLACEHOLDER_RE.sub(" ", _MARKER_RE.sub(" ", strip_tags(without_code)))
    return plain.lower().split()


def _carries_prose(text: str) -> bool:
    """Whether anything a translator could have translated is left.

    Rule 7 of the system prompt tells the model to return text that is
    already in the target language unchanged, and a lesson block that is
    a code sample, a SQL statement or a shell transcript is already in
    every language at once. The model obeys, and two checks then punish
    it for obeying: ``_check_identity`` sees output identical to input,
    and ``_check_language`` asks a detector that reads
    ``SELECT * FROM courses`` and ``for i in range(10)`` as English. Both
    are blocking, so a code-only block ru→de came back
    ``[('not_translated', True), ('wrong_language', True)]`` and parked
    the row — permanently, since ``executor`` skips a parked row whose
    source has not changed.

    The judgement those two checks make is about prose. Once the code
    spans and the markup are gone, a block with no words left is not a
    translation that failed; it is a block with nothing in it to judge,
    and the honest answer is to decline. Everything else about it —
    markers, tags, placeholders, length — is still checked.

    What counts as a word
    ---------------------
    "Anything at all is left" was the first bar and it is too low. The
    exemption above only reaches code somebody *tagged*, and the two
    shapes that hurt in production carried no tag:
    ``array.prototype.flatMap()`` as a quiz option, and a chemistry
    formula in a plain ``<p>``. Both are 25 characters or more, both are
    the same string in every language, and both came back from
    ``_check_identity`` as ``not_translated``, blocking, on a correct
    answer.

    Neither contains a word. ``array.prototype.flatMap()`` is one token
    with dots and brackets through it; ``2 H₂ + O₂ → 2 H₂O`` is digits,
    symbols and subscripts. So the bar is a *word* — a whitespace-
    delimited token that, once the punctuation around it is peeled off,
    is nothing but two or more letters. Ordinary prose clears it on its
    first word; a formula, an identifier and a call signature never do.

    The peeling matters: «Слово» is a word wearing quotation marks, and
    a rule that read the guillemets as part of the token would decline
    to judge a Russian sentence.

    One word is enough, and the stricter reading was tried and
    measured. "Most of the letter-bearing tokens must be words" —
    prose is mostly words, a formula is mostly not — sounds better and
    is wrong on this catalogue: run over all 14,687 active rows it
    calls "З жертовника в храмі", "Кто-то что-то сказал" and "У реки"
    prose-free, because one-letter prepositions are not words and short
    Slavic titles are half made of them. 112 real rows would have gone
    unjudged to buy two invented ones. The one-word rule changes 104
    rows against the bar it replaces, and every one of them is a bare
    number — "12", "64", "0" — which is exactly the set that should
    never have been called prose.

    Its limit, stated plainly: ``array.prototype.flatMap()`` clears,
    and ``array.prototype.flatMap(callbackFn, thisArg)`` does not,
    because ``thisArg`` on its own is letters and nothing else. A code
    sample with an argument list wants the ``<code>`` the exemption
    above is built around. This bar is for the shapes that arrive
    without one.
    """
    return any(_is_a_word(token) for token in _words_for_runs(text))


# Punctuation hanging off the ends of a token: quotation marks, a comma,
# a full stop, the brackets of a call. Stripped before asking whether
# what is left is a word.
_EDGE_PUNCTUATION: Final[re.Pattern[str]] = re.compile(r"^\W+|\W+$", re.UNICODE)

#: Two letters is the shortest thing worth calling a word here — a
#: one-letter token is a variable, an initial or an article, and none of
#: them is evidence that a string is prose.
_SHORTEST_WORD: Final[int] = 2


def _is_a_word(token: str) -> bool:
    """Two or more letters, and nothing that is not a letter.

    ``str.isalpha`` rather than a character class, because the class has
    to be right about more of Unicode than is comfortable: ``\\d`` is
    decimal digits only, so the subscript in ``H₂O`` is not one, and a
    pattern that merely excluded ``\\d`` would call ``H₂`` a word and
    hand the chemistry formula back to the checks this exists to keep
    away from it.
    """
    stripped = _EDGE_PUNCTUATION.sub("", token)
    return len(stripped) >= _SHORTEST_WORD and stripped.isalpha()


def _check_markers(source: str, translated: str) -> ValidationIssue | None:
    expected = _markers(source)
    if not expected:
        return None
    got = _markers(translated)
    if expected == got:
        return None
    missing = sorted(set(expected) - set(got))
    added = sorted(set(got) - set(expected))
    parts = []
    if missing:
        parts.append(f"lost {len(missing)} ({', '.join(missing[:3])})")
    if added:
        parts.append(f"invented {len(added)}")
    if not parts:
        parts.append("returned a different number of them")
    return ValidationIssue(
        code="scripture_marker_mismatch",
        detail=(
            f"Scripture markers do not match the source: {'; '.join(parts)}. "
            "A marker that does not come back leaves the raw token where the verse belongs."
        ),
    )


def _check_tags(source: str, translated: str) -> ValidationIssue | None:
    """Did the document keep its shape?

    This compared two sorted lists of tag names and reported any
    difference, which conflates three things that deserve three
    answers. Measured over the live catalogue on 2026-08-20, three rows
    fail it:

    * a Russian chapter block that dropped a whole
      ``<p><strong>Psalm</strong> — …</p>`` definition out of a list of
      eight (``lost {'p': 2, 'strong': 2}``);
    * an English chapter block that lost its only ``<p>`` and returned
      a bare sentence (``lost {'p': 2}``);
    * an English chapter block that put two words in ``<em>`` the
      Russian source had left plain (``added {'em': 2}``).

    The first two are the defect this check was built for: a paragraph
    that vanished, and a paragraph that stopped being one. The third is
    an editor doing their job. Sorted lists cannot tell them apart, so
    all three were blocking and the third was a lesson withheld over
    good writing.

    Three rules, and the direction is half of each:

    **A structural tag, in either direction, blocks.** ``<p>``,
    ``<li>``, ``<table>``, ``<img>``, ``<a>`` and everything else not
    named below carry the document rather than decorate it. Losing one
    merges two paragraphs into a wall or deletes a row from a table;
    inventing one splits a sentence, or invents a link that goes
    somewhere. Either way a reader is looking at a different document.

    **Emphasis lost is reported and served.** A ``<strong>`` the author
    put in and the model dropped is a real loss — the author marked
    that word for a reason. It is not a corrupted document: the
    sentence is whole, complete, and readable, and this module's rule
    is that a check withholds a page only when serving it would be
    worse than serving nothing. It is not, so the row earns the retry
    that non-blocking buys and is served if the retry does not fix it.

    **Emphasis added is not an issue at all.** Nothing in the system
    prompt forbids it, a language that marks emphasis by word order
    legitimately needs a tag where another did not, and the one live
    row that does this is better for it. Reporting it non-blocking was
    the alternative and it is worse than silence: every issue costs a
    retry, and paying the model to un-improve a correct translation is
    not a thing this pipeline should spend on.
    """
    expected = Counter(tag_names(source))
    got = Counter(tag_names(translated))
    if expected == got:
        return None

    lost = expected - got
    added = got - expected
    structural_lost = {tag: n for tag, n in lost.items() if tag not in _EMPHASIS_TAGS}
    structural_added = {tag: n for tag, n in added.items() if tag not in _EMPHASIS_TAGS}

    if structural_lost or structural_added:
        parts = []
        if structural_lost:
            parts.append("lost " + ", ".join(f"{n}×<{tag}>" for tag, n in sorted(structural_lost.items())))
        if structural_added:
            parts.append("gained " + ", ".join(f"{n}×<{tag}>" for tag, n in sorted(structural_added.items())))
        return ValidationIssue(
            code="markup_mismatch",
            detail=(
                f"The translation does not have the structure of its source: {'; '.join(parts)}. "
                "A paragraph, list item or table cell that does not come back leaves the reader "
                "a different document from the one the author wrote."
            ),
        )

    emphasis_lost = {tag: n for tag, n in lost.items() if tag in _EMPHASIS_TAGS}
    if not emphasis_lost:
        # Emphasis added and nothing lost. See the docstring: this is
        # editing, not damage, and it is not worth a retry either.
        return None
    return ValidationIssue(
        code="emphasis_lost",
        detail=(
            "Emphasis the source carried is missing from the translation: "
            + ", ".join(f"{n}×<{tag}>" for tag, n in sorted(emphasis_lost.items()))
            + ". The sentence is whole, so it is served — but the author marked those "
            "words for a reason, and the translation does not."
        ),
        blocking=False,
    )


def _check_placeholders(source: str, translated: str) -> ValidationIssue | None:
    expected = _placeholders(source)
    if not expected:
        return None
    got = _placeholders(translated)
    if expected == got:
        return None
    return ValidationIssue(
        code="placeholder_mismatch",
        detail=f"Placeholders changed: source has {expected}, translation has {got}.",
    )


def _ref_numbers(ref: BibleRef) -> str:
    """A reference reduced to the digits, in ``_verse_refs``' own shape."""
    if ref.verse_end is None:
        return f"{ref.chapter}:{ref.verse_start}"
    return f"{ref.chapter}:{ref.verse_start}-{ref.verse_end}"


def _check_verse_refs(
    source: str,
    translated: str,
    *,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
) -> ValidationIssue | None:
    """Did every passage the source points at survive as a pointer?

    Two things this used to get wrong, both found on 2026-08-19 and both
    of them the expensive direction — a blocking issue parks the row at
    ``needs_review``, ``executor`` then skips a parked row whose source
    has not changed, and the reconciler reads the course as waiting on a
    person and stops queueing it. A false positive here is not a warning
    somebody clears; it is a course that never publishes.

    **A number pair is not a reference until a book says so.** The
    source side was a bare regex for two numbers with a colon or a dot
    between them, inside plausible chapter and verse bounds, and a clock
    fits those bounds perfectly: ``The class meets at 2:30`` →
    ``Der Kurs beginnt um 14:30 Uhr`` was reported as
    ``verse_reference_lost``, and so was the same sentence going the
    other way. ``Урок 3.2 и 4.5 расписания`` parsed as two references,
    3:2 and 4:5, and stayed quiet only for as long as the translation
    happened to repeat both digits. ``bible.references.parse_references``
    already answers the question properly — it will not call anything a
    reference unless a declared book name stands in front of it — so it
    is what decides the source side now.

    That parser knows English and Russian book names, which is what the
    substitution layer knows too, so a reference authored in German or
    Ukrainian is no longer expected of the translation. That is a
    deliberate loss: it costs coverage on a locale pair that barely
    occurs as a *source*, and it buys the guarantee that nothing here
    calls a timetable a Bible verse.

    Why a lost reference stopped blocking
    -------------------------------------
    Requiring a book name fixed the clock and left the larger half of
    the problem standing: the books of the Bible are named after
    ordinary words, in every language served. ``books.py`` declares 521
    aliases and guards ten of them behind a capital or a printed dot.
    The other 511 are believed on sight, and measured against
    ``parse_references`` today:

        "See Ex. 3:4 for the worked solution."          -> exodus 3:4
        "Drawing Rev. 3:2 supersedes the earlier print." -> revelation 3:2
        "Column Col. 3:14 holds the running total."      -> colossians 3:14
        "Judges 4:2 of the appellate circuit dissented." -> judges 4:2
        "Job 3:2 was posted on the careers page."        -> job 3:2
        "Числа 3:14 в таблице округлены."                 -> numbers 3:14

    A translation that renders any of those the way the target language
    would — *Aufgabe 3 Punkt 4*, *Zeile 3, Spalte 14* — no longer
    contains the digit pair, and the row was parked for losing a verse
    it never had.

    Two narrowings were considered and neither works, because the six
    split evenly across both. **Require the name to be spelled out**
    and the three dotted abbreviations go, while Judges, Job and Числа
    stay — those are full book names. **Require the printed dot of an
    abbreviation** and it is the other three that stay. Nor does the
    capital rule that saves ``is`` and ``об`` reach these: "Job" and
    "Числа" are capitalised because they open a sentence. Extending the
    guarded list by hand was rejected on the same grounds as the
    quotation-mark narrowing under ``_check_untranslated_run`` — it
    would be one hand-written word list per language against an open
    set of homographs, and it would read as a guarantee it cannot give.

    So this keeps its eyes and loses its veto, exactly as
    ``untranslated_run`` did. What that costs is small and bounded,
    because a lost *pointer* is not lost *scripture*: a quoted verse
    travels as an ``EQV`` marker and ``scripture_marker_mismatch``
    still blocks, and a verse the provider dropped outright still
    arrives as ``scripture_dropped``, blocking, from ``executor``. What
    is at stake here is a citation a reader cannot follow in a lesson
    they can otherwise read — and the retry that non-blocking still
    buys is what fixes most of them anyway.

    **The Psalms are numbered twice.** The translation side stays a
    loose scan of the digits, because a German Bible prints
    ``Johannes 3,16`` and no alias list here knows the word Johannes.
    But the digits themselves legitimately move: the Synodal Psalter
    runs one behind every other edition we serve, rule 2a asks the model
    to print the reference the way the target-language Bible prints it,
    and it does. ``bible.psalm_numbering.renumber_between`` says which
    numbers the target edition should be showing, and both those and the
    source's own are accepted — see below for why the source's own
    still is.
    """
    expected = parse_references(source)
    if not expected:
        return None

    present = set(_verse_refs(translated))
    missing: list[str] = []
    unlocalised: list[str] = []
    for parsed in expected:
        source_form = _ref_numbers(parsed.ref)
        renumbered = {
            _ref_numbers(ref)
            for ref in renumber_between(parsed.ref, source_locale=source_locale, target_locale=target_locale)
        }
        if renumbered & present:
            continue
        if source_form in present:
            # The reference is there and a reader can follow it, so this
            # is not a lost reference and must not park the row. But if
            # the target edition prints that psalm under a different
            # number, the reader will land on the wrong one — the
            # English and Ukrainian rows of entity
            # c18954e1-6652-4fa8-8062-538483ce789b are exactly this, and
            # were marked ``ok`` for it.
            #
            # Non-blocking rather than blocking, because the premise is
            # a guess: we infer the source's numbering system from its
            # locale, and a Russian author who copied a reference out of
            # an English commentary breaks that inference. A guess may
            # earn a second pass; it may not withhold a lesson.
            if renumbered and source_form not in renumbered:
                unlocalised.append(f"{source_form} → {'/'.join(sorted(renumbered))}")
            continue
        missing.append(source_form)

    if missing:
        return ValidationIssue(
            code="verse_reference_lost",
            detail=(
                f"Chapter-and-verse references present in the source are missing from the "
                f"translation: {', '.join(sorted(set(missing))[:5])}. A student cannot look up "
                "a passage whose reference did not survive — unless the source never cited "
                "one, and this is an exercise number or a table cell that shares a book's name."
            ),
            blocking=False,
        )
    if unlocalised:
        return ValidationIssue(
            code="psalm_numbering_not_localised",
            detail=(
                f"The Psalms are numbered differently in {source_locale} and {target_locale}, and "
                f"these references kept the source's numbers: {', '.join(sorted(set(unlocalised))[:5])}. "
                f"A {target_locale} reader who looks one up lands on the neighbouring psalm. "
                f"Print the reference the way a {target_locale} Bible prints it, as rule 2a asks."
            ),
            blocking=False,
        )
    # Extra references where none were lost is usually a reference
    # the model spelled out; not worth stopping a course over.
    return None


def _check_fence(translated: str) -> ValidationIssue | None:
    if not any(marker in translated for marker in _FENCE_MARKERS):
        return None
    return ValidationIssue(
        code="fence_leaked",
        detail=(
            "The translation contains the prompt's fence markers, so the model echoed "
            "the scaffolding instead of translating the text inside it."
        ),
    )


def _check_identity(
    source: str,
    translated: str,
    *,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
) -> ValidationIssue | None:
    if source_locale == target_locale:
        return None
    if not _carries_prose(source):
        # A code sample is the same string in every language; rule 7
        # asks for it back unchanged. See ``_carries_prose``.
        return None
    normalised = _normalised_for_identity(source)
    if len(normalised) < _MIN_CHARS_FOR_IDENTITY:
        return None
    if normalised != _normalised_for_identity(translated):
        return None
    return ValidationIssue(
        code="not_translated",
        detail=(
            f"The {target_locale} text is identical to the {source_locale} source. "
            "Either the model returned its input, or the source was not in the language we think it is."
        ),
    )


def _check_language(
    source: str,
    translated: str,
    *,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
) -> ValidationIssue | None:
    """Is the answer in the language the reader asked for?

    When this may withhold the page
    -------------------------------
    The detector is good and it is not perfect: measured across
    production it is right to about one error in thirteen thousand
    lines (``api/v1/admin_translations.reset_review_status`` records
    the figure). What matters here is not the rate but where the errors
    sit, so both sides were measured on 2026-08-20 over all 12,434
    active rows that carry prose in a locale with a same-script rival.

    "False pos" is a correct row the detector contradicts. "Caught if
    wrong" is the same real sentences asked about as if they had been
    served to the other locale of their own script — German prose in an
    English row, in real language, at every length the catalogue
    actually contains — and it is how much of the defect the veto is
    worth in that band:

        band    pair    rows  false pos   FP rate   caught if wrong
        12-19   ru/uk   1371          1     0.07%       899  65.6%
        20-29   ru/uk   1516          1     0.07%      1211  79.9%
        30-44   ru/uk   1344          0     0.00%      1265  94.1%
        45-59   ru/uk    637          0     0.00%       627  98.4%
        60-∞    ru/uk   1260          0     0.00%      1260 100.0%

        12-19   de/en   1105          0     0.00%       801  72.5%
        20-29   de/en   1400          0     0.00%      1314  93.9%
        30-44   de/en   1400          0     0.00%      1371  97.9%
        45-59   de/en    827          0     0.00%       826  99.9%
        60-∞    de/en   1574          0     0.00%      1574 100.0%

    Three things fall out of that table, and the first cost a redesign.

    **A global floor is a hole, not a narrowing.** This check first went
    to a 60-letter floor for every same-script pair, borrowing the
    number from ``language_detection._ABSENCE_MIN_LETTERS``. That
    number was measured for a different and weaker question — how much
    text before the *absence* of a hallmark letter means anything —
    and importing it blindfolded the check across the two bands where
    it works best. A German sentence in an English row at 53 letters,
    which is a defect that has reached production in this project,
    would have been served. The floor has to be justified against the
    defect it must catch, not only against the false positives it must
    avoid, and 45-59 catches 98-100% of the defect at a 0% false
    positive rate.

    **Script is counted, not weighed.** Three Cyrillic letters rule out
    German at any length, so a cross-script mismatch blocks however
    short the string is. Everything below is about same-script only.

    **The confusion is one pair's, not the detector's.** All 6,306
    de/en rows are clean at every band, including 12-19 — English and
    German share little enough closed class, and what they do share
    ``_LATIN_HOMOGRAPHS`` already cancels. Both errors are ru/uk,
    Ukrainian read as Russian, at 18 and 24 letters:

        "Бог об'явився Аврааму."        18 letters
        "У кожному рядку по два образи" 24 letters

    ``кожному`` and ``рядку`` do not exist in Russian, but they are not
    in the word list either, and a short Ukrainian string without an
    і, ї or є starves the rest of the evidence. So the floor is scoped
    to the pair that earns it: ru/uk needs 30 letters, de/en needs
    none. A pair nobody has measured gets the floor, because "we have
    not looked" is not evidence of safety.

    What still gets through, said plainly: a Russian sentence in a
    Ukrainian row, or the reverse, under 30 letters. In that band the
    detector declines to name a language on a fifth to a third of real
    rows anyway, so the veto was never worth its nominal reach there;
    what it does cost is the ~70-80% it would have caught. That is
    accepted against burying 2 correct rows in 2,887, and it is bounded
    by mutual intelligibility — the two closest languages served — and
    softened by the retry a non-blocking issue still earns. A short
    German string in an English row, or any Cyrillic in a Latin row,
    still withholds the page.

    **The detector cannot be a witness against a text it already
    misreads.** A course that teaches a language quotes another one on
    purpose: «Правило: "I have been working here since 2019" — Present
    Perfect Continuous» is a Russian row, and the detector reads it as
    English, because it mostly is. Translated to German it correctly
    keeps the English, still reads as English, and was parked as the
    wrong language — 54 letters, comfortably over any floor.

    The tell is available and free: run the detector on the *source*.
    When it reads the source as the same language it is now objecting
    to, and that is not the language the source is declared to be in,
    it has demonstrated on this very pair that it is answering about
    the quoted material rather than the prose around it. Its verdict on
    the answer is then not evidence.

    Note what this does *not* do: exempt ``<em>`` or ``<q>`` the way
    ``<pre>`` and ``<code>`` are exempted. Rule 2b of the system prompt
    says in as many words that quotation marks are not a
    do-not-translate sign, and ``_check_untranslated_run`` rejected the
    same narrowing for the same reason — an untranslated verse hides in
    exactly the markup a deliberate citation hides in. The bare quiz
    option carrying an English phrase has no tag to exempt anyway. This
    asks about the source instead, which is a fact about the pair
    rather than a guess about the author's intent. On the live
    catalogue it fires on nothing: there is no active row whose source
    the detector misreads.
    """
    # "Три", "Amen", "1 Kor. 13" — a string with no prose in it is the
    # same string in every language, and asking which language it is in
    # is asking the wrong question. The detector will sometimes answer
    # anyway; this is where we decline to listen.
    #
    # ``carries_language`` counts letters after ``strip_tags``, and the
    # letters in ``SELECT * FROM courses`` count. So the code spans come
    # out first — see ``_carries_prose``.
    if not _carries_prose(translated):
        return None
    if not carries_language(translated):
        return None
    detected = detect_locale(translated)
    if detected is None or detected == target_locale:
        # ``None`` means the detector had no signal — short strings,
        # proper nouns, two languages of one script it cannot separate.
        # It refuses to guess, and so do we.
        return None

    reading = (
        f"The translation reads as {detected}, not {target_locale}. "
        "A student who chose that language would be served text they did not ask for."
    )

    if _carries_prose(source) and detected != source_locale and detect_locale(source) == detected:
        return ValidationIssue(
            code="wrong_language",
            detail=(
                f"{reading} But the detector reads the {source_locale} source as {detected} too, "
                "so it is answering about material both sides quote on purpose — a phrase in a "
                "language the lesson is teaching about — rather than about the prose. Served, "
                "because the reading is not evidence here."
            ),
            blocking=False,
        )

    close_pair = frozenset({detected, target_locale}) not in _PAIRS_TOLD_APART_AT_ANY_LENGTH
    if (
        shares_script(detected, target_locale)
        and close_pair
        and script_letters(translated) < _MIN_LETTERS_FOR_A_CLOSE_PAIR
    ):
        return ValidationIssue(
            code="wrong_language",
            detail=(
                f"{reading} On {script_letters(translated)} letters, though, {detected} and "
                f"{target_locale} share too much of a short phrase to be told apart — the "
                "detector's errors are all of this shape. Served, and worth a second look."
            ),
            blocking=False,
        )

    return ValidationIssue(code="wrong_language", detail=reading)


def _check_length(
    source: str,
    translated: str,
    *,
    content_kind: ContentKind,
) -> ValidationIssue | None:
    source_text = _normalised_for_identity(source)
    if len(source_text) < _MIN_CHARS_FOR_RATIO:
        if content_kind in _SHORT_KINDS and source_text:
            translated_length = len(_normalised_for_identity(translated))
            ratio = translated_length / len(source_text)
            grew_by = translated_length - len(source_text)
            if ratio > _SHORT_KIND_MAX_RATIO and grew_by >= _SHORT_KIND_MIN_GROWTH_CHARS:
                return ValidationIssue(
                    code="length_suspicious",
                    detail=(
                        f"A {content_kind} grew {ratio:.1f}x. The prompt asks the model not to "
                        "expand a heading or a one-line answer into a paragraph."
                    ),
                )
        return None

    translated_text = _normalised_for_identity(translated)
    ratio = len(translated_text) / len(source_text)
    if _MIN_LENGTH_RATIO <= ratio <= _MAX_LENGTH_RATIO:
        return None
    shape = "shorter" if ratio < _MIN_LENGTH_RATIO else "longer"
    return ValidationIssue(
        code="length_suspicious",
        detail=(
            f"The translation is {ratio:.2f}x the length of the source — much {shape} than "
            "any language pair we serve explains. Usually a truncated response or an "
            "explanation the model appended."
        ),
    )


# A run of source words long enough that finding it verbatim in the
# translation means it was not translated. Ten words is roughly a
# clause; below that, legitimate coincidence is common — proper names,
# a list of book titles, a formula.
_UNTRANSLATED_RUN_WORDS: Final[int] = 10

# ...and long enough in characters that ten short tokens (numbers, a
# reference list, initials) cannot reach the bar on their own.
#
# 45 rather than 60: ten English words are shorter than ten Russian
# ones, and at 60 the rule caught the Russian verse left inside English
# prose but not the English verse left inside German. Measured over
# every machine translation in production (2164 pairs) — six flagged,
# all six genuine, none false.
_UNTRANSLATED_RUN_CHARS: Final[int] = 45


def _check_untranslated_run(
    source: str,
    translated: str,
    *,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
) -> ValidationIssue | None:
    """Catch a clause of the source surviving verbatim in the translation.

    The whole-string version of this (``not_translated``) only fires
    when nothing was translated at all. What production actually
    produced was subtler and worse: a German sentence wrapping an
    English verse, because the prompt tells the model to leave quoted
    Scripture untouched and the substitution layer had not yet learned
    to recognise a quotation outside a blockquote. To a German reader
    that is not a citation — it is a sentence they cannot read, in the
    middle of one they can.

    Ten consecutive words is the bar, and the pair of languages has to
    actually differ; ``en``→``en`` is not a translation.

    Why it stopped blocking
    -----------------------
    A bibliography does exactly what this check punishes. ``F. F. Bruce,
    The Book of the Acts, Grand Rapids: Eerdmans, 1988`` is twelve words
    and sixty-odd characters of English, it *should* survive verbatim
    into a German lesson, and on 2026-08-19 it came back
    ``untranslated_run``, blocking. A church-history or OT-survey course
    is a list of these, and a blocking issue parks the row at
    ``needs_review`` where ``executor`` will skip it for as long as the
    source is unchanged — so one reading list retires a course.

    The obvious narrowing — ignore a run that sits entirely inside
    quotation marks, italics or parentheses — was considered and
    rejected, because it removes the only defect this check has ever
    caught. The founding incident *was* a quotation: a German sentence
    wrapping an English verse in quotes. Rule 2b of the system prompt
    now says in as many words that quotation marks are not a
    do-not-translate sign, so the region a citation hides in is exactly
    the region an untranslated verse hides in, and nothing in the shape
    of the text separates them. It also would not have caught the case
    that prompted this: a bibliography line in a plain ``<li>`` carries
    no quotes, no italics and no parentheses at all.

    So the check keeps its eyes and loses its veto. Non-blocking still
    buys the remedy that fixes most of these — the model is shown the
    run it left behind and asked again, in ``executor._ask`` — and still
    logs a stable code somebody can count. What it no longer does is
    withhold the page. A German lesson carrying one English citation
    still teaches; a course that never publishes does not.
    """
    if source_locale == target_locale:
        return None

    source_words = _words_for_runs(source)
    if len(source_words) < _UNTRANSLATED_RUN_WORDS:
        return None
    # Padded on both sides so a run only matches at word boundaries:
    # without it "near" matches inside "nearby" and every run built from
    # short words finds itself somewhere.
    haystack = " " + " ".join(_words_for_runs(translated)) + " "

    for start in range(len(source_words) - _UNTRANSLATED_RUN_WORDS + 1):
        run = " ".join(source_words[start : start + _UNTRANSLATED_RUN_WORDS])
        if len(run) < _UNTRANSLATED_RUN_CHARS:
            continue
        if f" {run} " in haystack:
            return ValidationIssue(
                code="untranslated_run",
                detail=(
                    f"A run of {_UNTRANSLATED_RUN_WORDS} words survives verbatim from the "
                    f"{source_locale} source: {run[:80]!r}. Usually a quotation the model "
                    "was told to leave alone and nothing restored in the target language. "
                    "Translate it, unless it is a bibliographic citation, which stays as "
                    "its author printed it."
                ),
                blocking=False,
            )
    return None


# Ukrainian does not form active participles in -ючий/-уючий; every one
# of them is a Russian pattern carried across whole, and a native reader
# hears it at once. Production had "зобов'язуюча обіцянка" where Ukrainian
# wants "обіцянка, що зобов'язує".
#
# Two words survived into the standard language and are not errors, so
# they are named rather than guessed at. Everything else ending this way
# is flagged — as a note, not a blocker: the sentence is understandable,
# and refusing to serve it would hurt the reader more than the calque
# does.
_UKRAINIAN_ESTABLISHED = frozenset(
    {
        # The two that survived into the standard language. Named rather
        # than guessed at, so the check stays honest about its own scope.
        "віруючий",
        "віруюча",
        "віруюче",
        "віруючі",
        "віруючих",
        "віруючим",
        "віруючими",
        "віруючою",
        "віруючої",
        "віруючому",
        "віруючого",
        "завідувач",
    }
)

# The apostrophe matters: production's real defect was "зобов'язуюча", and
# a pattern built from \w alone walks straight past it, because an
# apostrophe is not a word character. So the word class carries all three
# apostrophes Ukrainian text actually arrives with.
_UKRAINIAN_ACTIVE_PARTICIPLE = re.compile(
    r"[\w'\u2019\u02bc]*юч(?:ий|ого|ому|им|ім|их|ими|а|ої|ій|у|ою|е|і)\b",
    re.IGNORECASE,
)


def _check_ukrainian_calques(translated: str, target_locale: str) -> ValidationIssue | None:
    if target_locale != "uk":
        return None
    hits = [
        word for word in _UKRAINIAN_ACTIVE_PARTICIPLE.findall(translated) if word.lower() not in _UKRAINIAN_ESTABLISHED
    ]
    if not hits:
        return None
    return ValidationIssue(
        code="ukrainian_calque",
        detail=(
            "Active participles Ukrainian does not form: "
            + ", ".join(sorted(set(hits))[:5])
            + ". This is a Russian pattern carried across; Ukrainian uses a "
            "relative clause instead. The text is readable, so it is served — "
            "but it reads as translated."
        ),
        blocking=False,
    )


def _check_numerals(source: str, translated: str, source_locale: str, target_locale: str) -> ValidationIssue | None:
    """A number the source spells out and the translation does not.

    The digit checks above are careful about chapter-and-verse
    references, years and counts. None of them sees a number written as
    a word, and production had the Russian answer «Двенадцать» come back
    in German as *Fünf* — five for twelve, in a question where the number
    IS the answer. Marked ok, served, and invisible to every check
    including the reviewer, because "Fünf" is a perfectly good word in a
    perfectly good sentence.

    Blocking. A wrong number is not a matter of register: a student
    reading it is being told something false, and it is the one class of
    defect where serving a gap is better than serving the text.
    """
    from app.services.translation.numerals import numbers_lost

    missing = numbers_lost(
        source,
        translated,
        source_locale=source_locale,  # type: ignore[arg-type]
        target_locale=target_locale,  # type: ignore[arg-type]
    )
    if not missing:
        return None
    named = ", ".join(f"{src} → {tgt}" for src, tgt in missing[:4])
    return ValidationIssue(
        code="numeral_lost",
        detail=(
            f"The source counts with a number the translation does not "
            f"contain: {named}. Numbers must survive translation exactly."
        ),
    )


def _check_glossary(source: str, translated: str, source_locale: str, target_locale: str) -> ValidationIssue | None:
    """A register term the source used and the translation dropped.

    This is the only check here that looks at meaning, and it can only
    do so where meaning has been written down: the glossary. Everything
    else in this module asks whether the shape survived — markup,
    placeholders, numbers, length. A word swapped for another word
    passes all of them. The Ethiopian eunuch of Acts 8 was served to
    Ukrainian readers as a Pentecostal, in a row marked ok, for as long
    as it took a person to read it.

    Not blocking, and not acted on. A translator may legitimately reach
    for a synonym, and refusing to serve the page over a word choice
    would trade a small wrong for a blank one.

    It used to earn a correcting pass. It no longer does, because the
    pass could only ever push one way. This check cannot tell a dropped
    term from a declined one — `grace` is also a period a lender allows,
    `minister` is also in the cabinet — and the model had the register
    in front of it when it chose. Asking again with "you did not use
    this word" adds no information to a decision that was already
    informed; it adds pressure, and on the strings where declining was
    right the pressure produced *Gnade* for a grace period. So this
    names what it saw and stops there: see ``ValidationIssue.advisory``.
    """
    from app.services.translation.glossary import missing_terms

    absent = missing_terms(
        source,
        translated,
        source_locale=source_locale,  # type: ignore[arg-type]
        target_locale=target_locale,  # type: ignore[arg-type]
    )
    if not absent:
        return None
    named = ", ".join(f"{src} → {tgt}" for src, tgt in absent[:4])
    return ValidationIssue(
        code="glossary_term_missing",
        detail=(
            f"The source uses terms this school renders a fixed way, and "
            f"the translation does not contain them: {named}. If the word "
            f"carries that meaning here, use the school's wording, in "
            f"whatever form the sentence needs. If it does not — if it is "
            f"part of a name, or an everyday sense of the same word — keep "
            f"what you wrote."
        ),
        blocking=False,
        advisory=True,
    )


def _check_proper_names(source: str, translated: str, source_locale: str, target_locale: str) -> ValidationIssue | None:
    """A biblical name answered with a different biblical name.

    The second check here that looks at meaning, and like ``_check_
    glossary`` it can only do so where meaning has been written down —
    in ``translation/proper_names.py``, which carries the persons and
    places of the live catalogue in all four languages. Everything else
    in this module asks whether the *shape* survived. A name swapped for
    another name keeps every shape there is: «Крисп» came back
    *Sosthenes*, «Матфий» came back *Matthäus*, and a lesson titled
    «Филипп» — the evangelist of Acts 8 — came back *Philippi*, the city
    from Acts 16. All three were marked ``ok`` and served until a person
    read them.

    Blocking, and the reasoning is ``_check_numerals``'s rather than
    ``_check_glossary``'s. A synonym is a matter of register and a
    reader loses little either way; a different name is a false
    statement. The lesson says Matthew was chosen to replace Judas, the
    quiz offers *the book of Isaiah* as the wrong answer to a question
    whose right answer is Isaiah. Serving that is worse than serving the
    gap, which is the bar this module sets for withholding a page.

    What earns the veto is the measurement, not the seriousness. This
    module's own warning applies in full — a false positive here is not
    a warning somebody clears, it is a course that never publishes — so
    the check was run over every live machine translation joined to its
    source, all 6 077 of them, and every row it named was read. It names
    nine. All nine are real, four of them defects nobody had reported.
    None is correct prose. The design is what makes that hold rather
    than luck: both halves of the accusation demand an exact form from a
    hand-written table, and every fuzzy tier in that module can only
    ever excuse a translation, never accuse one.

    Not advisory, for the same reason it is not a matter of taste. The
    register check stops at naming what it saw because the model had the
    glossary in front of it and may have been right to decline. Nothing
    was in front of it here, and "you wrote Sosthenes where the source
    says Крисп" is a fact the second attempt did not have.
    """
    from app.services.translation.proper_names import substituted_names

    swapped = substituted_names(
        source,
        translated,
        source_locale=source_locale,  # type: ignore[arg-type]
        target_locale=target_locale,  # type: ignore[arg-type]
    )
    if not swapped:
        return None
    named = ", ".join(f"{src} → {tgt}" for src, tgt in swapped)
    return ValidationIssue(
        code="proper_name_substituted",
        detail=(
            f"The source names one person or place and the translation names "
            f"a different one: {named}. These are two different people or "
            f"places in Scripture, not two spellings of one — keep the name "
            f"the source used, in its established form in the target language."
        ),
    )


def _check_book_names(source: str, translated: str, source_locale: str, target_locale: str) -> ValidationIssue | None:
    """A book of the Bible called by a name the target language does not print.

    The third check here that reaches past shape into meaning, and the
    only one of the three where the machine may rule outright.
    ``_check_glossary`` cannot say whether «Завіт» or «Заповіт» is the
    covenant, and ``_check_proper_names`` needs a hand-written table of
    people because a name is not derivable from anything. A book name is
    different in kind: a language has spellings it prints and spellings
    it does not, ``bible/books.py`` writes down which is which for all
    four served languages, and there is nothing left for judgement to
    do. ``Дії`` is Ukrainian for Acts; ``Діїв.`` is not a word.

    Non-blocking, and that is the one interesting decision in it.

    The seriousness is real — the live catalogue printed ``3. Könige``
    and ``4. Könige`` in German, sending a reader to a book that is not
    in their Bible, and a Ukrainian quiz asked about ``Галатам 2:1``
    while its own answer cited ``Галатів 2:1``. But this module's bar
    for withholding a page is not seriousness, it is whether serving the
    page would be worse than serving nothing, and it would not be: a
    student who reads ``Діїв. 1:8`` finds Acts 1:8, and a student who
    reads a blank finds nothing. That is ``emphasis_lost``'s reasoning,
    not ``proper_name_substituted``'s. A name swapped for another name
    is a false statement about who did what; a book name misspelled is a
    true statement misspelled.

    Not advisory either, and here it parts company with
    ``_check_glossary``. The register was in the model's first prompt
    and it may have been right to decline; nothing was in front of it
    about which spellings German prints, and "you wrote ``Mark 5,1``
    where German prints ``Mk.``" is a fact the second attempt did not
    have. So it earns its retry and is then served.

    Measured before it was wired in, over every live machine translation
    joined to its Russian source — 6 075 rows. It names twelve of them,
    thirteen spellings, and every one was read: all thirteen are real,
    none is correct prose. It stays silent on ``Genesis`` and ``1. Mose``
    in German (both real German), on ``Isaiah`` and ``Philippians`` in
    English, on ``Дії`` and ``Рут`` in Ukrainian, and on the forty-odd
    ordinary Ukrainian declensions — «Згідно з Ісаєю 7:1», «У Бутті
    1:1» — that an earlier scan of the same corpus offered up as
    invented book names. See ``translation/book_names.py`` for why not
    being recognised is never, on its own, an accusation.
    """
    from app.services.translation.book_names import foreign_book_names

    foreign = foreign_book_names(
        source,
        translated,
        source_locale=source_locale,
        target_locale=target_locale,
    )
    if not foreign:
        return None
    named = ", ".join(f"{printed} → {expected}" for printed, expected in foreign)
    return ValidationIssue(
        code="book_name_not_printed_here",
        detail=(
            f"The translation names a book of the Bible with a spelling this "
            f"language does not print: {named}. Use the name the target "
            f"language's own Bible carries, in whatever form the sentence "
            f"needs."
        ),
        blocking=False,
    )


def _check_person_names(source: str, translated: str, source_locale: str, target_locale: str) -> ValidationIssue | None:
    """A person called by a name the target language does not print.

    ``_check_proper_names``'s sibling, and the distinction between them
    is the whole reason this one exists. That check asks whether the
    source named one known person and the translation named a
    *different known* one. «Стефан» → «Степан» is neither half of that:
    «Степан» is the ordinary Ukrainian given name Stepan, so it is the
    same man misspelt, and the check built to catch substitutions was
    silent on all eight rows by construction.

    Blocking, which is where it parts company with
    ``_check_book_names``, and the argument is worth stating because the
    two look alike.

    That check is non-blocking on the ground that a misspelled book name
    is a true statement misspelled: a student who reads ``Діїв. 1:8``
    finds Acts 1:8, because the numbers are the address and the name is
    only a label on it. A person's name has no numbers behind it. It is
    the whole address, and «Степан» is a wrong one — a student who reads
    «промова Степана в Діян. 7» and opens Acts 7 finds «Стефан», with
    nothing on the page to tell them the two are the same man.

    What settles it is where the rows sit. All eight are assessment
    items — three quiz questions, twice over, and a Daily Challenge
    question with its explanation — while the lessons those questions
    examine print «Стефан» correctly. So the student is graded on a name
    the course never taught them, and cannot recover the right one from
    the wrong one. That is ``proper_name_substituted``'s position, not
    ``emphasis_lost``'s: serving the page is worse than serving nothing.

    What earns the veto is the measurement, not the seriousness. Run
    over every live machine translation joined to its Russian source —
    6 075 reachable rows — it names ten, and every one was read. Eight
    are «Степана» for the martyr and two are Claudius Lysias called
    «Лисий» (the adjective *bald*) and «Клавдій Лій» (a name in no
    language). None is correct prose. It stays silent on all eight rows
    that print «Стефан», on «Клавдій Лісій», and on the fourteen German
    rows that write *Stephans Rede* — German prints that name for that
    man, and claiming otherwise is how a check gets switched off.

    Not advisory. Nothing was in front of the model about which
    spellings Ukrainian prints for this man, and "you wrote «Степана»
    where Ukrainian prints «Стефан»" is a fact the second attempt did
    not have.
    """
    from app.services.translation.person_names import foreign_person_names

    foreign = foreign_person_names(
        source,
        translated,
        source_locale=source_locale,
        target_locale=target_locale,
    )
    if not foreign:
        return None
    named = ", ".join(f"{printed} → {expected}" for printed, expected in foreign)
    return ValidationIssue(
        code="person_name_not_printed_here",
        detail=(
            f"The translation names a person with a form this language does "
            f"not print for them: {named}. These are one person, not two — "
            f"use the name this language's own Bible carries, in whatever "
            f"form the sentence needs."
        ),
    )


def validate_translation(
    *,
    source: str,
    translated: str,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
    content_kind: ContentKind = "plain",
) -> list[ValidationIssue]:
    """Return every structural defect in ``translated`` against ``source``.

    An empty list means the translation kept every promise this module
    knows how to check. It does not mean the translation is good — see
    the module docstring.
    """
    if not translated.strip():
        return [
            ValidationIssue(
                code="empty",
                detail="The translation is empty.",
            )
        ]

    issues = [
        _check_fence(translated),
        _check_markers(source, translated),
        _check_tags(source, translated),
        _check_placeholders(source, translated),
        _check_verse_refs(
            source,
            translated,
            source_locale=source_locale,
            target_locale=target_locale,
        ),
        _check_identity(
            source,
            translated,
            source_locale=source_locale,
            target_locale=target_locale,
        ),
        _check_language(
            source,
            translated,
            source_locale=source_locale,
            target_locale=target_locale,
        ),
        _check_untranslated_run(
            source,
            translated,
            source_locale=source_locale,
            target_locale=target_locale,
        ),
        _check_length(source, translated, content_kind=content_kind),
    ]
    issues.append(_check_ukrainian_calques(translated, target_locale))
    issues.append(_check_glossary(source, translated, source_locale, target_locale))
    issues.append(_check_numerals(source, translated, source_locale, target_locale))
    issues.append(_check_proper_names(source, translated, source_locale, target_locale))
    issues.append(_check_person_names(source, translated, source_locale, target_locale))
    issues.append(_check_book_names(source, translated, source_locale, target_locale))
    return [issue for issue in issues if issue is not None]


def summarise(issues: list[ValidationIssue]) -> str:
    """One-line summary for the row's ``review_reason`` column."""
    return " ".join(f"[{issue.code}] {issue.detail}" for issue in issues)


__all__ = ["ValidationIssue", "summarise", "tag_names", "validate_translation"]
