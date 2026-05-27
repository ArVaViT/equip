# ruff: noqa: RUF001
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
from app.services.language_detection import detect_locale


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
