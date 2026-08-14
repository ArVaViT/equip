# ruff: noqa: RUF001
# Mixed-script literals are the material under test.
"""What ``status='ok'`` is allowed to mean.

Before ``app.services.translation.validation``, an ``ok`` row meant the
HTTP call did not raise: ``gemini._parse_response`` inspects the
envelope — candidates, parts, ``finishReason``, non-empty text — and
nothing looks at the content. A response that dropped a scripture
marker, halved the markup, or answered in the wrong language is a
well-formed envelope, and every reader in the platform treats its
``ok`` as "this translation is good".

These tests pin both directions: the defects that must be caught, and —
just as important for a check that gates publishing — the ordinary
translations that must pass without a murmur.
"""

from __future__ import annotations

import pytest

from app.services.translation.validation import (
    ValidationIssue,
    summarise,
    validate_translation,
)


def codes(issues: list[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues}


class TestCleanTranslationsPass:
    """False positives are expensive here: this check will gate
    publishing, so an honest translation flagged is a course that
    cannot ship."""

    def test_ordinary_prose_ru_to_en(self):
        issues = validate_translation(
            source="Апостол Павел написал это послание церкви в Коринфе около 55 года.",
            translated="The apostle Paul wrote this letter to the church in Corinth around the year 55.",
            source_locale="ru",
            target_locale="en",
        )
        assert issues == []

    def test_ordinary_prose_en_to_ru(self):
        issues = validate_translation(
            source="Studying the first book of the Bible together, chapter by chapter.",
            translated="Изучаем первую книгу Библии вместе, глава за главой.",
            source_locale="en",
            target_locale="ru",
        )
        assert issues == []

    def test_html_with_matching_structure(self):
        issues = validate_translation(
            source="<p>Введение в <strong>книгу Бытия</strong></p><ul><li>Первый урок</li></ul>",
            translated="<p>Introduction to <strong>the book of Genesis</strong></p><ul><li>First lesson</li></ul>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert issues == []

    def test_scripture_markers_round_trip(self):
        issues = validate_translation(
            source="<blockquote>VERSE_a3f9c2b1</blockquote><p>Так начинается книга.</p>",
            translated="<blockquote>VERSE_a3f9c2b1</blockquote><p>This is how the book begins.</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert issues == []

    def test_short_title_is_not_measured_by_ratio(self):
        # "Yes"/"Да" style expansion is normal at this length.
        issues = validate_translation(
            source="Молитва",
            translated="Prayer",
            source_locale="ru",
            target_locale="en",
            content_kind="title",
        )
        assert issues == []

    def test_proper_noun_may_come_back_unchanged(self):
        # Rule 7 of the system prompt: already in the target language →
        # return unchanged. Below the identity threshold this is fine.
        issues = validate_translation(
            source="Genesis",
            translated="Genesis",
            source_locale="ru",
            target_locale="en",
            content_kind="title",
        )
        assert issues == []


class TestScriptureMarkers:
    """The marker stands in for canonical scripture during the call. A
    marker that does not come back is a student reading
    ``VERSE_a3f9c2b1`` where the verse should be."""

    def test_lost_marker_is_caught(self):
        issues = validate_translation(
            source="<blockquote>VERSE_a3f9c2b1</blockquote><p>Так начинается книга.</p>",
            translated="<blockquote>In the beginning God created the heavens</blockquote><p>This is how the book begins.</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert "scripture_marker_mismatch" in codes(issues)

    def test_invented_marker_is_caught(self):
        issues = validate_translation(
            source="<p>VERSE_a3f9c2b1</p>",
            translated="<p>VERSE_a3f9c2b1 VERSE_deadbeef</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert "scripture_marker_mismatch" in codes(issues)

    def test_altered_marker_is_caught(self):
        issues = validate_translation(
            source="<p>VERSE_a3f9c2b1</p>",
            translated="<p>VERSE_a3f9c2b2</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert "scripture_marker_mismatch" in codes(issues)


class TestMarkup:
    def test_dropped_tags_are_caught(self):
        issues = validate_translation(
            source="<p>Первый</p><ul><li>Один</li><li>Два</li></ul>",
            translated="<p>First: one, two</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert "markup_mismatch" in codes(issues)

    def test_attribute_changes_are_not_flagged(self):
        # Only tag names are compared: an alt text legitimately changes
        # language, the structure must not.
        issues = validate_translation(
            source='<img src="x.png" alt="Книга"/><p>Текст урока для проверки длины строки</p>',
            translated='<img src="x.png" alt="Book"/><p>Lesson text for checking the length of the line</p>',
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert issues == []


class TestPlaceholdersAndNumbers:
    def test_lost_placeholder_is_caught(self):
        issues = validate_translation(
            source="Здравствуйте, {name}! Ваш курс начинается сегодня.",
            translated="Hello! Your course starts today.",
            source_locale="ru",
            target_locale="en",
        )
        assert "placeholder_mismatch" in codes(issues)

    def test_lost_verse_number_is_caught(self):
        issues = validate_translation(
            source="Прочитайте Бытие 1:26 и запишите свои наблюдения об образе Божьем.",
            translated="Read Genesis and write down your observations about the image of God.",
            source_locale="ru",
            target_locale="en",
        )
        assert "numbers_lost" in codes(issues)

    def test_thousands_separators_do_not_trip_it(self):
        issues = validate_translation(
            source="Около 1 000 человек услышали проповедь в тот день в Иерусалиме.",
            translated="About 1,000 people heard the sermon that day in Jerusalem.",
            source_locale="ru",
            target_locale="en",
        )
        assert issues == []


class TestModelMisbehaviour:
    def test_fence_echoed_back_is_caught(self):
        issues = validate_translation(
            source="Введение в книгу Бытия для студентов первого курса",
            translated="===BEGIN_a1b2c3===\nIntroduction to Genesis\n===END_a1b2c3===",
            source_locale="ru",
            target_locale="en",
        )
        assert "fence_leaked" in codes(issues)

    def test_untranslated_echo_is_caught(self):
        source = "Апостол Павел написал это послание церкви в Коринфе"
        issues = validate_translation(
            source=source,
            translated=source,
            source_locale="ru",
            target_locale="en",
        )
        assert "not_translated" in codes(issues)

    def test_wrong_language_is_caught(self):
        issues = validate_translation(
            source="Introduction to the book of Genesis for first-year students",
            translated="Введение в книгу Бытия для студентов первого курса",
            source_locale="en",
            target_locale="en",
        )
        # Asked for English, answered in Russian.
        assert "wrong_language" in codes(issues)

    def test_truncated_response_is_caught(self):
        issues = validate_translation(
            source=(
                "Апостол Павел написал это послание церкви в Коринфе около 55 года, "
                "когда община разделилась на группы и спорила о духовных дарах."
            ),
            translated="The apostle Paul wrote",
            source_locale="ru",
            target_locale="en",
        )
        assert "length_suspicious" in codes(issues)

    def test_appended_explanation_is_caught(self):
        issues = validate_translation(
            source="Апостол Павел написал это послание церкви в Коринфе около 55 года.",
            translated=(
                "The apostle Paul wrote this letter to the church in Corinth around the year 55. "
                "Note: I have translated this passage faithfully, but you should know that the "
                "dating of this epistle is debated among scholars, and some place it as late as "
                "57 AD. If you would like, I can also provide a more formal register, or a "
                "version suitable for younger readers, or an explanation of the historical "
                "background of the Corinthian church and its divisions."
            ),
            source_locale="ru",
            target_locale="en",
        )
        assert "length_suspicious" in codes(issues)

    def test_expanded_quiz_option_is_caught(self):
        issues = validate_translation(
            source="Павел",
            translated="The apostle Paul, formerly known as Saul of Tarsus",
            source_locale="ru",
            target_locale="en",
            content_kind="quiz_option",
        )
        assert "length_suspicious" in codes(issues)

    def test_empty_translation_is_caught(self):
        issues = validate_translation(
            source="Введение в книгу Бытия",
            translated="   ",
            source_locale="ru",
            target_locale="en",
        )
        assert codes(issues) == {"empty"}


class TestSummarise:
    def test_summary_carries_codes_and_sentences(self):
        issues = [
            ValidationIssue(code="empty", detail="The translation is empty."),
            ValidationIssue(code="fence_leaked", detail="Fence markers."),
        ]
        summary = summarise(issues)
        assert "[empty]" in summary
        assert "[fence_leaked]" in summary
        assert "The translation is empty." in summary

    def test_no_issues_summarises_to_nothing(self):
        assert summarise([]) == ""


@pytest.mark.parametrize(
    "kind",
    ["plain", "html", "title", "quiz_question", "quiz_option"],
)
def test_every_content_kind_is_accepted(kind):
    # The signature takes the same vocabulary as the prompt builder;
    # a new kind must not raise here.
    validate_translation(
        source="Текст",
        translated="Text",
        source_locale="ru",
        target_locale="en",
        content_kind=kind,
    )
