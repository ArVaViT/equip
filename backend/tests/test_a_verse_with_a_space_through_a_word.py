# ruff: noqa: RUF001, RUF002
# Cyrillic letters standing next to Latin ones is the subject of this file,
# not an accident of the keyboard.
"""``Г осподь`` is not archaic. It is broken.

Read out of production on 2026-08-20, ``daily_challenge_option``,
Ukrainian, ``status='ok'``::

    Псалом 23:1 ('Псальма Давидова. Г осподь пастирь мій, …')

Ten more rows carry the same defect and every one of them is a Psalm.
Куліш 1905 sets a large initial capital on the first word of a psalm's
body, and the digitisation behind the API turned that initial into a
separate letter — ``Г осподи`` (8:1), ``Н ебеса`` (19:1), ``Б оже``
(22:1), ``П омилуй`` (51:1), ``Х то`` (91:1), ``Б лагослови`` (103:1),
``С казав`` (110:1), ``Г осподи`` (139:1). Nothing looked at the text
the publisher sent, so it went onto the page as Scripture.

The edition is not the problem and is not up for discussion: it is the
only complete Ukrainian Bible the API offers and the owner chose to keep
it, pre-1928 orthography and all (``translation/version.py``,
generation 2). ``дїло`` is how it spells. ``Г осподь`` is not.

Two things this file exists to hold still.

**The rule must not grow into a spell checker.** The wider rule everyone
writes first — a single letter opening a sentence, followed by a
lowercase word — was measured against 1,081 verses fetched live from all
four editions on 2026-08-20 and scored 314 hits, every one of them real
Scripture. ``TestRealScriptureIsNotRefused`` keeps samples of exactly
those.

**Archaic spelling is not a defect.** This edition sets the analytic
future as two words — ``глаголати ме вам``, ``слухати ме слова``, ``не
мати му недостатку`` — consistently, across the whole Bible. That is
1905 orthography, not a space that fell into a word, and a checker that
"corrected" it would be overruling the edition.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from app.services.bible import api_source
from app.services.bible import substitution as sub
from app.services.bible.references import BibleRef
from app.services.bible.substitution import post_substitute, pre_substitute
from app.services.bible.well_formed import malformed_fragment

PSALM_23_1_AS_IT_CAME_BACK = "Псальма Давидова. Г осподь пастирь мій, не мати му недостатку."
PSALM_23_1_AS_IT_SHOULD_READ = "Псальма Давидова. Господь пастирь мій, не мати му недостатку."


class TestEveryBrokenPsalmInProductionIsRefused:
    """The nine found by reading the whole catalogue, verbatim."""

    @pytest.mark.parametrize(
        ("psalm", "text"),
        [
            ("8:1", "Проводиреві хора: при Гиттейських інструментах. Псальма Давидова. Г осподи, Боже наш!"),
            ("19:1", "Проводиреві хора: Псальма Давидова. Н ебеса являють славу Божу."),
            ("22:1", 'Проводиреві хора: Після "Досьвітна ланя"; псальма Давидова. Б оже мій, Боже!'),
            ("23:1", PSALM_23_1_AS_IT_CAME_BACK),
            ("51:1", "Давидова псальма, як прийшов пророк Натан. П омилуй мене, Боже, по милостї твоїй."),
            ("91:1", "Х то під покровом Всевишнього, той буде в тїнї Всемогучого."),
            ("103:1", "Псальма Давидова. Б лагослови, душе моя, Господа."),
            ("110:1", "Псальма Давидова. С казав Господь моєму Господеві: Сядь праворуч коло мене."),
            ("139:1", "Проводиреві хора; псальма Давидова. Г осподи! Ти розглянув мене, і пізнав."),
        ],
    )
    def test_the_stranded_initial_is_found(self, psalm: str, text: str) -> None:
        assert malformed_fragment(text, "uk") is not None, f"Psalm {psalm} would still reach a reader"

    def test_and_the_same_psalm_spelled_properly_is_not(self) -> None:
        assert malformed_fragment(PSALM_23_1_AS_IT_SHOULD_READ, "uk") is None


class TestOnePsalmIsStillMissedAndThatIsDeliberate:
    """Psalm 121:1 comes back as ``О чі мої підношу на гори``.

    ``о`` is a real Ukrainian word — this same edition writes ``на
    молитву о девятій годинї`` — so a stranded ``О`` cannot be told
    apart from the vocative in ``о Боже`` or ``о нерозумні Галати``
    without a dictionary this project does not have and should not
    guess at. Refusing it would mean refusing those.

    This test is here so the gap is a decision somebody made rather
    than something nobody noticed. If a later change catches it, this
    test fails and the note in the PR gets deleted on purpose.
    """

    def test_a_word_that_is_also_a_word(self) -> None:
        assert malformed_fragment("Посходня пісня. О чі мої підношу на гори.", "uk") is None

    def test_because_the_same_letter_opens_a_real_sentence(self) -> None:
        assert malformed_fragment("Петр та Йоан ійшли до церкви на молитву о девятій годинї.", "uk") is None


class TestRealScriptureIsNotRefused:
    """Samples from the four live editions, chosen from the 314 hits the
    naive rule scored. Every one of these is Scripture as printed."""

    @pytest.mark.parametrize(
        ("locale", "verse"),
        [
            # A one-letter conjunction opening a sentence is not a defect,
            # it is Russian — and Ukrainian, and English.
            ("ru", "И глаз не может сказать руке: «Ты мне не нужна»."),
            ("ru", "Я отверг его как царя над Израилем. Наполни рог маслом."),
            ("ru", "В те дни слово Господа было редким."),
            ("ru", "К тем частям тела, которые мы считаем менее почетными."),
            ("ru", "С того дня началось большое гонение на иерусалимскую церковь."),
            ("uk", "І рече Господь Самуїлові: Чи довго ще журити мешся по Саулові?"),
            ("uk", "А приймете силу, як зійде сьвятий Дух на вас."),
            ("uk", "У другому році, під такий час, як царі виходять на війну."),
            ("uk", "Я дорога й правда, й життє: нїхто не приходить до Отця."),
            ("uk", "Був чоловік у землї Уз, на імя Йов."),
            ("en", "I am sending you to Jesse of Bethlehem."),
            ("en", "O LORD, our Lord, how majestic is Your name in all the earth!"),
            ("en", "The LORD is my shepherd; I shall not want."),
            ("de", "Denn also hat Gott die Welt geliebt, dass er seinen eingeborenen Sohn gab."),
        ],
    )
    def test_it_comes_through_untouched(self, locale: str, verse: str) -> None:
        assert malformed_fragment(verse, locale) is None

    @pytest.mark.parametrize(
        ("locale", "verse"),
        [
            # The traps a first attempt at this drowns in: one-letter
            # prepositions are words in both Slavic languages.
            ("uk", "І сьвітло у темряві сьвітить, і темрява його не обняла."),
            ("uk", "З усякого дерева райського їсти мемо."),
            ("ru", "Мы возвещаем о том, что существовало от начала."),
            ("ru", "Лука один со мною."),
        ],
    )
    def test_a_one_letter_preposition_is_a_word(self, locale: str, verse: str) -> None:
        assert malformed_fragment(verse, locale) is None


class TestTheEditionsOwnSpellingIsLeftAlone:
    """1905 orthography is a cost the owner accepted, not a defect."""

    @pytest.mark.parametrize(
        "verse",
        [
            "Сього слухайте у всьому, що глаголати ме вам.",
            "Ти сам будеш над моїм домом, і слухати ме слова твого все царство моє.",
            "Кожен землянин Ізраїльський жити ме в кучках.",
            "І коли справляєте жнива на землї вашій, то не дожинати меш до краю.",
            "Що казати му їм?",
            PSALM_23_1_AS_IT_SHOULD_READ,
        ],
    )
    def test_the_analytic_future_is_two_words_in_this_edition(self, verse: str) -> None:
        assert malformed_fragment(verse, "uk") is None

    @pytest.mark.parametrize(
        "verse",
        [
            "Се дїло сьвятого Духа, і тїла нашого.",
            "Об'явлення Ісуса Христа, що дав йому Бог.",
        ],
    )
    def test_and_so_are_its_letters(self, verse: str) -> None:
        assert malformed_fragment(verse, "uk") is None


class TestALetterIsJudgedByTheLanguageItIsIn:
    """``с`` is a Russian preposition and not a Ukrainian word. One
    shared list would have to allow it everywhere, and Psalm 110:1 would
    go on reading ``С казав Господь моєму Господеві``."""

    def test_russian_keeps_its_preposition(self) -> None:
        assert malformed_fragment("Лука один с мною.", "ru") is None

    def test_ukrainian_does_not_have_one(self) -> None:
        assert malformed_fragment("Псальма Давидова. С казав Господь моєму Господеві.", "uk") is not None

    def test_an_unmeasured_locale_gets_the_benefit_of_the_doubt(self) -> None:
        # No list for Polish, so no opinion about Polish: the generous
        # reading, because a refusal costs a reader a verse.
        assert malformed_fragment("Псальма Давидова. С казав Господь.", "pl") is None


class TestAnEncliticCannotOpenASentence:
    """``б`` and ``ж`` lean backwards onto the word before them. One that
    opens a sentence is the head of the next word, not a particle."""

    def test_leaning_on_the_word_before_it_is_fine(self) -> None:
        assert malformed_fragment("Коли б усе тїло було око, де ж був би слух?", "uk") is None

    def test_opening_a_sentence_is_not(self) -> None:
        assert malformed_fragment("псальма Давидова. Б оже мій, Боже!", "uk") is not None

    def test_and_neither_is_opening_the_passage(self) -> None:
        assert malformed_fragment("Б лагослови, душе моя, Господа.", "uk") is not None


class TestNothingElseInAVerseIsMistakenForALetter:
    def test_a_stress_mark_does_not_split_a_word(self) -> None:
        # The Russian edition prints stress on a name it expects to be
        # misread. A combining acute is not a letter.
        assert malformed_fragment("поставил ее на равнине Дура́, что в провинции Вавилон.", "ru") is None

    def test_a_possessive_is_not_a_stranded_s(self) -> None:
        assert malformed_fragment("This verse affirms God's love for the world.", "en") is None

    def test_a_hyphenated_name_is_not_two_words(self) -> None:
        assert malformed_fragment("отаборились перед Пі-Гахиротом, між Микдолом і морем.", "uk") is None

    def test_a_script_with_no_list_gets_no_opinion(self) -> None:
        assert malformed_fragment("ἐν ἀρχῇ ἦν ὁ λόγος", "en") is None


# --------------------------------------------------------------------
# The check where it actually runs
# --------------------------------------------------------------------


class _Response:
    def __init__(self, status_code: int, content: str = "") -> None:
        self.status_code = status_code
        self._content = content

    def json(self) -> dict[str, str]:
        return {"content": self._content}


@pytest.fixture(autouse=True)
def _a_clean_cache_and_a_key(monkeypatch):
    api_source._cache.clear()
    monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")
    yield
    api_source._cache.clear()


def _answer_with(monkeypatch, *responses: _Response) -> list[int]:
    calls: list[int] = []

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def get(self, *_args, **_kwargs):
            calls.append(1)
            return responses[min(len(calls) - 1, len(responses) - 1)]

    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: _Client())
    return calls


PSALM_23 = BibleRef("psalms", 23, 1)


class TestAMalformedVerseNeverLeavesTheFetcher:
    def test_a_200_that_is_not_a_verse_answers_none(self, monkeypatch) -> None:
        _answer_with(monkeypatch, _Response(200, PSALM_23_1_AS_IT_CAME_BACK))

        assert api_source.fetch_verse(PSALM_23, "uk") is None

    def test_the_same_body_spelled_properly_answers_with_it(self, monkeypatch) -> None:
        _answer_with(monkeypatch, _Response(200, PSALM_23_1_AS_IT_SHOULD_READ))

        assert api_source.fetch_verse(PSALM_23, "uk") == PSALM_23_1_AS_IT_SHOULD_READ

    def test_it_is_not_asked_for_again(self, monkeypatch) -> None:
        # The edition will say the same thing next time. Unlike a 429,
        # this is an answer.
        calls = _answer_with(monkeypatch, _Response(200, PSALM_23_1_AS_IT_CAME_BACK))

        assert api_source.fetch_verse(PSALM_23, "uk") is None
        assert api_source.fetch_verse(PSALM_23, "uk") is None
        assert len(calls) == 1

    def test_the_refusal_is_countable(self, monkeypatch, caplog) -> None:
        _answer_with(monkeypatch, _Response(200, PSALM_23_1_AS_IT_CAME_BACK))

        with caplog.at_level(logging.WARNING, logger="app.services.bible.api_source"):
            api_source.fetch_verse(PSALM_23, "uk")

        assert any("verse_malformed" in record.getMessage() for record in caplog.records), (
            "a verse refused in silence is the defect this replaces, not a fix for it"
        )


class TestTheReaderKeepsTheAuthorsWordsInstead:
    """The one thing a refusal must never do is leave a hole. Generation 3
    of the pipeline did exactly that — the placeholder was translated, so
    the marker matched nothing on the way back and the reference stood
    over nothing."""

    def _author_wrote(self) -> str:
        return "<blockquote>The LORD is my shepherd; I shall not want.</blockquote> (Psalm 23:1)."

    def test_the_verse_is_not_dropped(self, monkeypatch) -> None:
        def fake_fetch(ref, locale):
            if locale == "en":
                return "The LORD is my shepherd; I shall not want."
            return None  # what the refusal looks like to this layer

        monkeypatch.setattr(sub, "fetch_verse", fake_fetch)

        markered, subs = pre_substitute(self._author_wrote(), "en")
        assert len(subs) == 1, "the author quoted the edition; this is a substitution"

        restored = post_substitute(markered, subs, "uk")

        assert "EQV" not in restored, "a sentinel reached the page"
        assert "The LORD is my shepherd" in restored, "the reader was left with a reference over a hole"
        assert "Г осподь" not in restored

    def test_and_the_gap_is_reported(self, monkeypatch, caplog) -> None:
        monkeypatch.setattr(
            sub,
            "fetch_verse",
            lambda ref, locale: None if locale == "uk" else "The LORD is my shepherd; I shall not want.",
        )

        markered, subs = pre_substitute(self._author_wrote(), "en")
        with caplog.at_level(logging.WARNING, logger="app.services.bible.substitution"):
            post_substitute(markered, subs, "uk")

        assert any("verse_fallback_to_source" in record.getMessage() for record in caplog.records)
