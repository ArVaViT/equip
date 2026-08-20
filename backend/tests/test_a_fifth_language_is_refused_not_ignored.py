"""What a fifth language actually costs, answered by CI instead of by opinion.

``test_adding_a_language_is_a_config_change.py`` proves the easy half:
turn a locale on and the pipeline demands it, queues it and stops asking
once it has it, with nobody holding a list. This file is the other half
— the tables where a person still has to write something down, and what
happens on the day they do not.

The answer used to be: nothing happens. Three tables in the translation
pipeline were keyed by locale and answered "nothing wrong" about a
language they had never heard of.

* the terminology register indexed its rows by a hand-written
  ``{"ru": 0, "en": 1, ...}``; a fifth locale got ``None``, ``terms_in``
  returned ``[]``, and every prompt into that language went out with no
  terminology at all. «завет» comes back one way in one lesson and
  another way in the next — the exact defect the register exists to
  prevent, with the register switched off and reporting success;
* the numeral check kept its own frozenset of languages and returned
  ``[]`` for anything else, forever. A translation that turns
  «двенадцать» into *Fünf* passed;
* the typography pass kept a frozenset too, and had a test that failed
  if a served locale was missing from it — a test satisfied by adding
  one word to the set, because the pass's own quote rules ended in
  "otherwise set it in «…»". A fifth language was pointed like Russian
  and the guard called that a pass.

CI was green through all of it. The reader was the first to find out.

So: every per-language table is listed in ``_TABLES`` below with the set
of languages it actually carries, and two things are asserted about
each. That it covers every language the platform serves — which is what
turns red the day ``LOCALE_CODES`` grows and the table does not. And
that it does *not* carry ``FIFTH``, a locale nobody serves, because a
coverage assertion nothing can fail is not a guard. The three tables
that can now be asked directly are asked, and have to refuse in a
sentence that names the table and the work.

**Tables deliberately not in this list**, because "covers every served
language" is the wrong question for them:

* ``bible/books.py::_LOCALE_ALIASES`` — *extra* spellings a language's
  readers use beyond the names the platform prints. A language with no
  extra spellings needs no entry; its printed names are covered by
  ``_DISPLAY_NAMES``, which is in the list.
* ``bible/store.py::_FILES`` and ``api_source.py::TRUSTED_BUNDLE_LOCALES``
  — the two scriptures shipped in the repo. Deliberately not a roster:
  every other language reads the API, and both are pinned exactly by
  ``test_wrong_scripture_is_never_quoted.py``.
* ``bible/psalm_numbering.py::SEPTUAGINT_LOCALES`` — a fact about which
  *edition* a language reads, not about the language. Membership is
  earned by the edition's numbering, not by being served.
* ``translation/validation.py::_PAIRS_TOLD_APART_AT_ANY_LENGTH`` — a set
  of language *pairs*, and absence is the strict direction: an unlisted
  pair gets more scrutiny, not less.
* ``legal/registry.py::LOCALES`` — ru and en, with the English text
  governing. Recorded as a decision in that module, and a reader in a
  fifth language correctly gets the governing text.
* ``glossary.py::_NOT_A_TERM_HERE`` — a flat list of fixed names, with
  no per-language structure to check. Missing a language's "New
  Testament" costs one advisory note on a handful of strings, not a
  check that has stopped checking.
* ``org_settings`` ``school_name_ru`` / ``school_name_en`` — database
  columns, not a table in Python. A language is added there by a
  migration, and the ``CHECK`` constraints on the locale columns raise
  rather than accept an unknown code.
* ``daily_challenge/admin.py::_active_cv_rows`` — not a table, but the
  same defect and found while writing this list: a ``locale IN
  ('en', 'ru')`` filter underneath two callers that fan out over
  ``LOCALE_CODES`` and say so in their docstrings. It is fixed in the
  same change as this file, and pinned where it belongs — by a German
  row travelling to the review screen, in
  ``test_daily_challenge_bilingual.py``, rather than by counting
  entries in a list.
* Everything in ``frontend/`` — same property, different runner. See
  ``frontend/src/i18n/__tests__/aFifthLanguage.test.ts``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

import pytest

from app.core.i18n import _CATALOG
from app.schemas.locale import LOCALE_CODES, LOCALE_DISPLAY_NAMES, QUOTATION_MARKS, LanguageNotInTable
from app.services.bible.api_source import API_BIBLE_IDS
from app.services.bible.books import _ALIAS_PRECEDENCE, _DISPLAY_NAMES
from app.services.language_detection import _PROFILES
from app.services.translation.glossary import (
    _TERMS,
    _verify_every_term_is_written_in_every_language,
    known_forms,
    terms_in,
)
from app.services.translation.numerals import (
    Numeral,
    _verify_every_number_is_spelled_in_every_language,
    numbers_lost,
)
from app.services.translation.prompt import _target_language_notes, build_system_prompt
from app.services.translation.typography import _APOSTROPHE_RULES, normalize_typography

if TYPE_CHECKING:
    from collections.abc import Callable

#: A language this platform does not serve, and the same one
#: ``test_adding_a_language_is_a_config_change.py`` switches on. Nothing
#: about the choice matters except that it is not in ``LOCALE_CODES``.
FIFTH: Final[str] = "pl"

#: The roster as it would read the moment somebody starts step 1 of the
#: checklist in ``app/schemas/locale.py`` — the state every table below
#: has to survive being asked about.
WITH_A_FIFTH: Final[tuple[str, ...]] = (*LOCALE_CODES, FIFTH)


class _Table(NamedTuple):
    """One per-language table, and the languages it actually carries."""

    where: str
    #: Not the table itself: what it *covers*. A dict covers its keys; a
    #: table of positional rows covers as many languages as its rows are
    #: wide; a function covers the languages it answers for.
    covers: frozenset[str]
    #: What a person does about it, in the imperative, because whoever
    #: reads this failure is halfway through adding a language.
    fix: str


def _languages_the_register_has_columns_for() -> frozenset[str]:
    """The register's rows are positional, so its coverage is a width.

    Read against ``LOCALE_CODES`` in order, which is the invariant
    ``glossary._COLUMN`` now encodes by being derived from it rather
    than written out a second time.
    """
    return frozenset(LOCALE_CODES[: min(len(row) for row in _TERMS)])


def _languages_the_prompt_has_notes_for() -> frozenset[str]:
    """Asked rather than read: the notes are a local dict inside the
    builder, and probing it is the only honest way to learn what it
    answers for. ``FIFTH`` is probed too, so this cannot pass by never
    looking."""
    return frozenset(code for code in WITH_A_FIFTH if _target_language_notes(code))  # type: ignore[arg-type]


_TABLES: Final[dict[str, _Table]] = {
    "LOCALE_DISPLAY_NAMES": _Table(
        "app/schemas/locale.py",
        frozenset(LOCALE_DISPLAY_NAMES),
        "Add the language's name in English — it is how the model is addressed.",
    ),
    "QUOTATION_MARKS": _Table(
        "app/schemas/locale.py",
        frozenset(QUOTATION_MARKS),
        "Add the pair of marks the language sets a quotation in. Both the typography "
        "pass and the verse restorer read this one, so the two agree by construction.",
    ),
    "i18n._CATALOG": _Table(
        "app/core/i18n.py",
        frozenset(_CATALOG),
        "Add a key block with every key translated; scripts/translate_catalog.py drafts it.",
    ),
    "books._DISPLAY_NAMES": _Table(
        "app/services/bible/books.py",
        frozenset(_DISPLAY_NAMES),
        "Name all 66 books in the language, or references cannot be localized at all.",
    ),
    "books._ALIAS_PRECEDENCE": _Table(
        "app/services/bible/books.py",
        frozenset(_ALIAS_PRECEDENCE),
        "Add the language to the precedence tuple. The import-time loop that registers "
        "book names iterates *this*, not LOCALE_CODES, so a language missing here has "
        "its names printed and never parsed back.",
    ),
    "API_BIBLE_IDS": _Table(
        "app/services/bible/api_source.py",
        frozenset(API_BIBLE_IDS),
        "Choose an edition for the language and record its YouVersion id.",
    ),
    "language_detection._PROFILES": _Table(
        "app/services/language_detection.py",
        frozenset(_PROFILES),
        "Write the language's profile — script, exclusive letters, function words. "
        "Until it exists, detection switches itself off for every language.",
    ),
    "glossary._TERMS": _Table(
        "app/services/translation/glossary.py",
        _languages_the_register_has_columns_for(),
        "Give every row of the register the language's form, in LOCALE_CODES order.",
    ),
    "numerals.Numeral": _Table(
        "app/services/translation/numerals.py",
        frozenset(Numeral._fields[1:]),
        "Add a field to Numeral and the number written out in all 24 rows.",
    ),
    "typography._APOSTROPHE_RULES": _Table(
        "app/services/translation/typography.py",
        frozenset(_APOSTROPHE_RULES),
        "Say what the language does with a single mark. None is an answer; absence is not.",
    ),
    "prompt._target_language_notes": _Table(
        "app/services/translation/prompt.py",
        _languages_the_prompt_has_notes_for(),
        "Write the language's house-style notes, or the model is asked for it with "
        "rule 10 of the system prompt silently missing.",
    ),
}


class TestEveryTableCarriesEveryLanguageServed:
    """The forcing function. Add a code to ``LOCALE_CODES`` and this
    turns red once per table still to be filled, each with the work
    named — which is the list nobody has to keep by hand."""

    @pytest.mark.parametrize("name", list(_TABLES))
    def test_it_carries_them(self, name: str) -> None:
        table = _TABLES[name]
        missing = sorted(set(LOCALE_CODES) - table.covers)
        assert not missing, f"{name} ({table.where}) has nothing for {missing}. {table.fix}"


class TestNoneOfThemCarriesALanguageNobodyServes:
    """And the guard above is not vacuous.

    A coverage assertion is only worth what it costs to fail. Each table
    is asked about a language that is not served, and has to say no —
    otherwise the test above would pass on a table that accepts
    anything, which is precisely the shape of the defect this file was
    written for."""

    @pytest.mark.parametrize("name", list(_TABLES))
    def test_it_does_not_carry_the_fifth(self, name: str) -> None:
        table = _TABLES[name]
        assert FIFTH not in table.covers, (
            f"{name} ({table.where}) claims to carry {FIFTH!r}, which this platform "
            "does not serve. Either the roster moved and this test is stale, or the "
            "table accepts anything it is asked about — and a table that accepts "
            "anything cannot fail the coverage check above."
        )


class _Refusal(NamedTuple):
    probe: Callable[[], object]
    raises: type[Exception]
    #: Fragments the message must contain. A failure that says only
    #: ``KeyError: 'pl'`` sends whoever is adding the language reading
    #: source; the whole point is that it should not have to.
    mentions: tuple[str, ...]


_REFUSALS: Final[dict[str, _Refusal]] = {
    "the register, asked to translate into it": _Refusal(
        lambda: terms_in("завет", source_locale="ru", target_locale=FIFTH),  # type: ignore[arg-type]
        LanguageNotInTable,
        (FIFTH, "_TERMS"),
    ),
    "the register, asked what it already decides": _Refusal(
        lambda: known_forms(FIFTH),  # type: ignore[arg-type]
        LanguageNotInTable,
        (FIFTH, "_TERMS"),
    ),
    "the register, one column short of the roster": _Refusal(
        lambda: _verify_every_term_is_written_in_every_language(WITH_A_FIFTH),
        LanguageNotInTable,
        ("_TERMS", "LOCALE_CODES"),
    ),
    "the numeral check": _Refusal(
        lambda: numbers_lost("двенадцать", "dwanaście", source_locale="ru", target_locale=FIFTH),  # type: ignore[arg-type]
        LanguageNotInTable,
        (FIFTH, "Numeral"),
    ),
    "the numeral table, one column short of the roster": _Refusal(
        lambda: _verify_every_number_is_spelled_in_every_language(WITH_A_FIFTH),
        LanguageNotInTable,
        ("Numeral", "LOCALE_CODES"),
    ),
    "the typography pass": _Refusal(
        lambda: normalize_typography('Er sagte "Wort".', FIFTH),  # type: ignore[arg-type]
        LanguageNotInTable,
        (FIFTH, "QUOTATION_MARKS"),
    ),
    "the prompt builder": _Refusal(
        lambda: build_system_prompt(source_locale="ru", target_locale=FIFTH),  # type: ignore[arg-type]
        KeyError,
        (FIFTH,),
    ),
}


class TestNothingAnswersAboutALanguageItCannotRead:
    """The three that used to answer, and what they answer now.

    Each of these returned a value indistinguishable from success: an
    empty list of missing terms, an empty list of lost numbers, the text
    unchanged. The prompt builder is here as the shape to copy — it has
    always raised, because ``LOCALE_DISPLAY_NAMES[locale]`` is a
    subscript and not a ``.get``, and nobody has ever had to wonder
    whether a language was configured."""

    @pytest.mark.parametrize("what", list(_REFUSALS))
    def test_it_refuses(self, what: str) -> None:
        refusal = _REFUSALS[what]
        with pytest.raises(refusal.raises) as raised:
            refusal.probe()
        message = str(raised.value)
        for fragment in refusal.mentions:
            assert fragment in message, f"the refusal should name {fragment!r}: {message}"

    @pytest.mark.parametrize("what", list(_REFUSALS))
    def test_the_refusal_is_a_sentence_and_not_a_code(self, what: str) -> None:
        refusal = _REFUSALS[what]
        if refusal.raises is KeyError:
            # A bare KeyError is the one exception, and it is the
            # pre-existing behaviour of a subscript into
            # ``LOCALE_DISPLAY_NAMES``. Loud enough: the request dies in
            # the caller's face. Left alone because rewriting a builtin
            # lookup to say more is a bigger change than the silence it
            # would fix.
            return
        with pytest.raises(refusal.raises) as raised:
            refusal.probe()
        assert len(str(raised.value).split()) > 20, (
            "the message has to say what a person must do, not merely that something is missing"
        )


class TestTheLanguagesServedTodayAreAllStillAnswered:
    """The other direction, and the one that would hurt to get wrong.

    Making these tables refuse an unknown language is only safe if every
    language the platform actually serves is known to all of them. This
    is that assertion, made through the front door rather than by
    reading the tables."""

    @pytest.mark.parametrize("locale", list(LOCALE_CODES))
    def test_the_register_and_the_numerals_and_the_pass_all_answer(self, locale: str) -> None:
        other = next(code for code in LOCALE_CODES if code != locale)
        assert known_forms(locale)  # type: ignore[arg-type]
        assert terms_in("церковь", source_locale="ru", target_locale=locale) or locale == "ru"  # type: ignore[arg-type]
        numbers_lost("двенадцать", "x", source_locale="ru", target_locale=locale)  # type: ignore[arg-type]
        opening, closing = QUOTATION_MARKS[locale]  # type: ignore[index]
        assert f"{opening}Wort{closing}" in normalize_typography('Er sagte "Wort".', locale)  # type: ignore[arg-type]
        assert build_system_prompt(source_locale=locale, target_locale=other)  # type: ignore[arg-type]
