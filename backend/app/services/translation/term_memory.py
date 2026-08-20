# ruff: noqa: RUF001, RUF002, RUF003
# The transliteration table below is Cyrillic and Latin side by side by
# definition — the whole point is that «Филиппы» and "Philippi" become
# the same string.
"""What this course has already called a thing, offered to the next field.

The glossary (``translation/glossary.py``) fixes the words a school
always renders the same way. It is a hand-written table of about forty
terms, and it can never be more than that: nobody is going to curate a
row for every person, city and river in every course, and the owner is
about to add courses on subjects nobody has chosen terms for.

Twin reuse (``executor._load_twins``) fixes the other easy half: two
rows with *identical* source text get one answer. But «Филиппы» and «в
Филиппах» are not identical strings, so it never sees them.

Between those two is where the remaining "this was translated by a
machine" lives, and an editor reading the whole Ukrainian generation
found it at every seam. One lesson said «у Филиппах» in its objectives,
«у Филипах» in the heading below, «Филиппійська» in the body and «у
Пилипах» in the discussion questions — four spellings of Philippi in one
lesson, and the fourth is the name of the *person* Philip, so two
different things ended up sharing a name. Elsewhere «Коринф» ×7 sat
against «Коринт-» ×8, once in the same line: ``<h2>Коринф: півтора
року</h2><p>У Коринті…``.

None of those is a mistranslation. Each is defensible on its own. What
is wrong is that they disagree, and they disagree because a field is
translated by a call that has never seen any other field.

So this module is a memory. It reads what the course has already been
translated into, works out which name in the source became which name in
the translation, and hands the pairs to the next call as a preference.

Three things it is deliberately not
-----------------------------------

**Not a rule.** Everything here reaches the model as "this is what the
rest of the course says; if you mean the same thing, say it the same
way; if you mean something else, ignore this". The register check
learned that the hard way: a note that said "use our wording" turned
"New Testament" into "New Covenant" on ten production rows. A memory
that can force is a memory that can be wrong in a way nobody can undo.

**Not a subject.** Nothing here knows about Acts, about Philippi or
about the three courses that exist today. What it knows is that a
capitalised word which is not starting a sentence is usually a name, and
that a name survives translation as something that still sounds like
itself. A course on church history benefits without anyone editing
Python.

**Not a query.** The memory is built from rows the executor has already
read — ``store.active_rows`` gains one column, and nothing else about
the pass changes — and then from the pass's own answers as they arrive.
Seeding costs zero additional statements at any plan size. See
``executor._seed_memory``.

How a pair is found
-------------------

Both sides are reduced to a rough sound skeleton: Cyrillic and Latin
both collapse onto one small alphabet, the digraphs these four languages
spell the same sound with are folded (``ph``→f, ``th``→f, ``ch``→h,
``sch``→s), and doubled letters collapse. «Филиппы» and "Philippi" and
«Филіппи» all become ``filipi``.

A source candidate and a target candidate are the same name when their
skeletons are close (``SequenceMatcher`` ≥ ``_MIN_SIMILARITY``), when
they begin with the same consonant, and when the match is *unambiguous*:
each has to be the other's best match, by a clear margin. Everything
about those rules is chosen to fail closed. Learning nothing costs a
seam; learning the wrong pair teaches the model a wrong name and spreads
it through the rest of the course, which is strictly worse than the
defect being fixed.

The consonant rule is what makes the Philippi case safe in the direction
that matters: ``filipi`` and ``pilipah`` (Пилипах — the person Philip)
begin f and p, so the memory refuses to believe they are the same word,
and the pipeline never learns to call the city by the man's name.

Disagreement is resolved by counting, not by recency. A key that has
been rendered two ways offers the reading the course used most often; a
tie offers nothing at all. That is the whole answer to "what if the
memory is stale" — a stale reading is one vote, and one vote does not
win an argument it is not ahead in.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Final

from app.core.sanitize import strip_tags
from app.schemas.locale import LOCALE_CODES
from app.services.translation.glossary import known_forms

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

#: How alike two skeletons must be before they are believed to be the
#: same name. Measured on the pairs this corpus actually contains:
#: «Филиппы»/«Филіппах» scores 0.77 and «Коринфе»/«Коринті» 0.83, while
#: «Марк»/«Марія» — two different people who share four letters — stops
#: at 0.75. The gap is narrow because the thing being told apart is
#: narrow; ``_MIN_MARGIN`` and the mutual-best rule are what make a
#: borderline score safe rather than this number.
_MIN_SIMILARITY: Final[float] = 0.76

#: How far ahead the winner must be. Two names in one paragraph that both
#: half-match the same word are not evidence of anything, and a coin toss
#: between them is exactly the wrong pairing this module must not make.
_MIN_MARGIN: Final[float] = 0.10

#: Skeletons shorter than this carry too little to identify anything —
#: ``iov`` (Иов) would match half the Old Testament.
_MIN_SKELETON: Final[int] = 4

#: A name is remembered under the first few letters of its skeleton, so
#: that «Филиппы», «Филиппах» and «Филиппийской» are one memory rather
#: than three. Inflection is a suffix in all four languages, which is why
#: a prefix works at all; five is the shortest prefix that still keeps
#: «Иерусалим» (``ierus``) apart from «Иерихон» (``ierih``).
_KEY_LENGTH: Final[int] = 5

#: Candidates read out of one text. A lesson block is asked for in
#: pieces, and each piece is scanned on its own, so this bounds the work
#: per call rather than per lesson.
_MAX_CANDIDATES_PER_TEXT: Final[int] = 64

#: Names held per language. A course that reaches this has more distinct
#: names than any prompt could carry anyway; the cap is here so that a
#: catalogue-wide pass cannot turn a dictionary into the thing that
#: spends the worker's memory.
_MAX_KEYS_PER_LOCALE: Final[int] = 500

#: Pairs offered to any one call. Past a handful the block stops being a
#: reminder and starts being a wall of vocabulary in front of the rules
#: that matter — the same reason ``glossary.terms_in`` filters.
_MAX_OFFERED_PAIRS: Final[int] = 8

# A word, apostrophes included so «Мар'ям» is one token. Hyphens are not:
# they join ordinary words as often as they join names.
_WORD_RE: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+(?:['’ʼ][^\W\d_]+)*", re.UNICODE)

# What, immediately before a capitalised word, means the capital is
# grammar rather than a name: the start of the text, the end of a
# sentence, an opening bracket or quote. A comma is absent on purpose —
# a capitalised word after a comma is mid-sentence and is exactly what we
# are looking for.
_CLAUSE_OPENERS: Final[frozenset[str]] = frozenset('.!?…:;•—–"«»„“”()[]{}/|')

_VOWELS: Final[frozenset[str]] = frozenset("aeiou")

# One alphabet for four languages. Two decisions are worth stating
# because both cost something:
#
# ``г``, ``ґ``, ``х``, ``g`` and ``h`` all become ``h``. Ukrainian ``г``
# is an h-sound where Russian ``г`` is a g-sound, and a table that kept
# them apart would refuse «Галилея»/«Галілея».
#
# ``th`` becomes ``f``. That looks wrong until you notice which words it
# is for: these are Greek names reaching Russian through a theta, so
# "Thomas"/«Фома», "Timothy"/«Тимофей» and "Thessalonica"/«Фессалоника»
# all line up, and they are far more of this corpus than the handful
# ("Bethlehem"/«Вифлеем") that it costs.
_TRANSLIT: Final[dict[str, str]] = {
    # Cyrillic, Russian and Ukrainian together
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "h", "д": "d", "е": "e",
    "ё": "e", "є": "e", "ж": "z", "з": "z", "и": "i", "і": "i", "ї": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "k",
    "ч": "c", "ш": "s", "щ": "s", "ъ": "", "ы": "i", "ь": "", "э": "e",
    "ю": "u", "я": "a",
    # Latin, English and German together
    "a": "a", "b": "b", "c": "k", "d": "d", "e": "e", "f": "f", "g": "h",
    "h": "h", "i": "i", "j": "i", "k": "k", "l": "l", "m": "m", "n": "n",
    "o": "o", "p": "p", "q": "k", "r": "r", "s": "s", "t": "t", "u": "u",
    "v": "v", "w": "v", "x": "ks", "y": "i", "z": "z",
    "ä": "e", "ö": "o", "ü": "u", "ß": "s", "é": "e", "è": "e", "ê": "e",
    "á": "a", "í": "i", "ó": "o", "ú": "u", "ñ": "n", "ç": "s",
}  # fmt: skip

# Applied before the table, on the lowercased Latin form, because each of
# these spells with two letters what another of our languages spells with
# one. Order matters: ``sch`` before ``ch``.
_DIGRAPHS: Final[tuple[tuple[str, str], ...]] = (
    ("sch", "ш"),
    ("ph", "ф"),
    ("th", "ф"),
    ("ch", "х"),
    ("ck", "к"),
    ("qu", "кв"),
)


def _skeleton(token: str) -> str:
    """``token`` reduced to how it sounds, in one alphabet for all four
    languages.

    «Филиппы» → ``filipi``. "Philippi" → ``filipi``. «Филіппи» →
    ``filipi``. «Пилипах» → ``pilipah``, which is the point.
    """
    lowered = token.lower()
    for digraph, single in _DIGRAPHS:
        lowered = lowered.replace(digraph, single)
    letters = []
    for char in lowered:
        mapped = _TRANSLIT.get(char)
        if mapped is None:
            continue
        letters.append(mapped)
    joined = "".join(letters)
    # Doubling is spelling, not sound, and the four languages do not
    # agree about it: «Филиппы» doubles the p and «Филипи» does not.
    collapsed: list[str] = []
    for char in joined:
        if collapsed and collapsed[-1] == char:
            continue
        collapsed.append(char)
    return "".join(collapsed)


def _memory_key(skeleton: str) -> str:
    """Where a name is filed, so its inflections all land together."""
    return skeleton[:_KEY_LENGTH]


def _first_consonant(skeleton: str) -> str:
    """The consonant a name starts with, ignoring any leading vowels.

    ``ierusalim`` and ``erusalim`` both answer ``r``, which is what lets
    «Иерусалим» meet «Єрусалим». ``filipi`` answers ``f`` and
    ``pilipah`` answers ``p``, which is what keeps the city of Philippi
    away from the apostle Philip.
    """
    for char in skeleton:
        if char not in _VOWELS:
            return char
    return ""


def _glossary_keys() -> dict[str, frozenset[str]]:
    """Names the register already decides, per language.

    Built once at import rather than cached on demand: this is read from
    provider threads (a long lesson learns from its own paragraphs as it
    goes), and a dictionary filled lazily from several threads is a race
    nobody would ever see fail and nobody could ever explain.
    """
    return {
        locale: frozenset(
            key for key in (_memory_key(_skeleton(form)) for form in known_forms(locale)) if len(key) >= _MIN_SKELETON
        )
        for locale in LOCALE_CODES
    }


_GLOSSARY_KEYS: Final[dict[str, frozenset[str]]] = _glossary_keys()


def name_candidates(text: str) -> list[str]:
    """The words in ``text`` that look like names, in order of appearance.

    The rule is "capitalised, and not because a sentence started". That
    is a weak signal in German, where every noun is capitalised, and a
    strong one in the other three. It is allowed to be weak: nothing is
    remembered from a candidate on its own — a candidate only becomes a
    memory when a word on the *other* side of the translation still
    sounds like it, and "Gemeinde" does not sound like «громада».

    Markup is stripped first, so the ``h2`` in ``<h2>Коринф`` is not a
    name and «Коринф» is not sentence-initial for being first in its tag.
    """
    if not text:
        return []
    prose = strip_tags(text) if "<" in text else text
    found: list[str] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(prose):
        word = match.group(0)
        if not word[0].isupper() or word.isupper():
            # An all-caps word is a heading or an acronym; its shape says
            # nothing about whether it is a name.
            continue
        if _opens_a_clause(prose, match.start()):
            continue
        lowered = word.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        found.append(word)
        if len(found) >= _MAX_CANDIDATES_PER_TEXT:
            break
    return found


def _opens_a_clause(prose: str, start: int) -> bool:
    """Is the capital at ``start`` grammar rather than a name?"""
    index = start - 1
    while index >= 0 and prose[index].isspace():
        index -= 1
    if index < 0:
        return True
    return prose[index] in _CLAUSE_OPENERS


def pair_names(source: str, translation: str) -> list[tuple[str, str]]:
    """Which name in ``source`` became which name in ``translation``.

    Only pairs that are unambiguous in both directions are returned: the
    target must be the source's best match by ``_MIN_MARGIN``, and the
    source must be the target's. A paragraph that names two people whose
    skeletons both half-fit the same word yields nothing, because
    guessing between them is the one outcome worse than silence.
    """
    sources = [(word, _skeleton(word)) for word in name_candidates(source)]
    targets = [(word, _skeleton(word)) for word in name_candidates(translation)]
    sources = [(word, skeleton) for word, skeleton in sources if len(skeleton) >= _MIN_SKELETON]
    targets = [(word, skeleton) for word, skeleton in targets if len(skeleton) >= _MIN_SKELETON]
    if not sources or not targets:
        return []

    scores = {
        (s_index, t_index): _similarity(s_skeleton, t_skeleton)
        for s_index, (_, s_skeleton) in enumerate(sources)
        for t_index, (_, t_skeleton) in enumerate(targets)
    }

    pairs: list[tuple[str, str]] = []
    for s_index, (source_word, _skeleton_of_source) in enumerate(sources):
        t_index = _clear_winner([(t_index, scores[s_index, t_index]) for t_index in range(len(targets))])
        if t_index is None:
            continue
        back = _clear_winner([(other, scores[other, t_index]) for other in range(len(sources))])
        if back != s_index:
            continue
        target_word = targets[t_index][0]
        if source_word.casefold() == target_word.casefold():
            # The name came through unchanged. True often enough between
            # Latin-script languages, and nothing is gained by telling a
            # model to write the word it was already going to write.
            continue
        pairs.append((source_word, target_word))
    return pairs


def _stem(skeleton: str) -> str:
    """``skeleton`` with its trailing vowels off — a poor man's lemma.

    Nothing in this pipeline knows how to decline, and it does not need
    to: names arrive inflected («Коринфе», «Коринті») and the ending is
    where the two languages differ most while meaning the same. Cutting
    it off is what lets ``korinfe`` recognise ``korinti``, which the full
    forms score at 0.71 and would otherwise miss.

    One vowel, not every trailing vowel. Stripping greedily turned
    ``maria`` into ``mar``, which is three quarters of ``mark`` — and
    Марк and Мария are two people, in a corpus where they stand next to
    each other constantly.
    """
    if len(skeleton) > _MIN_SKELETON - 1 and skeleton[-1] in _VOWELS:
        return skeleton[:-1]
    return skeleton


def _similarity(left: str, right: str) -> float:
    """How likely these two skeletons are the same name, 0 to 1.

    Two gates and then a measurement. Names that do not begin with the
    same consonant are not inflections of each other in any of these four
    languages — that is the cheap check doing most of the work, and the
    one that keeps «Филиппы» from being taught to call itself «Пилипах»,
    which is the name of a man rather than a city. Past that, the better
    of the whole forms and the de-inflected stems, because a Russian
    locative and a Ukrainian locative agree about the word and disagree
    about the ending.
    """
    if _first_consonant(left) != _first_consonant(right):
        return 0.0
    return max(
        SequenceMatcher(None, left, right).ratio(),
        SequenceMatcher(None, _stem(left), _stem(right)).ratio(),
    )


def _clear_winner(scored: list[tuple[int, float]]) -> int | None:
    """The index that wins outright, or ``None`` if the field is close."""
    ranked = sorted(scored, key=lambda item: (-item[1], item[0]))
    if not ranked or ranked[0][1] < _MIN_SIMILARITY:
        return None
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < _MIN_MARGIN:
        return None
    return ranked[0][0]


class TermMemory:
    """Names this course has already been given, per target language.

    One instance per translation pass. Written from the caller's thread
    only — the executor seeds it before the pool opens and adds to it
    after the pool closes, the same discipline that keeps the database
    out of the worker threads. ``recall`` is read-only and safe anywhere.
    """

    __slots__ = ("_by_locale",)

    def __init__(self) -> None:
        self._by_locale: dict[str, dict[str, Counter[str]]] = {}

    def learn(
        self,
        source: str,
        translation: str,
        *,
        source_locale: LocaleCode,
        target_locale: LocaleCode,
    ) -> None:
        """Record what this translation called the names in this source.

        A no-op in the direction that means nothing (a field whose source
        and target are the same language) and for a language whose
        register already fixes the word.
        """
        if source_locale == target_locale or not source or not translation:
            return
        forbidden = _GLOSSARY_KEYS.get(source_locale, frozenset())
        known = self._by_locale.setdefault(target_locale, {})
        for source_word, target_word in pair_names(source, translation):
            key = _memory_key(_skeleton(source_word))
            if key in forbidden:
                # The register decides this one, and the register is
                # authoritative — a memory that disagreed with it would
                # be two answers to the same question in one prompt.
                continue
            counted = known.get(key)
            if counted is None:
                if len(known) >= _MAX_KEYS_PER_LOCALE:
                    continue
                counted = known[key] = Counter()
            counted[target_word] += 1

    def recall(self, text: str, *, target_locale: LocaleCode) -> tuple[tuple[str, str], ...]:
        """The pairs worth putting in front of a call translating ``text``.

        Returned as ``(the form this text uses, the form the course
        used)`` — the source side is quoted from the text being
        translated rather than from the memory, so a model reading
        «Филиппах → Филіппи» is looking at its own sentence rather than
        at a dictionary headword.
        """
        known = self._by_locale.get(target_locale)
        if not known or not text:
            return ()
        offered: list[tuple[str, str]] = []
        used: set[str] = set()
        for word in name_candidates(text):
            skeleton = _skeleton(word)
            if len(skeleton) < _MIN_SKELETON:
                continue
            key = _memory_key(skeleton)
            if key in used:
                continue
            counted = known.get(key)
            if counted is None:
                continue
            settled = _plurality(counted)
            if settled is None or settled.casefold() == word.casefold():
                continue
            used.add(key)
            offered.append((word, settled))
            if len(offered) >= _MAX_OFFERED_PAIRS:
                break
        return tuple(offered)

    def known_keys(self, target_locale: LocaleCode) -> int:
        """How many distinct names are held for a language. For tests and
        for the log line that says whether the memory is doing anything."""
        return len(self._by_locale.get(target_locale, {}))


def _plurality(counted: Counter[str]) -> str | None:
    """The reading this course actually uses, or ``None`` if it is torn.

    Counting rather than taking the newest is what makes a stale or
    contradictory memory harmless: one row that says «Коринт» does not
    outvote seven that say «Коринф», and four-all says nothing.
    """
    ranked = counted.most_common(2)
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def merge_pairs(*groups: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """Several sources of pairs, first one wins, capped.

    Used where a long lesson learns from its own earlier paragraphs: what
    the course already knows comes first, what this document has just
    decided fills the rest.
    """
    merged: list[tuple[str, str]] = []
    seen: set[str] = set()
    for group in groups:
        for source_word, target_word in group:
            key = _memory_key(_skeleton(source_word))
            if key in seen:
                continue
            seen.add(key)
            merged.append((source_word, target_word))
            if len(merged) >= _MAX_OFFERED_PAIRS:
                return tuple(merged)
    return tuple(merged)


def memory_block(pairs: tuple[tuple[str, str], ...]) -> str:
    """Render the pairs as prompt lines, or an empty string for none.

    Every word of this is a preference and none of it is an instruction,
    and that is not politeness. The register check shipped a note saying
    "use our wording" and the model obediently turned "New Testament"
    into "New Covenant" — a correct translation made wrong by a hint
    that could not be declined. So the block says what the rest of the
    course happens to say, states the condition under which it applies,
    and says in as many words that the model should ignore it otherwise.
    """
    if not pairs:
        return ""
    lines = "\n".join(f"  {source} → {target}" for source, target in pairs)
    return (
        "Names already used elsewhere in this course, with the wording "
        "chosen for them there:\n"
        f"{lines}\n"
        "This is not a rule — it is what the rest of the course says. "
        "Where the text below means the same person, place or thing, use "
        "the same wording, so a reader meets one name for it and not "
        "four. Where it means something else, or where the wording does "
        "not fit the sentence, ignore the line and translate what is in "
        "front of you.\n\n"
    )


__all__ = [
    "TermMemory",
    "memory_block",
    "merge_pairs",
    "name_candidates",
    "pair_names",
]
