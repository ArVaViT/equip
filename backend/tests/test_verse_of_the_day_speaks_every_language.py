# ruff: noqa: RUF002, RUF003
# The edition names in the prose are Cyrillic because that is their name.
"""The verse of the day exists in every language the platform serves.

It used to know two editions and answer 404 for anything else, so a
German or Ukrainian reader got an empty card on their home page the day
those languages shipped.

The interesting part is not the two new ids — it is the Psalm numbering
underneath them. Hebrew and Septuagint numbering disagree from Psalm 9
to Psalm 147, and a bible that follows the other system answers a
reference with a *different psalm* rather than an error. Get it wrong
and the platform prints "Psalm 23" over the text of Psalm 24, quietly,
forever.

So the numbering was checked against the live API rather than inferred
from the language — 2026-08-15, at every reference where the systems
disagree. НРТ is Septuagint-numbered; Luther 1912 and Куліш are not.
That last one is the point: a Slavic edition is not automatically
Septuagint-numbered, and assuming it would have been a plausible,
confident, wrong guess.

These tests pin what that check established.
"""

from __future__ import annotations

import pytest

from app.schemas.locale import LOCALE_CODES
from app.services import verse_of_the_day as svc


class TestEveryLanguageHasAnEdition:
    def test_no_served_language_is_missing(self):
        missing = [code for code in LOCALE_CODES if code not in svc._BIBLE_ID_BY_LOCALE]
        assert not missing, f"the route would answer 404 for {missing}"

    def test_the_editions_are_the_ones_that_were_checked(self):
        assert svc._BIBLE_ID_BY_LOCALE == {"en": 3034, "ru": 143, "de": 51, "uk": 188}


class TestPsalmNumbering:
    """A reference is remapped only for editions that actually number the
    Psalms the Septuagint way. Everything else is passed through."""

    @pytest.mark.parametrize("ref", ["PSA.23.1", "PSA.51.1", "PSA.116.1", "PSA.147.1", "JHN.3.16"])
    def test_german_is_never_remapped(self, ref: str):
        assert svc._remap_ref_for_locale(ref, "de") == ref

    @pytest.mark.parametrize("ref", ["PSA.23.1", "PSA.51.1", "PSA.116.1", "PSA.147.1", "JHN.3.16"])
    def test_ukrainian_is_never_remapped(self, ref: str):
        # Куліш answers Hebrew 23 with the shepherd psalm, the same as the
        # English edition. Remapping it would have served Psalm 22.
        assert svc._remap_ref_for_locale(ref, "uk") == ref

    def test_russian_still_shifts(self):
        # НРТ puts the shepherd psalm at 22, so the catalog's Hebrew 23
        # has to be asked for as 22.
        assert svc._remap_ref_for_locale("PSA.23.1", "ru") == "PSA.22.1"

    def test_russian_still_refuses_the_split_chapters(self):
        # Hebrew 116 is two psalms in the Septuagint; no per-verse remap
        # is honest, so the walk moves to the next catalog entry.
        assert svc._remap_ref_for_locale("PSA.116.1", "ru") is None

    def test_non_psalms_are_untouched_everywhere(self):
        for code in LOCALE_CODES:
            assert svc._remap_ref_for_locale("JHN.3.16", code) == "JHN.3.16"
