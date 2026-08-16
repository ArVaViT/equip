# ruff: noqa: RUF001, RUF002, RUF003
# This module's entire job is telling Cyrillic apart from Latin and
# Russian apart from Ukrainian. The "ambiguous character" lint fires
# on every letter of the evidence tables — where a Cyrillic "о" next
# to a Latin "o" is the point, not a typo.
"""Source-language detection for course-authored text.

Replaces the ``source_locale = teacher.preferred_locale`` shortcut
that conflated the teacher's UI language with the language they
actually authored content in. The bug it fixes: an English-UI
teacher who authored a Russian course ended up with
``courses.source_locale='en'``, the translation pipeline thought
the course was already in English, and Russian students saw the
Russian text labelled as English (while English students never got
a translation).

Why this is not a script counter any more
-----------------------------------------

The first version counted Cyrillic characters against Latin ones.
That is exact while the supported set is ``ru`` + ``en``, and wrong
the moment it is not: Ukrainian is Cyrillic and would come back as
``"ru"``, German is Latin and would come back as ``"en"``. That
misread is not a quality problem, it is a *reading* problem —
``pick_overlay_value`` compares the detected language against the
display locale and, on a match, serves the raw source text instead
of the overlay. A Ukrainian student would be handed Ukrainian text
while a correct Russian translation sat unread in
``content_versions``.

So detection now runs in two steps:

1. **Script** decides which locales are even possible. Cyrillic
   rules out ``en``/``de``; Latin rules out ``ru``/``uk``.
2. **Language within that script** is decided by evidence —
   script-exclusive letters (``ы э ъ ё`` vs ``і ї є ґ``, ``ä ö ü ß``),
   frequent function words, and characteristic letter sequences.

Both steps are scoped to ``LOCALE_CODES``: the detector never claims
a language the platform does not serve, and it gets *more* cautious,
never less, as languages are added. While the set is ``ru`` + ``en``
step 2 never runs — there is only one candidate per script — so this
module behaves exactly as before for today's content.

Contract
--------

``detect_locale(text)``:
* Returns a supported locale when the script is clear AND, where the
  script hosts more than one supported locale, the evidence for the
  winner beats the runner-up by ``_MIN_SCORE_MARGIN``.
* Returns ``None`` when there's no usable signal: empty input, fewer
  than ``_MIN_LETTER_COUNT`` letters, or two same-script languages
  that the text cannot tell apart. The caller is expected to fall
  back to a declared locale (the teacher's UI language, the course's
  ``source_locale``) in that case.
* Never guesses between same-script languages. "Тайтл" is Russian
  *or* Ukrainian by the letters alone; with both supported, the
  honest answer is ``None`` and the caller's declared value wins.
* Is forgiving of HTML, emojis, numbers, and punctuation — markup is
  stripped and only letters contribute to the decision.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple

from app.core.sanitize import strip_tags
from app.schemas.locale import LOCALE_CODES

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

# Minimum number of script-tagged letters before the detector is
# willing to commit to a locale. Below this we return ``None`` so
# the caller falls back to a deterministic default (teacher UI).
#
# 3 is empirically the right number for our content: it catches
# single-word titles like "Тайтл" (5 Cyrillic letters), "Genesis"
# (7 Latin letters), and "Yes" / "Хай" while rejecting "Hi" / "Да"
# which are too short to disambiguate from acronyms or interjections.
_MIN_LETTER_COUNT: Final[int] = 3

# How far ahead the winning language must be before we act on it,
# when its script hosts more than one supported locale. One
# exclusive letter (weight 3) or one function word (weight 2) is
# enough — those are hard signals, a Ukrainian "ї" does not appear
# in Russian prose. A tie, or a one-point lead from a single shared
# letter sequence, is not enough.
_MIN_SCORE_MARGIN: Final[int] = 2

# Evidence weights. Exclusive letters outrank function words, which
# outrank letter sequences: "ї" can only be Ukrainian, "die" is
# usually German but is also an English verb, "sch" merely leans.
_WEIGHT_EXCLUSIVE_LETTER: Final[int] = 3
_WEIGHT_FUNCTION_WORD: Final[int] = 2
_WEIGHT_SEQUENCE: Final[int] = 1

# Each kind of evidence saturates, so one long paragraph cannot
# outvote the other signals by sheer repetition.
_MAX_HITS_PER_KIND: Final[int] = 5

_CYRILLIC = "cyrillic"
_LATIN = "latin"

_WORD_RE: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+", re.UNICODE)

_CYRILLIC_START: Final[int] = 0x0400
_CYRILLIC_END: Final[int] = 0x04FF

# Latin letters carrying diacritics live outside ASCII (ä, ö, ü, é,
# ß…). They are Latin script and must be counted as such, or a
# German sentence loses exactly the characters that identify it.
_LATIN_EXTENDED_RANGES: Final[tuple[tuple[int, int], ...]] = (
    (0x00C0, 0x024F),  # Latin-1 Supplement + Extended-A/B
)


# Above this many letters of the script, the *absence* of a language's
# hallmark letters becomes evidence against it — see ``_absence_bonus``.
#
# This was 20 on the reasoning that a Ukrainian text of three words
# without a single "і/ї/є" would be a freak occurrence. Measured
# against every Ukrainian string in production, that reasoning is
# simply wrong:
#
#     letters   strings   without і/ї/є
#      20-39       584      61   (10%)
#      40-59       355       9   (2.5%)
#      60-79       180       0
#      80+         ~380      1
#
# One in ten. "Модуль 3. Друга половина: чотири групи" and "Уздовж
# узбережжя Середземного моря" are ordinary Ukrainian, and the rule
# read them as Russian — which the validator then reported as the wrong
# language, on correct translations, in production.
#
# 60 is where the measurement says the absence starts meaning
# something. Even there it is not a proof, which is why it stays worth
# less than a matched function word rather than more.
_ABSENCE_MIN_LETTERS: Final[int] = 60


class _Profile(NamedTuple):
    """Evidence that identifies one language inside its script.

    ``exclusive_letters`` are letters no other supported language of
    the same script uses. ``function_words`` are frequent closed-class
    words — the ones that appear even in a two-line course title.
    ``sequences`` are letter combinations that lean towards the
    language without proving it.

    ``hallmark_letters`` is the subset of ``exclusive_letters`` common
    enough that a text of ``_ABSENCE_MIN_LETTERS`` in this language
    would almost certainly contain one. Their absence then counts
    *for* the other languages of the same script. Ukrainian "і" alone
    is ~7% of all letters, so it qualifies; Russian "ы э ъ ё" together
    are ~2.5%, and "Изучаем первую книгу Библии вместе" is a perfectly
    ordinary Russian sentence without any of them — so Russian leaves
    this empty and argues from its own evidence instead.
    """

    script: str
    exclusive_letters: frozenset[str]
    function_words: frozenset[str]
    sequences: tuple[str, ...]
    hallmark_letters: frozenset[str] = frozenset()


# Function-word lists, written as prose and split at import. Same data
# as a set literal, but readable as a list of words and left alone by
# the formatter — which prints a set literal one word per line and
# buries the module under 400 lines of nouns.
_RU_WORDS = """
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли
если уже или ни быть был него до вас опять уж вам ведь там потом себя ничего ей
может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего
раз тоже себе под будет тогда кто этот того потому этого какой совсем ним здесь
этом один почти мой тем чтобы нее были куда зачем всех никогда можно при наконец
два об другой хоть после над больше тот через эти нас про всего них какая много
разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя
такой им более всегда конечно всю между тебе
"""

_UK_WORDS = """
і та що як це для не в у на з із зі до від або який яка які яке є був була було
були ми ви вони він вона воно щоб коли тому бо ще вже де тільки але також ні так
її його їх цей ця цього цьому може має треба потрібно після перед між через про
над під при без усі всі нам вам їм мене тебе себе свій своя своє більше менше
дуже чи хто кожен жодного
а за нас вас ним нею них той ті ці тут там тоді потім знову завжди ніколи
можна буде будуть мають серед крім проти разом майже теж лише навколо довкола
замість щодо попри задля поруч один два три
"""
# Why the second block exists: the first list was written as "the words
# a course title uses", and it left out the ordinary connective tissue —
# "а", "за", "той", "все". Those are in the Russian list, so a Ukrainian
# sentence built out of them scored 4:0 for Russian. "Урок 10. Листи
# Павла: порядок за довжиною, а не за часом" was read as Russian in
# production, on a correct translation, for exactly that reason.
#
# Most of the additions are words the two languages share ("а", "за",
# "тут", "все"), so the ambiguity rule below drops them from scoring
# for both — which is the point. A word only helps when it belongs to
# one language.
#
# The first attempt at this list also carried content words — слово,
# люди, сказав, такий — and they made it worse in the other direction:
# "Слово Божие" is Russian and scored for Ukrainian on "слово" alone.
# Measured over every string in production, that turned 1 Russian row
# read as Ukrainian into 17. Closed class only, and nothing that a
# Russian sentence says just as often.

_EN_WORDS = """
the and is of to in a for with that this on are was were it as be by from or an
we you they he she his her their but not have has had will would can could what
when which who how there these those been than then them its our your about into
over after before between through each all any some one two first also more
other such only own same so if because while during against without within upon
"""

_DE_WORDS = """
der die das und ist nicht ein eine einen einem einer eines für mit zu zur zum den
dem des sich auf von vom im in an am wir sie er es aber oder auch wenn wie dass
war waren sind haben hat hatte werden wird kann können nach bei über durch noch
nur schon als so man ihr ihre sein seine diese dieser dieses alle mehr sehr
wieder hier dort damit weil denn beim unter gegen ohne um vor aus ich du mir
mich dich was wurde wurden würde laut dann dazu jeder jede jedes kein keine
welche welcher welches soll sollen muss müssen wem wen wessen weil zwischen
darauf worin wodurch heißt gibt geben nun etwa
"""

_PROFILES: Final[dict[str, _Profile]] = {
    "ru": _Profile(
        script=_CYRILLIC,
        # Ukrainian has none of these; they are the cleanest ru/uk split.
        exclusive_letters=frozenset("ыэъё"),
        function_words=frozenset(_RU_WORDS.split()),
        # The last five are the vowel pairs Russian writes where
        # Ukrainian writes an "і" form: Библии / Біблії, послание /
        # послання, первую / першу. They carry a Russian sentence that
        # happens to contain none of "ы э ъ ё" — "Изучаем первую книгу
        # Библии вместе" is exactly that, and with the absence rule now
        # requiring real length, orthography is what is left to argue
        # from.
        sequences=("ого", "ому", "ться", "ешь", "ает", "ение", "ый", "ий", "ах", "ями", "ии", "ие", "ию", "ую", "ые"),
    ),
    "uk": _Profile(
        script=_CYRILLIC,
        # Russian has none of these. "ґ" is rare but decisive.
        exclusive_letters=frozenset("іїєґ"),
        function_words=frozenset(_UK_WORDS.split()),
        sequences=("ння", "ський", "ої", "ими", "ють", "ати", "ність", "ів", "ах"),
        # "і" is the second most frequent letter in Ukrainian. A
        # Ukrainian paragraph without one does not realistically occur.
        hallmark_letters=frozenset("іїє"),
    ),
    "en": _Profile(
        script=_LATIN,
        # English has no letter German lacks; it wins on words.
        exclusive_letters=frozenset(),
        function_words=frozenset(_EN_WORDS.split()),
        # Deliberately excludes "tion" and "ing": German has Lektion,
        # Information, Ding, bringen. A sequence both languages own is
        # not evidence, it is noise that cancels a real signal —
        # "Lektion 3. Das Gebet" scored 2:1 for German and fell below
        # the margin because of "tion" alone.
        sequences=("ough", "igh", "th", "wh", "ness", "ould", "ay"),
    ),
    "de": _Profile(
        script=_LATIN,
        exclusive_letters=frozenset("äöüß"),
        function_words=frozenset(_DE_WORDS.split()),
        sequences=("sch", "ung", "keit", "heit", "cht", "eit", "lich", "chen", "ei", "eu"),
    ),
}


# A word two languages share is not evidence about which one this is.
#
# "was" is the case that cost a production row: German's most ordinary
# interrogative and English's past tense of "to be". It sat in the
# English list and not the German one, so "Was wurde laut 1. Mose 2,1
# vollendet?" — six German words — scored 1:0 for English and was
# parked as the wrong language.
#
# Adding it to German alone would have swapped the error. Computing the
# overlap and dropping it from every profile is the rule that holds:
# what remains in each list is what only that language says. It also
# scales — a fifth language that shares half its closed class with a
# fourth cannot poison either.
_AMBIGUOUS_WORDS: Final[frozenset[str]] = frozenset(
    word
    for word in {w for profile in _PROFILES.values() for w in profile.function_words}
    if sum(word in profile.function_words for profile in _PROFILES.values()) > 1
)


class _Counted(NamedTuple):
    cyrillic: int
    latin: int


def _is_latin(ch: str, codepoint: int) -> bool:
    """ASCII letters plus the accented Latin blocks.

    German loses exactly the characters that identify it if "ä ö ü ß"
    are not counted as Latin.
    """
    if ch.isascii():
        return True
    return any(start <= codepoint <= end for start, end in _LATIN_EXTENDED_RANGES)


def _count_scripts(text: str) -> _Counted:
    cyrillic = 0
    latin = 0
    for ch in text:
        if not ch.isalpha():
            continue
        codepoint = ord(ch)
        if _CYRILLIC_START <= codepoint <= _CYRILLIC_END:
            cyrillic += 1
        elif _is_latin(ch, codepoint):
            latin += 1
    return _Counted(cyrillic=cyrillic, latin=latin)


def _supported_candidates(script: str) -> list[str] | None:
    """Supported locales written in ``script``.

    Returns ``None`` when ``LOCALE_CODES`` contains a locale this
    module has no profile for. That is a configuration error — step 5
    of the "adding a language" checklist in ``app/schemas/locale.py``
    was skipped — and the safe response is to detect nothing rather
    than to hand the new language's text to whichever profile happens
    to share its script. ``test_language_detection`` fails on the
    same condition, so CI catches it before production does.
    """
    if any(code not in _PROFILES for code in LOCALE_CODES):
        return None
    return [code for code in LOCALE_CODES if _PROFILES[code].script == script]


def _absence_bonus(code: str, candidates: list[str], letters: str, letter_count: int) -> int:
    """Credit ``code`` for every rival whose hallmark letters are missing.

    Evidence from absence, and only in the direction where absence
    means something. A Russian sentence can easily avoid "ы э ъ ё",
    which is why Russian claims no hallmarks and gets no free pass —
    but a Ukrainian sentence of this length avoiding "і ї є" would be
    a curiosity, so its absence is a real argument for the other
    Cyrillic languages.
    """
    if letter_count < _ABSENCE_MIN_LETTERS:
        return 0

    bonus = 0
    for rival in candidates:
        if rival == code:
            continue
        hallmarks = _PROFILES[rival].hallmark_letters
        if hallmarks and not any(ch in hallmarks for ch in letters):
            bonus += _WEIGHT_FUNCTION_WORD
    return bonus


def _score(profile: _Profile, letters: str, words: set[str], haystack: str) -> int:
    exclusive = sum(1 for ch in letters if ch in profile.exclusive_letters)
    function_words = len(words & profile.function_words - _AMBIGUOUS_WORDS)
    sequences = sum(1 for seq in profile.sequences if seq in haystack)

    return (
        min(exclusive, _MAX_HITS_PER_KIND) * _WEIGHT_EXCLUSIVE_LETTER
        + min(function_words, _MAX_HITS_PER_KIND) * _WEIGHT_FUNCTION_WORD
        + min(sequences, _MAX_HITS_PER_KIND) * _WEIGHT_SEQUENCE
    )


def detect_locale(text: str | None) -> LocaleCode | None:
    """Return the detected locale, or ``None`` if the input is too short
    or the evidence does not separate two same-script languages.

    Script decides the candidate set; within a script, exclusive
    letters, function words, and letter sequences decide the winner.
    A winner must lead by ``_MIN_SCORE_MARGIN`` — otherwise this
    returns ``None`` and the caller uses its declared locale.
    """
    if not text:
        return None

    # Tag names are Latin letters: `<strong>` used to vote against a
    # short Cyrillic paragraph wrapped in markup.
    stripped = strip_tags(text)
    counted = _count_scripts(stripped)

    total = counted.cyrillic + counted.latin
    if total < _MIN_LETTER_COUNT:
        return None

    script = _CYRILLIC if counted.cyrillic > counted.latin else _LATIN
    candidates = _supported_candidates(script)
    if not candidates:
        # Either the platform serves no language in this script, or a
        # locale is missing its profile. Both mean "do not decide".
        return None
    if len(candidates) == 1:
        return candidates[0]  # type: ignore[return-value]

    lowered = stripped.lower()
    words = set(_WORD_RE.findall(lowered))
    script_letters = counted.cyrillic if script == _CYRILLIC else counted.latin
    scored = sorted(
        (
            (
                code,
                _score(_PROFILES[code], lowered, words, lowered)
                + _absence_bonus(code, candidates, lowered, script_letters),
            )
            for code in candidates
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )

    best_code, best_score = scored[0]
    runner_up_score = scored[1][1]
    if best_score <= 0 or best_score - runner_up_score < _MIN_SCORE_MARGIN:
        return None
    return best_code  # type: ignore[return-value]


# Enough letters that the text is prose rather than a label. Two or three
# words: below it sit the strings that read the same in every language we
# serve — "OK", "2026", "Genesis", a person's name, a course code.
_PROSE_MIN_LETTERS: Final[int] = 12


def carries_language(text: str | None) -> bool:
    """Whether this text is written in *a* language, whoever's it is.

    ``detect_locale`` answers "which language"; this answers the prior
    question, and the two disagree in a way that matters. A detector that
    returns ``None`` on "Апостол Павло написав це послання" — a Ukrainian
    sentence that happens to avoid і, ї and є — has not established that the
    text is language-neutral. It has only failed to name the language.

    The resolve path leans on the difference. Text that carries no language
    is served to everyone, because it is the same string in every language.
    Text that carries one the reader did not choose is not served at all,
    even when we cannot say which language it is: an unnamed foreign
    language is still foreign.
    """
    if not text:
        return False
    counted = _count_scripts(strip_tags(text))
    return counted.cyrillic + counted.latin >= _PROSE_MIN_LETTERS
