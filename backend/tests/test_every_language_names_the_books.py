"""A reference in the middle of German prose has to be a German reference.

``display_book_name`` returns ``None`` for a locale it has no table for,
and every caller does the same thing with ``None``: keeps the English
name. So a missing language does not fail — it renders "(Rom. 8:1)" to a
German reader and "(Rom. 8:1)" to a Ukrainian one, in the one place on
the page where the platform is quoting Scripture at them.

That is the quiet kind of gap. It survived the German and Ukrainian
rollout precisely because nothing breaks: the abbreviation is short, it
is in a parenthesis, and it looks deliberate.

These tests make the next language loud instead.
"""

from __future__ import annotations

import pytest

from app.schemas.locale import LOCALE_CODES
from app.services.bible.books import _DISPLAY_NAMES, all_canonical_slugs, display_book_name


class TestEveryLanguageIsComplete:
    @pytest.mark.parametrize("locale", LOCALE_CODES)
    def test_it_names_all_sixty_six_books(self, locale: str):
        missing = sorted(set(all_canonical_slugs()) - set(_DISPLAY_NAMES.get(locale, {})))
        assert not missing, f"{locale} would show English for {missing}"

    @pytest.mark.parametrize("locale", LOCALE_CODES)
    def test_no_abbreviation_is_blank(self, locale: str):
        blank = sorted(slug for slug, name in _DISPLAY_NAMES[locale].items() if not name.strip())
        assert not blank

    def test_it_knows_no_books_outside_the_canon(self):
        canon = set(all_canonical_slugs())
        for locale, table in _DISPLAY_NAMES.items():
            assert not set(table) - canon, f"{locale} names a book that is not in the canon"


class TestTheAbbreviationsAreTheRightLanguage:
    def test_german_uses_luther_naming(self):
        # The German edition the platform quotes from is Luther 1912,
        # and Luther numbers the Pentateuch rather than naming it.
        assert display_book_name("genesis", "de") == "1. Mose"
        assert display_book_name("deuteronomy", "de") == "5. Mose"
        assert display_book_name("romans", "de") == "Röm."
        assert display_book_name("revelation", "de") == "Offb."

    def test_ukrainian_is_not_russian(self):
        # These two are a copy-paste away from each other and are not the
        # same word. John especially: Ів. against Ин.
        assert display_book_name("john", "uk") == "Ів."
        assert display_book_name("john", "ru") == "Ин."
        assert display_book_name("acts", "uk") == "Дії"
        assert display_book_name("acts", "ru") == "Деян."

    @pytest.mark.parametrize("locale", ["ru", "uk"])
    def test_the_cyrillic_languages_are_written_in_cyrillic(self, locale: str):
        for slug, name in _DISPLAY_NAMES[locale].items():
            letters = [ch for ch in name if ch.isalpha()]
            assert letters, slug
            assert all("Ѐ" <= ch <= "ӿ" for ch in letters), f"{locale}/{slug} is not Cyrillic: {name}"

    @pytest.mark.parametrize("locale", ["en", "de"])
    def test_the_latin_languages_are_written_in_latin(self, locale: str):
        for slug, name in _DISPLAY_NAMES[locale].items():
            letters = [ch for ch in name if ch.isalpha()]
            assert letters, slug
            assert all(ch.isascii() or ch in "äöüÄÖÜß" for ch in letters), f"{locale}/{slug}: {name}"


class TestNothingFallsBackToEnglish:
    @pytest.mark.parametrize("locale", LOCALE_CODES)
    def test_every_book_resolves_in_every_language(self, locale: str):
        for slug in all_canonical_slugs():
            assert display_book_name(slug, locale) is not None

    def test_no_two_languages_share_a_table(self):
        # Individual books can legitimately coincide — Ukrainian and
        # Russian both abbreviate Romans "Рим." — but two languages
        # agreeing on all 66 means one of them was copied and never
        # translated.
        tables = {locale: tuple(sorted(_DISPLAY_NAMES[locale].items())) for locale in LOCALE_CODES}
        assert len(set(tables.values())) == len(LOCALE_CODES), "two languages share one table"

    @pytest.mark.parametrize("locale", ["de", "uk"])
    def test_the_languages_added_later_are_not_english_in_disguise(self, locale: str):
        # What the caller actually did before this table existed.
        english = _DISPLAY_NAMES["en"]
        same = [slug for slug, name in _DISPLAY_NAMES[locale].items() if name == english[slug]]
        # Coincidences are real and legitimate — German and English
        # both write Ps., Dan., Amos, Gal. — so the bar is "most of the
        # canon", not "none of it". A table that was never translated
        # scores 66.
        assert len(same) < len(english) / 2, f"{locale} still reads as English for {same}"
