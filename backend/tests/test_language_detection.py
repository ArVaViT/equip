# ruff: noqa: RUF001, RUF002, RUF003
# These tests EXIST to exercise Cyrillic-vs-Latin detection, so the
# mixed-script literals (and any docstring describing them) are the
# whole point.
"""TDD spec for the source-language detector.

The bug this fixes: when a teacher with an English UI authors a
Russian course, ``courses.source_locale`` was being set to ``"en"``
based on the teacher's profile preference, and the translation
pipeline then refused to translate ``"en" → "ru"`` for Russian
students.

This file defines the contract of the detector that must replace the
``source_locale = teacher.preferred_locale`` shortcut. Tests are
intentionally written BEFORE the implementation exists — they fail
on import until ``app.services.language_detection`` lands.
"""

from __future__ import annotations

import pytest

# The module doesn't exist yet — import will fail and every test in
# this file errors. That's the red phase of the TDD cycle.
from app.schemas.locale import LOCALE_CODES
from app.services import language_detection as lang_mod
from app.services.language_detection import detect_locale


@pytest.fixture(autouse=True)
def _two_locales(monkeypatch: pytest.MonkeyPatch):
    """Most of this file describes the detector on the set it shipped
    with: ``ru`` + ``en``, one language per script, where the script
    alone settles it.

    That is a property of the SET, not of the detector, and pinning it
    to the live ``LOCALE_CODES`` made these tests quietly change meaning
    the day German and Ukrainian were switched on. The classes below
    that describe four locales override this fixture.
    """
    monkeypatch.setattr(lang_mod, "LOCALE_CODES", ("ru", "en"))


class TestDetectLocaleHappyPath:
    def test_pure_russian_returns_ru(self):
        assert detect_locale("Книга Бытия") == "ru"

    def test_pure_english_returns_en(self):
        assert detect_locale("Book of Genesis") == "en"

    def test_russian_sentence_returns_ru(self):
        assert detect_locale("Изучаем первую книгу Библии вместе") == "ru"

    def test_english_sentence_returns_en(self):
        assert detect_locale("Studying the first book of the Bible together") == "en"


class TestDetectLocaleBugCase:
    """The exact bug Vadym reported: a single Cyrillic word that
    transliterates an English word (``Тайтл`` = "title") MUST still
    be detected as Russian — it's Cyrillic characters, not Latin."""

    def test_short_cyrillic_transliteration_returns_ru(self):
        # This is literally the production row that triggered the
        # report. ``Тайтл`` is what a Russian-speaking teacher writes
        # when they mean "title" without bothering to translate it.
        assert detect_locale("Тайтл") == "ru"

    def test_short_cyrillic_with_description_returns_ru(self):
        # The course's real production state had this title +
        # description combo. Detector should return ``ru`` for either.
        assert detect_locale("Тайтл Кто-то что-то сказал") == "ru"


class TestDetectLocaleMixedContent:
    """Bible-school courses mix Cyrillic body with English technical
    terms (``chapter``, ``Old Testament``) and Hebrew/Greek
    transliterations. Detection picks the majority script."""

    def test_majority_cyrillic_with_english_term_returns_ru(self):
        # Russian commentary that cites an English chapter reference.
        assert detect_locale("Книга Бытия chapter 1") == "ru"

    def test_majority_latin_with_russian_quote_returns_en(self):
        # English course that quotes a Russian source.
        assert detect_locale("Genesis study — alongside the Russian Синодальный text") == "en"

    def test_with_numbers_and_punctuation_uses_letters_only(self):
        # Numbers + punctuation should not influence the decision; only
        # alphabetic characters count.
        assert detect_locale("Глава 1, стих 2 — 2026 год") == "ru"
        assert detect_locale("Chapter 1, verse 2 — year 2026") == "en"


class TestDetectLocaleEmptyAndDegenerate:
    """When the input has no signal, the detector returns ``None`` and
    the caller falls back to the teacher's UI locale. The detector
    does NOT silently default — that's the entire bug being fixed."""

    def test_none_returns_none(self):
        assert detect_locale(None) is None

    def test_empty_string_returns_none(self):
        assert detect_locale("") is None

    def test_pure_whitespace_returns_none(self):
        assert detect_locale("   \n\t   ") is None

    def test_only_digits_returns_none(self):
        assert detect_locale("123 456 789") is None

    def test_only_punctuation_returns_none(self):
        assert detect_locale("!!! ??? --- ...") is None


class TestDetectLocaleThreshold:
    """Very short inputs ("Hi", "Да") are ambiguous and risky to act on;
    the detector requires at least 3 alphabetic characters of one
    script before committing to a locale."""

    def test_two_latin_letters_returns_none(self):
        # "Hi" is below the threshold — could be initials, an
        # abbreviation, or a typo. Don't decide.
        assert detect_locale("Hi") is None

    def test_two_cyrillic_letters_returns_none(self):
        # "Да" (yes) is below threshold.
        assert detect_locale("Да!") is None

    def test_three_latin_letters_meets_threshold(self):
        assert detect_locale("Yes") == "en"

    def test_three_cyrillic_letters_meets_threshold(self):
        assert detect_locale("Хай") == "ru"


class TestDetectLocaleHtml:
    """The course body is sanitised HTML; the detector should pick up
    the text content, not the tag soup. Tag characters are Latin
    letters so a Russian-content HTML block could otherwise tip Latin."""

    def test_html_tags_do_not_skew_russian_detection(self):
        # 10+ Cyrillic chars inside <p> tags. The tags add ~4 Latin
        # chars but the body wins.
        html = "<p>Введение в книгу Бытия</p>"
        assert detect_locale(html) == "ru"

    def test_html_tags_do_not_skew_english_detection(self):
        html = "<p>Introduction to the book of Genesis</p>"
        assert detect_locale(html) == "en"


class TestDetectLocaleEdgeCases:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Привет мир", "ru"),
            ("Hello world", "en"),
            ("📖 Книга", "ru"),
            ("📖 Book", "en"),
            ("Изучение Bible (НЗ)", "ru"),  # majority cyrillic
            ("Bible study (НЗ)", "en"),  # majority latin
        ],
    )
    def test_assorted_realistic_inputs(self, text: str, expected: str):
        assert detect_locale(text) == expected


@pytest.fixture
def four_locales(monkeypatch: pytest.MonkeyPatch):
    """Run the detector as if ``de`` and ``uk`` were already served.

    ``LOCALE_CODES`` is read at call time precisely so this is
    possible: the tests below are the contract the detector must
    already satisfy on the day those two locales are switched on, not
    a description of today's two-locale behaviour.
    """
    monkeypatch.setattr(lang_mod, "LOCALE_CODES", ("ru", "en", "de", "uk"))


class TestDetectLocaleUkrainianVsRussian:
    """Both are Cyrillic. Counting scripts made Ukrainian answer ``ru``,
    which told ``pick_overlay_value`` to serve raw Ukrainian source to
    a Ukrainian student while the Russian translation went unread."""

    def test_ukrainian_sentence_returns_uk(self, four_locales):
        assert detect_locale("Вивчаємо першу книгу Біблії разом") == "uk"

    def test_russian_sentence_still_returns_ru(self, four_locales):
        assert detect_locale("Изучаем первую книгу Библии вместе") == "ru"

    def test_ukrainian_exclusive_letters_decide(self, four_locales):
        # "ї" and "є" do not occur in Russian orthography.
        assert detect_locale("Історія Церкви") == "uk"

    def test_russian_exclusive_letters_decide(self, four_locales):
        # "ы" and "ъ" do not occur in Ukrainian orthography.
        assert detect_locale("Объясняем язык веры") == "ru"

    def test_ambiguous_cyrillic_returns_none(self, four_locales):
        # "Тайтл" is spelled identically in both languages. With only
        # one of them supported the script settles it; with both, the
        # honest answer is "no signal" and the caller's declared
        # locale decides. Guessing here is how a student gets served
        # the wrong language.
        assert detect_locale("Тайтл") is None


class TestDetectLocaleGermanVsEnglish:
    """Both are Latin. Counting scripts made German answer ``en``."""

    def test_german_sentence_returns_de(self, four_locales):
        assert detect_locale("Wir lesen das erste Buch der Bibel zusammen") == "de"

    def test_english_sentence_still_returns_en(self, four_locales):
        assert detect_locale("Studying the first book of the Bible together") == "en"

    def test_umlaut_decides(self, four_locales):
        assert detect_locale("Einführung für Schüler") == "de"

    def test_german_without_umlauts_returns_de(self, four_locales):
        # No umlaut in sight; the articles carry it.
        assert detect_locale("Das Evangelium und die Apostel") == "de"

    def test_proper_nouns_alone_return_none(self, four_locales):
        # "Genesis Exodus" is the same string in both languages.
        assert detect_locale("Genesis Exodus") is None


class TestDetectLocaleRespectsSupportedSet:
    """The detector never names a language the platform does not
    serve, and never keeps a stale profile map silently."""

    def test_never_returns_an_unsupported_locale(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(lang_mod, "LOCALE_CODES", ("ru",))
        # Latin script, but ``en`` is not served in this configuration.
        assert detect_locale("Book of Genesis") is None
        assert detect_locale("Книга Бытия") == "ru"

    def test_locale_without_a_profile_stops_detection(self, monkeypatch: pytest.MonkeyPatch):
        # A language added to LOCALE_CODES but not to _PROFILES must
        # not be quietly detected as whichever locale shares its
        # script — French text would come back "en" and be served raw.
        monkeypatch.setattr(lang_mod, "LOCALE_CODES", ("ru", "en", "fr"))
        assert detect_locale("Book of Genesis") is None

    def test_every_supported_locale_has_a_profile(self):
        # The live configuration must never be in the state the test
        # above simulates.
        missing = [code for code in LOCALE_CODES if code not in lang_mod._PROFILES]
        assert not missing, f"add a detection profile for {missing} in language_detection.py"

    def test_profiles_agree_with_display_names(self):
        # Both maps are keyed by locale; drift between them means one
        # of the five "adding a language" steps was half-done.
        assert set(lang_mod._PROFILES) >= set(LOCALE_CODES)


class TestDetectLocaleMarkup:
    """Tag names are Latin letters. Stripping markup keeps a short
    Cyrillic paragraph inside nested HTML from tipping Latin."""

    def test_nested_markup_does_not_tip_the_count(self):
        html = "<div><p><strong>Бог</strong></p></div>"
        assert detect_locale(html) == "ru"

    def test_markup_only_input_returns_none(self):
        assert detect_locale("<div><br/></div>") is None


class TestAWordTwoLanguagesShare:
    @pytest.fixture(autouse=True)
    def _all_four(self, monkeypatch: pytest.MonkeyPatch):
        """This class is about German against English, so it needs the
        set the platform actually serves — the file's default of ru+en
        would score German prose against Russian and English only."""
        monkeypatch.setattr(lang_mod, "LOCALE_CODES", ("ru", "en", "de", "uk"))

    """The rule that stops a common word from deciding a language.

    "was" is German's most ordinary interrogative and English's past
    tense of "to be". It sat in the English list and not the German
    one, so *Was wurde laut 1. Mose 2,1 vollendet?* — six German words
    — scored 1:0 for English. The row was written, validated as the
    wrong language, and parked for review, in production.

    Adding "was" to German alone would have swapped the error. Dropping
    every word the profiles share is the rule that holds, and it scales
    to a fifth language that overlaps a fourth.
    """

    def test_the_sentence_that_started_it(self):
        assert detect_locale("Was wurde laut 1. Mose 2,1 vollendet?") == "de"

    def test_english_still_reads_as_english(self):
        assert detect_locale("What was completed according to Genesis 2:1?") == "en"

    def test_the_shared_words_are_excluded_from_scoring(self):
        from app.services.language_detection import _AMBIGUOUS_WORDS

        assert "was" in _AMBIGUOUS_WORDS
        assert "in" in _AMBIGUOUS_WORDS

    def test_a_word_only_one_language_has_still_counts(self):
        from app.services.language_detection import _AMBIGUOUS_WORDS

        assert "wurde" not in _AMBIGUOUS_WORDS
        assert "the" not in _AMBIGUOUS_WORDS

    def test_short_german_questions_read_as_german(self):
        for text in (
            "Wer schrieb den Brief an die Römer?",
            "Was sagt der Vers über den Glauben?",
            "Wem wurde diese Verheißung gegeben?",
        ):
            assert detect_locale(text) == "de", text

    def test_the_detector_still_refuses_to_guess_on_nothing(self):
        # The whole design: no signal means no answer, not a coin flip.
        assert detect_locale("Amen") is None
        assert detect_locale("1:1") is None


class TestTheEvidenceWasMeasuredNotImagined:
    """Every rule here was checked against every string in production.

    The absence rule — "a Ukrainian text without і/ї/є does not occur" —
    was set at 20 letters on reasoning alone, and the reasoning was
    wrong: 10% of Ukrainian strings between 20 and 39 letters have no
    hallmark at all. It read them as Russian, and the validator then
    reported correct translations as the wrong language.
    """

    @pytest.fixture(autouse=True)
    def _all_four(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(lang_mod, "LOCALE_CODES", ("ru", "en", "de", "uk"))

    @pytest.mark.parametrize(
        "text",
        [
            "Модуль 3. Друга половина: чотири групи",
            "Урок 10. Листи Павла: порядок за довжиною, а не за часом",
            "Уздовж узбережжя Середземного моря",
            "За авторами, а не за адресатами",
        ],
    )
    def test_ukrainian_without_a_hallmark_letter_is_not_called_russian(self, text: str):
        # Production strings, all four of them. None contains і, ї or є.
        assert lang_mod.detect_locale(text) != "ru"

    @pytest.mark.parametrize(
        "text",
        [
            "Изучаем первую книгу Библии вместе",
            "Кто написал послание к римлянам?",
            "Согласно Матфею 4:1, кто повёл Иисуса в пустыню?",
        ],
    )
    def test_russian_is_still_russian(self, text: str):
        assert lang_mod.detect_locale(text) == "ru"

    @pytest.mark.parametrize(
        "text",
        ["Слово Божие", "Вся карта на одной странице", "Сколько тебе лет?", "Через три роки", "Три"],
    )
    def test_a_few_words_are_not_enough_to_name_a_language(self, text: str):
        # The first three are Russian, the fourth Ukrainian, and none of
        # them carries evidence either way. Refusing is the answer; a
        # wrong guess here is what parks a correct translation for
        # review.
        assert lang_mod.detect_locale(text) is None

    def test_a_word_both_languages_use_decides_nothing(self):
        from app.services.language_detection import _AMBIGUOUS_WORDS

        for word in ("а", "за", "три", "тебе", "не", "на"):
            assert word in _AMBIGUOUS_WORDS, word


class TestAWordThatMeansSomethingOnBothSides:
    """The overlap rule can only cancel a word both lists carry, and the
    lists are written by hand. German declares "man", "war", "die",
    "am", "den", "hat", "nun" because they are German function words;
    nobody put them in the English list because in English they are
    content words. So the rule never saw them.

    "Lesson 7. Man and war" scored 4:0 for German. The validator then
    reported a correct English translation as the wrong language — and
    ``orchestrator`` treats ``needs_review`` at an unchanged source hash
    as terminal, so that translation was parked for good.
    """

    @pytest.fixture(autouse=True)
    def _all_four(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(lang_mod, "LOCALE_CODES", ("ru", "en", "de", "uk"))

    @pytest.mark.parametrize(
        "text",
        [
            "Lesson 7. Man and war",
            "Man of war, man of peace",
            "The die is cast and the war is over",
        ],
    )
    def test_english_prose_built_from_homographs_is_not_german(self, text: str):
        assert lang_mod.detect_locale(text) != "de"

    @pytest.mark.parametrize(
        "text",
        [
            "Was wurde laut 1. Mose 2,1 vollendet?",
            "Wer schrieb den Brief an die Römer?",
            "Der Brief nennt seinen Verfasser im ersten Vers.",
        ],
    )
    def test_german_prose_is_still_german(self, text: str):
        assert lang_mod.detect_locale(text) == "de"

    def test_the_list_holds_only_words_that_live_in_both_languages(self):
        from app.services.language_detection import _LATIN_HOMOGRAPHS

        # The first version swept in "the", "to", "is", "can" — English
        # words with no German life at all — and threw away real
        # evidence to fix a different problem.
        for english_only in ("the", "to", "is", "can", "and", "with"):
            assert english_only not in _LATIN_HOMOGRAPHS, english_only
        for both in ("man", "war", "die", "was", "in"):
            assert both in _LATIN_HOMOGRAPHS, both
