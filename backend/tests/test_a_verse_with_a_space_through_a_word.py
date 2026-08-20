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

What is done about it: the split is undone where undoing it is provable
and the verse is refused where it is not. Refusing everything was the
first answer here and it was the wrong default — a refused verse falls
back to the author's words, which for these rows are English, so ten
Ukrainian explanations would have read ``Псалом 8:1 (KJV) говорить: 'O
LORD our Lord…'``. A typographic artifact the reader can read past is a
smaller failure than a lesson that stops speaking their language.

Three things this file exists to hold still.

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

**A mend is provable or it does not happen.** The repair asks for one
thing the detection does not — a capital, then one space, then a
lowercase letter of the same script — because a wrong refusal costs one
verse and says so, while a wrong repair changes Scripture and says
nothing. ``TestTheMendOnlyRunsWhereTheReadingIsClosed`` is that
condition, case by case.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from app.services.bible import api_source
from app.services.bible import substitution as sub
from app.services.bible.references import BibleRef
from app.services.bible.substitution import post_substitute, pre_substitute
from app.services.bible.well_formed import malformed_fragment, mend

PSALM_23_1_AS_IT_CAME_BACK = "Псальма Давидова. Г осподь пастирь мій, не мати му недостатку."
PSALM_23_1_AS_IT_SHOULD_READ = "Псальма Давидова. Господь пастирь мій, не мати му недостатку."


#: Every stranded initial found by reading the whole live catalogue,
#: with the word each one belongs to. Psalm 121:1 is absent on purpose —
#: see ``TestOnePsalmIsStillMissedAndThatIsDeliberate``.
BROKEN_IN_PRODUCTION = [
    ("8:1", "Проводиреві хора: при Гиттейських інструментах. Псальма Давидова. Г осподи, Боже наш!", "Господи"),
    ("19:1", "Проводиреві хора: Псальма Давидова. Н ебеса являють славу Божу.", "Небеса"),
    ("22:1", 'Проводиреві хора: Після "Досьвітна ланя"; псальма Давидова. Б оже мій, Боже!', "Боже"),
    ("23:1", PSALM_23_1_AS_IT_CAME_BACK, "Господь"),
    ("51:1", "Давидова псальма, як прийшов пророк Натан. П омилуй мене, Боже, по милостї твоїй.", "Помилуй"),
    ("91:1", "Х то під покровом Всевишнього, той буде в тїнї Всемогучого.", "Хто"),
    ("103:1", "Псальма Давидова. Б лагослови, душе моя, Господа.", "Благослови"),
    ("110:1", "Псальма Давидова. С казав Господь моєму Господеві: Сядь праворуч коло мене.", "Сказав"),
    ("139:1", "Проводиреві хора; псальма Давидова. Г осподи! Ти розглянув мене, і пізнав.", "Господи"),
]


@pytest.mark.parametrize(("psalm", "text", "word"), BROKEN_IN_PRODUCTION)
class TestEveryBrokenPsalmInProductionIsMended:
    """The nine found by reading the whole catalogue, verbatim."""

    def test_the_stranded_initial_is_found(self, psalm: str, text: str, word: str) -> None:
        assert malformed_fragment(text, "uk") is not None, f"Psalm {psalm} would still reach a reader"

    def test_and_mended_rather_than_withheld(self, psalm: str, text: str, word: str) -> None:
        mended = mend(text, "uk")

        assert word in mended, f"Psalm {psalm} would fall back to the author's English"
        assert malformed_fragment(mended, "uk") is None, f"Psalm {psalm} is still not a verse"

    def test_and_nothing_but_a_space_was_taken_out(self, psalm: str, text: str, word: str) -> None:
        # The mend removes a space. It does not choose a letter, a form
        # or a spelling — that would be editing the edition.
        mended = mend(text, "uk")

        assert mended.replace(" ", "") == text.replace(" ", "")
        assert len(mended) == len(text) - 1


class TestASoundPsalmIsLeftAlone:
    def test_the_same_verse_spelled_properly_is_not_flagged(self) -> None:
        assert malformed_fragment(PSALM_23_1_AS_IT_SHOULD_READ, "uk") is None

    def test_nor_touched(self) -> None:
        assert mend(PSALM_23_1_AS_IT_SHOULD_READ, "uk") == PSALM_23_1_AS_IT_SHOULD_READ


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

    def test_and_is_therefore_left_exactly_as_it_came(self) -> None:
        # Unseen means untouched. The mend only ever runs where the
        # detection fires, so the limit is one limit and not two.
        psalm = "Посходня пісня. О чі мої підношу на гори."

        assert mend(psalm, "uk") == psalm

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


class TestTheMendOnlyRunsWhereTheReadingIsClosed:
    """A capital, one space, a lowercase letter of the same script. That
    shape has exactly one well-formed reading; everything else is
    ambiguous and gets refused rather than guessed."""

    def test_a_capital_glued_to_a_lowercase_remainder_is_closed(self) -> None:
        assert mend("Псальма Давидова. Г осподь пастирь мій.", "uk") == "Псальма Давидова. Господь пастирь мій."

    def test_a_lowercase_stray_is_not(self) -> None:
        # Which side does it belong to? A lowercase letter could be the
        # tail of the word before it as easily as the head of the word
        # after. Refused, not guessed.
        ambiguous = "Псальма давидова. г осподь пастирь мій."

        assert malformed_fragment(ambiguous, "uk") is not None
        assert mend(ambiguous, "uk") == ambiguous

    def test_a_capital_before_another_capital_is_not(self) -> None:
        # Joining would put a capital inside a word, which this
        # orthography does not write.
        ambiguous = "Псальма Давидова. Г Осподь пастирь мій."

        assert mend(ambiguous, "uk") == ambiguous

    def test_a_letter_with_punctuation_after_it_is_not(self) -> None:
        ambiguous = "Псальма Давидова. Г. осподь пастирь мій."

        assert mend(ambiguous, "uk") == ambiguous

    def test_a_letter_from_another_script_is_not(self) -> None:
        ambiguous = "Псальма Давидова. G осподь пастирь мій."

        assert mend(ambiguous, "uk") == ambiguous

    def test_two_spaces_are_not_one_word_split(self) -> None:
        ambiguous = "Псальма Давидова. Г  осподь пастирь мій."

        assert mend(ambiguous, "uk") == ambiguous


class TestTheMendIsSafeToRunTwiceAndEverywhere:
    """A verse re-made next month has to land on the same bytes as the
    one made today, or every row would look edited on every sweep."""

    def test_mending_a_mended_verse_changes_nothing(self) -> None:
        once = mend(PSALM_23_1_AS_IT_CAME_BACK, "uk")

        assert mend(once, "uk") == once

    def test_the_same_verse_mends_to_the_same_bytes(self) -> None:
        assert mend(PSALM_23_1_AS_IT_CAME_BACK, "uk") == mend(PSALM_23_1_AS_IT_CAME_BACK, "uk")

    def test_it_mends_to_what_the_edition_prints(self) -> None:
        assert mend(PSALM_23_1_AS_IT_CAME_BACK, "uk") == PSALM_23_1_AS_IT_SHOULD_READ

    def test_every_stranded_initial_in_one_verse_is_mended(self) -> None:
        both = "Псальма Давидова. Г осподь пастирь мій. Н ебеса являють славу."

        assert mend(both, "uk") == "Псальма Давидова. Господь пастирь мій. Небеса являють славу."

    @pytest.mark.parametrize(
        ("locale", "verse"),
        [
            ("ru", "И глаз не может сказать руке: «Ты мне не нужна»."),
            ("uk", "І рече Господь Самуїлові: Чи довго ще журити мешся по Саулові?"),
            ("uk", "Сього слухайте у всьому, що глаголати ме вам."),
            ("uk", "Коли б усе тїло було око, де ж був би слух?"),
            ("en", "O LORD, our Lord, how majestic is Your name in all the earth!"),
            ("en", "This verse affirms God's love for the world."),
            ("de", "Denn also hat Gott die Welt geliebt, dass er seinen eingeborenen Sohn gab."),
            ("ru", "поставил ее на равнине Дура́, что в провинции Вавилон."),
        ],
    )
    def test_sound_scripture_comes_through_byte_for_byte(self, locale: str, verse: str) -> None:
        # Measured over the same 1,081 live verses the detection was
        # measured on: the mend touches none of them.
        assert mend(verse, locale) == verse

    def test_a_stress_mark_survives_a_mend_in_the_same_verse(self) -> None:
        # The analysis stands a filler in for the combining acute so
        # offsets keep pointing at the right character; the acute itself
        # belongs to the edition and must come out untouched.
        broken = "На равнине Дура́. Г осподь пастирь мій."

        assert mend(broken, "uk") == "На равнине Дура́. Господь пастирь мій."


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


class TestAMalformedVerseNeverLeavesTheFetcherUnmended:
    UNMENDABLE = "Посходня пісня. О чі мої підношу на гори."
    LOWERCASE_STRAY = "псальма давидова. г осподь пастирь мій."

    def test_a_200_that_is_not_a_verse_is_mended_before_anyone_sees_it(self, monkeypatch) -> None:
        _answer_with(monkeypatch, _Response(200, PSALM_23_1_AS_IT_CAME_BACK))

        assert api_source.fetch_verse(PSALM_23, "uk") == PSALM_23_1_AS_IT_SHOULD_READ

    def test_a_sound_body_comes_back_exactly_as_sent(self, monkeypatch) -> None:
        _answer_with(monkeypatch, _Response(200, PSALM_23_1_AS_IT_SHOULD_READ))

        assert api_source.fetch_verse(PSALM_23, "uk") == PSALM_23_1_AS_IT_SHOULD_READ

    def test_what_cannot_be_mended_is_refused(self, monkeypatch) -> None:
        _answer_with(monkeypatch, _Response(200, self.LOWERCASE_STRAY))

        assert api_source.fetch_verse(PSALM_23, "uk") is None

    def test_a_verse_the_rule_cannot_see_is_served_untouched(self, monkeypatch) -> None:
        # Psalm 121:1. Not seen, so not mended and not refused — the
        # single limit, honestly kept, rather than a second one.
        _answer_with(monkeypatch, _Response(200, self.UNMENDABLE))

        assert api_source.fetch_verse(PSALM_23, "uk") == self.UNMENDABLE

    def test_half_a_mend_is_not_scripture(self, monkeypatch) -> None:
        # One initial can be joined, one cannot. Serving the first and
        # keeping the second would read as sound and would not be.
        _answer_with(monkeypatch, _Response(200, "Псальма Давидова. Г осподь пастирь мій. г осподь пастирь мій."))

        assert api_source.fetch_verse(PSALM_23, "uk") is None

    def test_the_mend_is_asked_for_once(self, monkeypatch) -> None:
        # The cache holds the mended text, so a course quoting this psalm
        # in a dozen lessons costs one call and one mend.
        calls = _answer_with(monkeypatch, _Response(200, PSALM_23_1_AS_IT_CAME_BACK))

        assert api_source.fetch_verse(PSALM_23, "uk") == PSALM_23_1_AS_IT_SHOULD_READ
        assert api_source.fetch_verse(PSALM_23, "uk") == PSALM_23_1_AS_IT_SHOULD_READ
        assert len(calls) == 1

    def test_a_refusal_is_remembered_too(self, monkeypatch) -> None:
        # The edition will say the same thing next time. Unlike a 429,
        # this is an answer.
        calls = _answer_with(monkeypatch, _Response(200, self.LOWERCASE_STRAY))

        assert api_source.fetch_verse(PSALM_23, "uk") is None
        assert api_source.fetch_verse(PSALM_23, "uk") is None
        assert len(calls) == 1

    @pytest.mark.parametrize(
        ("body", "outcome"),
        [
            (PSALM_23_1_AS_IT_CAME_BACK, "outcome=mended"),
            (LOWERCASE_STRAY, "outcome=refused"),
        ],
    )
    def test_every_defect_is_counted_either_way(self, monkeypatch, caplog, body: str, outcome: str) -> None:
        # One log code for the rate, one field for which way it went. A
        # verse mended in silence would hide the publisher's defect just
        # as thoroughly as a verse refused in silence.
        _answer_with(monkeypatch, _Response(200, body))

        with caplog.at_level(logging.WARNING, logger="app.services.bible.api_source"):
            api_source.fetch_verse(PSALM_23, "uk")

        messages = [record.getMessage() for record in caplog.records]
        assert any("verse_malformed" in message and outcome in message for message in messages), messages


class TestWhatTheReaderActuallyGets:
    """Both outcomes end on a page, so both are asserted on a page.

    The mended verse is the point of the change: a Ukrainian reader gets
    Ukrainian Scripture instead of an English fallback. And the one thing
    a refusal must never do is leave a hole — generation 3 of the pipeline
    did exactly that, the placeholder was translated, the marker matched
    nothing on the way back, and the reference stood over nothing.
    """

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

    def test_a_mended_verse_reaches_the_page_in_ukrainian(self, monkeypatch) -> None:
        # What the ten rows in production get instead of an English
        # verse inside Ukrainian prose.
        def fake_fetch(ref, locale):
            if locale == "en":
                return "The LORD is my shepherd; I shall not want."
            return mend(PSALM_23_1_AS_IT_CAME_BACK, "uk")

        monkeypatch.setattr(sub, "fetch_verse", fake_fetch)

        markered, subs = pre_substitute(self._author_wrote(), "en")
        restored = post_substitute(markered, subs, "uk")

        assert "Господь пастирь мій" in restored
        assert "Г осподь" not in restored
        assert "The LORD is my shepherd" not in restored, "the reader was handed the source language"
        assert "EQV" not in restored

    def test_and_no_warning_is_raised_about_a_verse_that_arrived(self, monkeypatch, caplog) -> None:
        monkeypatch.setattr(sub, "fetch_verse", lambda ref, locale: mend(PSALM_23_1_AS_IT_CAME_BACK, "uk"))

        markered, subs = pre_substitute(self._author_wrote(), "en")
        with caplog.at_level(logging.WARNING, logger="app.services.bible.substitution"):
            post_substitute(markered, subs, "uk")

        assert not [record for record in caplog.records if "verse_fallback_to_source" in record.getMessage()]
