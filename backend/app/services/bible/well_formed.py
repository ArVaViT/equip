# ruff: noqa: RUF001, RUF002, RUF003
# The subject matter here is individual Cyrillic letters and the words they
# do or do not spell. A Cyrillic letter meant to be a Cyrillic letter is not
# a homoglyph typo.
"""Is what the publisher sent back actually a verse — and if not, can it be mended?

The substitution layer inserts canonical Scripture verbatim, which is
right: an edition prints the verse, we do not paraphrase it, and the
whole point of ``api_source`` is that the publisher's own copy beats a
bundle that silently rots. What nothing checked is whether the copy that
came back is *well formed*.

Production, read on 2026-08-20, ``daily_challenge_option`` in Ukrainian::

    Псалом 23:1 ('Псальма Давидова. Г осподь пастирь мій, …')

``Г осподь`` is ``Господь`` with a space through the middle of it. The
row is ``status='ok'``; every structural check passed, because every
structural check compares a translation with its source and this text is
neither — it is Scripture, inserted after the model was done, from
outside. Ten more rows carry it, every one of them a Psalm.

The cause is typographic, not linguistic. Куліш 1905 sets a large
initial capital on the first word of a psalm's body and the digitisation
behind the API turned that initial into a separate letter: ``Г осподи``,
``Н ебеса``, ``П омилуй``, ``Х то``, ``Б оже``, ``С казав``. It happens
at the opening of a psalm and nowhere else, which is why the Psalter is
riddled with it and the Gospels are clean.

Mend where the mend is provable, refuse where it is not
-------------------------------------------------------
The first version of this module only refused, and refusing was the
wrong default. A refused verse falls back to the author's own words,
which for these rows are English — so a Ukrainian student would have
read ``Псалом 8:1 (KJV) говорить: 'O LORD our Lord…'``. Weigh the two
failures as that student meets them. ``Г осподь пастирь мій`` is a
typographic artifact: every word is legible, and at worst the edition
reads as old, which it is. An English verse inside a Ukrainian lesson is
the product failing to speak the reader's language on the one line in a
Bible school that most has to be theirs. Refusing traded the smaller
failure for the larger one, deliberately, on ten rows.

And the repair rests on the fact the detection already established. If a
letter is not a word in this language, it is not standing on its own; it
belongs to the token beside it. Detection and repair read the same
measurement, so a rule trusted to withhold a verse is trusted to close
the gap it found.

One refinement, because the two are not perfectly symmetrical. A wrong
refusal costs one verse and says so in the log. A wrong repair changes
Scripture and says nothing. Equal evidence, unequal consequences — so
the repair asks for one thing the detection does not:

    the stranded letter is a **capital**, and what follows it after a
    single space begins **lowercase**, in the same script.

That closes the reading. Joined backwards, a capital would land inside a
word, which no orthography here writes. Left apart, a non-word stands
alone. The only well-formed reading left is one capitalised word, and it
is reached without a dictionary and without a guess. Every one of the
production defects has that shape; anything that does not is refused
exactly as before.

This is still not editing Scripture. The 1905 Psalter prints ``Господь``
with a decorative initial; the digitisation of it emits ``Г осподь``, so
the text that arrives is *already* not what the edition prints. Removing
the space restores the edition's word rather than choosing a different
one — which is the whole distinction, and it holds only while the
reconstruction is unique. The capitalisation condition is what keeps it
unique, and the day a case stops being unique it gets refused, not
guessed.

What this module does NOT claim to be
-------------------------------------
It is not a spell checker and must not become one. It answers one
question — *is there a letter standing alone that is not a word?* — from
a closed list of the one-letter words each language has, which is short,
finite, and the same next year.

That narrowness is the whole design. The obvious wider rule — "a single
letter opening a sentence, followed by a lowercase word" — was written,
measured against 1,081 verses fetched live from all four editions on
2026-08-20, and scored **314 hits, every one of them real**: ``И глаз не
может сказать руке``, ``І рече Господь Самуїлові``, ``Я отверг его как
царя``, ``I am sending you to Jesse``. A conjunction opening a sentence
is not a defect, it is Russian. The rules below score **zero** on those
same 1,081 verses — and because the mend only ever runs where they fire,
that same zero bounds how often Scripture is touched.

Archaic is not broken
---------------------
Куліш is a pre-1928 edition and the owner's decision to keep it stands
(``translation/version.py``, generation 2). ``дїло``, ``сьвятий`` and
``тїла`` are how it spells and nothing here objects.

Neither does anything here object to ``жити ме``. The analytic future —
an infinitive plus ``ме``/``му``/``меш``/``мете``/``мемо`` — is set as
two words throughout this edition: ``глаголати ме вам``, ``судити ме
вселенну``, ``слухати ме слова``, ``жити ме в кучках``, ``дожинати
меш``, ``їсти мемо``, ``не мати му недостатку``. Twenty-odd verses
across Genesis, Exodus, Leviticus, Joshua, Acts and the Epistles, always
after an infinitive, always the same six endings: that is
nineteenth-century orthography applied consistently, not a space that
fell into one word, and a checker that "corrected" it would be
overruling the edition rather than repairing it.
``test_a_verse_with_a_space_through_a_word.py`` pins this, and it is the
test to read before widening anything here.

What is still missed, and why it is left missed
-----------------------------------------------
Psalm 121:1 comes back as ``О чі мої підношу на гори``. ``о`` is a real
Ukrainian word — the same edition writes ``на молитву о девятій
годинї`` — so the stranded initial is indistinguishable from the
vocative in ``о Боже`` or ``о нерозумні Галати`` without a dictionary.
Seeing it would mean refusing those, and mending it would mean rewriting
them. It is named in the PR so a person can decide, which is the honest
place for a judgement a program cannot make.

Mending is a pure function
--------------------------
``mend`` depends on nothing but its two arguments, so one verse mends to
the same bytes in every process and every deploy, and mending a mended
verse changes nothing further — the stranded letter is no longer a
one-letter token, and joining only ever removes a space. Neither fact is
incidental: a translation re-made next month has to land on the same
text as the one made today, or every row would look edited on every
sweep. ``source_hash`` is untouched either way; it is computed over the
author's source text, and Scripture arrives after the model is done.

What happens to a verse that cannot be mended
---------------------------------------------
``fetch_verse`` returns ``None``, which its callers have always read as
"no canonical text" and answered by keeping the author's own quotation.
Nothing is dropped — the defect this project already had once, when a
translated placeholder left a reference standing over a hole (see
generation 3) — and nothing is guessed.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: A word, for the purpose of "is this letter standing on its own".
#: Apostrophes are inside words — ``об'явлення``, ``God's`` — so a
#: possessive must not read as a stranded ``s``.
_TOKEN: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+(?:['’ʼ`][^\W\d_]+)*")

#: Every letter that is a word by itself, per language and per script.
#:
#: Per language rather than per script, because the difference decides
#: cases. ``с`` is a preposition in Russian and appears 67 times in the
#: Russian edition; it is not a Ukrainian word — Ukrainian writes ``з``
#: — and the Ukrainian edition uses it not once in 271 verses. Keeping
#: one shared list would have to allow ``с`` everywhere, and Psalm 110:1
#: would go on reading ``С казав Господь моєму Господеві``.
#:
#: Verified against 1,081 verses fetched live from the four editions on
#: 2026-08-20: every one-letter token in every one of them is listed
#: below for its own language. A letter wrongly present costs recall on
#: one shape of defect; a letter wrongly absent costs a reader a verse,
#: so where the language is not certain the generous reading wins.
_ONE_LETTER_WORDS: Final[dict[str, frozenset[str]]] = {
    # а и о у я в к с б ж — conjunction, preposition, pronoun, particle.
    "ru": frozenset("абвжикосуя"),
    # No ``и`` (Ukrainian writes ``і``), no ``к`` and no ``с``.
    "uk": frozenset("абвєжзійоуя"),
    # German has one: the vocative ``o Mensch``.
    "de": frozenset("o"),
    # ``a``, ``I``, and the vocative ``O LORD``.
    "en": frozenset("aio"),
}

#: The union, used when the text is in no locale we hold a list for.
#: Wider means quieter, which is the right way round for a locale
#: nobody has measured.
_ANY_ONE_LETTER_WORD: Final[frozenset[str]] = frozenset().union(*_ONE_LETTER_WORDS.values())

#: Scripts whose one-letter words we can enumerate at all. A verse in
#: Greek or Hebrew gets no opinion rather than a guess.
_KNOWN_SCRIPTS: Final[frozenset[str]] = frozenset({"CYRILLIC", "LATIN"})

#: Enclitic particles: they lean backwards onto the word before them and
#: cannot open a sentence in Russian or Ukrainian. One that does open a
#: sentence is not a particle but the head of the next word, which is how
#: ``Боже мій`` came back as ``Б оже мій`` in Psalm 22:1 and
#: ``Благослови, душе моя`` as ``Б лагослови`` in Psalm 103:1.
#:
#: This is grammar, not a measurement, which is why the list stops at
#: two letters and does not grow to cover ``о``. See the module note.
_ENCLITIC: Final[frozenset[str]] = frozenset("бж")

#: What a sentence ends with, including the marks an edition closes a
#: quotation or a psalm superscription with.
_SENTENCE_END: Final[str] = ".!?;:»”’\"')"

#: How much text to hand back with a complaint: enough for a person
#: reading the log to recognise the verse, short enough not to paste a
#: passage into it.
_CONTEXT: Final[int] = 40

#: Stands in for a combining mark while the text is being analysed. The
#: Russian edition prints stress on a name it expects to be misread —
#: ``Дура́`` — and a combining acute is not a letter, so a tokenizer
#: splits the word around it and invents a stranded letter that was never
#: there. Substituting rather than deleting keeps every offset where it
#: was, which is what lets the mend cut a space out of the *original*
#: string and leave the edition's own diacritics alone.
_MARK_STAND_IN: Final[str] = "a"


def _script_of(char: str) -> str:
    return unicodedata.name(char, " ").partition(" ")[0]


def _for_analysis(text: str) -> str:
    """``text`` with combining marks replaced one-for-one, so tokens read
    correctly and every index still points at the same character."""
    if not any(unicodedata.category(char) == "Mn" for char in text):
        return text
    return "".join(_MARK_STAND_IN if unicodedata.category(char) == "Mn" else char for char in text)


def _opens_a_sentence(text: str, start: int) -> bool:
    before = text[:start].rstrip()
    return before == "" or before[-1] in _SENTENCE_END


def _is_stranded(token: str, text: str, start: int, words: frozenset[str]) -> bool:
    """Whether this one-letter token is a letter that is not a word here."""
    if _script_of(token) not in _KNOWN_SCRIPTS:
        return False
    letter = token.lower()
    return letter not in words or (letter in _ENCLITIC and _opens_a_sentence(text, start))


def _joins_forward(token: str, text: str, end: int) -> bool:
    """Whether the only well-formed reading of this stranded letter is as
    the initial of the word after it.

    A capital followed by a single space and a lowercase letter of the
    same script has exactly one reading: joined backwards the capital
    would sit inside a word, and left alone it is not a word at all.
    Anything else is ambiguous and gets refused rather than guessed.
    """
    if not token.isupper():
        return False
    tail = text[end:]
    if not tail.startswith(" ") or len(tail) < 2:
        return False
    following = tail[1]
    return following.isalpha() and following.islower() and _script_of(following) == _script_of(token)


def malformed_fragment(text: str, locale: str) -> str | None:
    """The neighbourhood of the first stranded letter in ``text``, or
    ``None`` when every letter in it belongs to a word.

    The return value is for a log line, not for a reader: it says which
    verse to go and look at.
    """
    words = _ONE_LETTER_WORDS.get(locale, _ANY_ONE_LETTER_WORD)
    analysis = _for_analysis(text)
    for match in _TOKEN.finditer(analysis):
        token = match.group()
        if len(token) != 1 or not _is_stranded(token, analysis, match.start(), words):
            continue
        return text[max(0, match.start() - _CONTEXT) : match.end() + _CONTEXT].strip()
    return None


def mend(text: str, locale: str) -> str:
    """``text`` with every provably stranded initial joined back to its
    word, and everything else left exactly as the publisher sent it.

    Pure, and a fixed point: mending a mended verse changes nothing,
    because the joined letter is no longer a one-letter token and a join
    only ever removes a space.
    """
    words = _ONE_LETTER_WORDS.get(locale, _ANY_ONE_LETTER_WORD)
    analysis = _for_analysis(text)
    cuts: list[int] = []
    for match in _TOKEN.finditer(analysis):
        token = match.group()
        if len(token) != 1 or not _is_stranded(token, analysis, match.start(), words):
            continue
        if _joins_forward(token, analysis, match.end()):
            cuts.append(match.end())
    if not cuts:
        return text
    pieces: list[str] = []
    read_from = 0
    for cut in cuts:
        pieces.append(text[read_from:cut])
        read_from = cut + 1  # the space that should never have been there
    pieces.append(text[read_from:])
    return "".join(pieces)


__all__ = ["malformed_fragment", "mend"]
