# ruff: noqa: RUF001, RUF003
# Mixed-script literals and en dashes inside verse ranges are the
# material under test.
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

    def test_lost_verse_reference_is_caught(self):
        issues = validate_translation(
            source="Прочитайте Бытие 1:26 и запишите свои наблюдения об образе Божьем.",
            translated="Read Genesis and write down your observations about the image of God.",
            source_locale="ru",
            target_locale="en",
        )
        assert "verse_reference_lost" in codes(issues)

    def test_verse_reference_survives_spacing_differences(self):
        issues = validate_translation(
            source="Прочитайте Бытие 1:26–27 и запишите свои наблюдения об образе Божьем.",
            translated="Read Genesis 1:26–27 and write down your observations about the image of God.",
            source_locale="ru",
            target_locale="en",
        )
        assert issues == []

    def test_book_numbering_differences_are_not_flagged(self):
        # Production case. The Slavic tradition numbers these books
        # differently from the English one: "3–4 Царств" IS "1–2 Kings".
        # A faithful translation changes the digits, and a check on
        # bare numbers called it a defect.
        issues = validate_translation(
            source="Третья и четвёртая книги Царств рассказывают о Соломоне и о падении обоих царств.",
            translated="First and Second Kings tell of Solomon and the fall of both kingdoms.",
            source_locale="ru",
            target_locale="en",
        )
        assert issues == []

    def test_a_year_that_moves_is_not_flagged(self):
        # Years are not references; a translation may render or drop
        # one without breaking anything a student needs to look up.
        issues = validate_translation(
            source="Около 1 000 человек услышали проповедь в тот день в Иерусалиме.",
            translated="About a thousand people heard the sermon that day in Jerusalem.",
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

    def test_a_one_letter_title_may_grow(self):
        # Production case: a quiz titled "Q" renders as "Вопрос" —
        # six times the length, and obviously fine. Growth has to be
        # large in absolute terms too before it means anything.
        issues = validate_translation(
            source="Q",
            translated="Вопрос",
            source_locale="en",
            target_locale="ru",
            content_kind="title",
        )
        assert issues == []

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


class TestAClauseThatWasNeverTranslated:
    """``not_translated`` catches a whole string that came back as it went
    in. The failure production actually produced was one clause inside an
    otherwise good translation — a German sentence wrapping an English
    verse, because the model is told to leave quoted Scripture alone and
    nothing restored it in German. To the reader that is not a citation.
    """

    def test_a_quotation_left_in_the_source_language_is_caught(self):
        source = (
            "John 3:17 states, 'For God did not send his Son into the world to condemn "
            "the world, but in order that the world might be saved through him.'"
        )
        translated = (
            "Johannes 3:17 besagt: 'For God did not send his Son into the world to condemn "
            "the world, but in order that the world might be saved through him.'"
        )
        issues = validate_translation(
            source=source,
            translated=translated,
            source_locale="en",
            target_locale="de",
        )
        assert [issue.code for issue in issues if issue.code == "untranslated_run"]

    def test_a_fully_translated_sentence_passes(self):
        issues = validate_translation(
            source="The letter names its author in the opening verse, and the argument follows from it.",
            translated="Der Brief nennt seinen Verfasser im ersten Vers, und die Beweisführung folgt daraus.",
            source_locale="en",
            target_locale="de",
        )
        assert [issue.code for issue in issues] == []

    def test_a_short_source_cannot_trigger_it(self):
        # Ten words is the bar; a title or an answer option never reaches
        # it, so a proper name repeated verbatim is not a defect.
        issues = validate_translation(
            source="Paul writes to the Romans",
            translated="Paul writes to the Romans",
            source_locale="en",
            target_locale="de",
            content_kind="title",
        )
        assert "untranslated_run" not in [issue.code for issue in issues]

    def test_scripture_markers_are_not_evidence(self):
        # Markers are identical on both sides by design — they are what
        # the canonical text is restored into afterwards.
        marker = "VERSE_0123456789abcdef"
        source = f"According to the passage: {marker} and the argument that follows from it here."
        translated = f"Laut der Stelle: {marker} und die daraus folgende Beweisführung hier."
        issues = validate_translation(
            source=source,
            translated=translated,
            source_locale="en",
            target_locale="de",
        )
        assert "untranslated_run" not in [issue.code for issue in issues]

    def test_the_same_language_is_not_a_translation(self):
        issues = validate_translation(
            source="A sentence that is long enough to have ten words in it, easily.",
            translated="A sentence that is long enough to have ten words in it, easily.",
            source_locale="en",
            target_locale="en",
        )
        assert "untranslated_run" not in [issue.code for issue in issues]


class TestAReferenceIsTheNumbersNotThePunctuation:
    """Every language served here writes a reference its own way, and the
    prompt now asks for that. The check has to read them as the same
    reference or it parks a correct translation for review — which it
    did, in production, for every German explanation that carried one.
    """

    def test_the_german_comma_is_not_a_lost_reference(self):
        issues = validate_translation(
            source="What does the passage promise, as stated in John 3:16?",
            translated="Was verspricht die Stelle, wie in Johannes 3,16 beschrieben?",
            source_locale="en",
            target_locale="de",
        )
        assert "verse_reference_lost" not in [issue.code for issue in issues]

    def test_an_en_dash_range_is_not_a_lost_reference(self):
        issues = validate_translation(
            source="What is promised to anyone who believes, as stated in John 3:14-16?",
            translated="Яким є обіцяний результат для кожного, хто вірить, як зазначено в Івана 3:14–16?",
            source_locale="en",
            target_locale="uk",
        )
        assert "verse_reference_lost" not in [issue.code for issue in issues]

    def test_a_reference_that_really_vanished_is_still_caught(self):
        issues = validate_translation(
            source="What is promised to anyone who believes, as stated in John 3:14-16?",
            translated="Was wird jedem versprochen, der glaubt, wie die Stelle beschreibt?",
            source_locale="en",
            target_locale="de",
        )
        assert "verse_reference_lost" in [issue.code for issue in issues]

    def test_a_different_verse_is_not_the_same_reference(self):
        issues = validate_translation(
            source="What does the passage promise, as stated in John 3:16?",
            translated="Was verspricht die Stelle, wie in Johannes 3,17 beschrieben?",
            source_locale="en",
            target_locale="de",
        )
        assert "verse_reference_lost" in [issue.code for issue in issues]


class TestANumberIsNotAlwaysAReference:
    """Broadening the separator to ``[:.,]`` so a German "Johannes 3,16"
    compares equal to "John 3:16" swept in everything else written as
    two numbers with a comma between them. And a row parked at
    ``needs_review`` with an unchanged source hash is never retried, so
    each false positive retired a correct translation permanently.
    """

    def test_a_date_is_not_a_lost_verse(self):
        issues = validate_translation(
            source="Enrolment closes on August 15, 2026, and places are limited.",
            translated="Die Anmeldung endet am 15. August 2026, und die Plätze sind begrenzt.",
            source_locale="en",
            target_locale="de",
        )
        assert [issue.code for issue in issues] == []

    def test_a_thousands_separator_is_not_a_lost_verse(self):
        issues = validate_translation(
            source="The church had about 1,000 households.",
            translated="Die Gemeinde hatte etwa 1000 Haushalte.",
            source_locale="en",
            target_locale="de",
        )
        assert [issue.code for issue in issues] == []

    @pytest.mark.parametrize("dash", ["-", "–", "—", "‑", "−"])
    def test_every_dash_a_range_might_use(self, dash: str):
        # A model reaches for a non-breaking hyphen so the range does not
        # break across a line. That is not a lost reference.
        issues = validate_translation(
            source="See John 3:14-16 for the promise.",
            translated=f"Siehe Johannes 3,14{dash}16 für die Verheißung.",
            source_locale="en",
            target_locale="de",
        )
        assert "verse_reference_lost" not in [issue.code for issue in issues]

    def test_a_reference_that_really_vanished_is_still_caught(self):
        issues = validate_translation(
            source="What is promised in John 3:14-16?",
            translated="Was wird in Johannes verheißen?",
            source_locale="en",
            target_locale="de",
        )
        assert "verse_reference_lost" in [issue.code for issue in issues]


class TestWhatIsNotProse:
    def test_a_code_block_that_survives_is_not_an_untranslated_run(self):
        code = "<pre><code>for chapter in course.chapters: print(chapter.title)</code></pre>"
        issues = validate_translation(
            source=f"<p>Run this to list the lessons:</p>{code}",
            translated=f"<p>Führen Sie dies aus, um die Lektionen aufzulisten:</p>{code}",
            source_locale="en",
            target_locale="de",
            content_kind="html",
        )
        assert "untranslated_run" not in [issue.code for issue in issues]

    def test_a_run_matches_only_at_word_boundaries(self):
        # "near" inside "nearby" used to count, which widened the net of
        # every false positive this rule can produce.
        from app.services.translation.validation import _check_untranslated_run

        issue = _check_untranslated_run(
            "the near the near the near the near the near",
            "Xthe nearby Xthe nearby Xthe nearby Xthe nearby Xthe nearby",
            source_locale="en",
            target_locale="de",
        )
        assert issue is None
