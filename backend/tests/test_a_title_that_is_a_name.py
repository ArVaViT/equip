# Russian titles are the source language here; the Latin ones beside
# them are the point of the comparison.
"""A title that came back unchanged, or reading as another language, is
a note for a person — not a reason to hold the course out of the
catalogue.

Two checks were parking course titles in production. ``not_translated``
fires on an unchanged string of 25 characters or more, and a title is
where unchanged is most often right: ``Alpha & Omega Bible School`` is
the same six words in Russian, English, German and Ukrainian. Four
``course:title`` rows parked ru→en on it. ``wrong_language`` fires when
the detector reads the answer as another language, and a title is the
length at which the detector is weakest by its own account — and the
place where a phrase is most often *meant* to be in another language.
Two ``course:title`` rows parked ru→de on it.

A parked title is a course nobody can see. So for titles these two
checks keep their eyes and lose their veto, the way ``untranslated_run``
did on 2026-08-19: the code is still logged, the model is still shown
the complaint and asked again, and the row is served.

With one line held. A title in the author's own alphabet, in front of a
reader whose language uses another, is not a name the detector misread;
it is Russian on a German catalogue card. That still blocks, in both
checks, and this file pins that it does.
"""

from __future__ import annotations

from app.services.translation.validation import validate_translation


def _codes(issues) -> dict[str, bool]:
    return {issue.code: issue.blocking for issue in issues}


class TestAnUnchangedTitle:
    def test_a_latin_name_kept_in_an_english_row_is_served(self) -> None:
        """The production row, four times over."""
        issues = validate_translation(
            source="Alpha & Omega Bible School",
            translated="Alpha & Omega Bible School",
            source_locale="ru",
            target_locale="en",
            content_kind="title",
        )
        assert _codes(issues) == {"not_translated": False}

    def test_the_same_string_as_a_paragraph_still_blocks(self) -> None:
        """Nothing changes outside titles. A paragraph that came back
        identical is a paragraph the model did not translate."""
        issues = validate_translation(
            source="Alpha & Omega Bible School",
            translated="Alpha & Omega Bible School",
            source_locale="ru",
            target_locale="en",
            content_kind="plain",
        )
        assert _codes(issues)["not_translated"] is True

    def test_a_latin_name_in_a_ukrainian_row_is_served(self) -> None:
        """Neither party's alphabet: a name kept as its owner spells it."""
        issues = validate_translation(
            source="Alpha & Omega Bible School",
            translated="Alpha & Omega Bible School",
            source_locale="ru",
            target_locale="uk",
            content_kind="title",
        )
        assert _codes(issues)["not_translated"] is False

    def test_within_one_alphabet_a_title_is_served(self) -> None:
        issues = validate_translation(
            source="Alpha & Omega Bible School",
            translated="Alpha & Omega Bible School",
            source_locale="en",
            target_locale="de",
            content_kind="title",
        )
        assert _codes(issues) == {"not_translated": False}

    def test_a_cyrillic_title_in_a_german_row_still_blocks(self) -> None:
        """The line that is held. This is not a name; it is the author's
        title, untranslated, for a reader who cannot read it."""
        issues = validate_translation(
            source="Введение в Послание к Римлянам",
            translated="Введение в Послание к Римлянам",
            source_locale="ru",
            target_locale="de",
            content_kind="title",
        )
        assert _codes(issues)["not_translated"] is True


class TestATitleReadAsAnotherLanguage:
    def test_english_on_a_german_card_is_served(self) -> None:
        """The other production shape, twice over: a school named in
        English, the German row keeps the name, the detector reads it
        as English. Within one alphabet that is a note, not a veto."""
        issues = validate_translation(
            source="Библейская школа Альфа и Омега",
            translated="Alpha and Omega Bible School of Theology",
            source_locale="ru",
            target_locale="de",
            content_kind="title",
        )
        assert _codes(issues) == {"wrong_language": False}

    def test_the_same_text_as_a_paragraph_still_blocks(self) -> None:
        issues = validate_translation(
            source="Библейская школа Альфа и Омега",
            translated="Alpha and Omega Bible School of Theology",
            source_locale="ru",
            target_locale="de",
            content_kind="plain",
        )
        assert _codes(issues)["wrong_language"] is True

    def test_cyrillic_on_a_german_card_still_blocks(self) -> None:
        """Across alphabets the detector is not guessing, and a German
        reader is not served a Russian title."""
        issues = validate_translation(
            source="Библейская школа Альфа и Омега",
            translated="Библейская школа богословия Альфа и Омега",
            source_locale="ru",
            target_locale="de",
            content_kind="title",
        )
        assert _codes(issues)["wrong_language"] is True
