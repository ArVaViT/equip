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


def blocking(issues: list[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues if issue.blocking}


class TestACrossReferenceThatIsNotScripture:
    """``books.py`` declares 521 aliases and guards ten of them behind a
    capital or a printed dot. The rest are believed on sight, and the
    books of the Bible are named after ordinary words in every language
    served — so a course that numbers its exercises, its drawings or
    its table columns hands ``parse_references`` a Bible verse.

    Every source string below really does parse as scripture today. The
    translations are what a correct answer looks like when the target
    language renders the cross-reference its own way, at which point
    the digit pair is gone and the row was parked at ``needs_review``
    for losing a verse the lesson never cited.
    """

    @pytest.mark.parametrize(
        ("source", "translated"),
        [
            ("See Ex. 3:4 for the worked solution.", "Siehe Aufgabe 3 Punkt 4 für die Musterlösung."),
            ("Drawing Rev. 3:2 supersedes the earlier print.", "Zeichnung, Revision 3 Punkt 2, ersetzt den Druck."),
            ("Column Col. 3:14 holds the running total.", "Spalte C Punkt 3, Zeile 14, führt die Summe."),
            ("Judges 4:2 of the appellate circuit dissented.", "Richterin 4, Senat 2, gab ein Sondervotum ab."),
            ("Job 3:2 was posted on the careers page.", "Die Stelle 3, Ausschreibung 2, steht online."),
        ],
    )
    def test_a_cross_reference_that_reads_as_a_book_never_withholds_the_lesson(self, source: str, translated: str):
        issues = validate_translation(
            source=source,
            translated=translated,
            source_locale="en",
            target_locale="de",
        )
        assert blocking(issues) == set()

    def test_a_russian_table_caption_never_withholds_the_lesson(self):
        # «Числа» is the book of Numbers and it is also the word for
        # numbers, capitalised here only because it opens the sentence.
        issues = validate_translation(
            source="Числа 3:14 в таблице округлены до целых.",
            translated="Die Zahlen in Zeile 3, Spalte 14 sind auf ganze gerundet.",
            source_locale="ru",
            target_locale="de",
        )
        assert blocking(issues) == set()

    def test_a_reference_that_really_vanished_is_still_named(self):
        # Losing the veto is not losing the eyes: the code still goes on
        # the row, still earns a retry, and is still countable.
        issues = validate_translation(
            source="Прочитайте Бытие 1:26 и запишите свои наблюдения об образе Божьем.",
            translated="Read Genesis and write down your observations about the image of God.",
            source_locale="ru",
            target_locale="en",
        )
        assert "verse_reference_lost" in codes(issues)
        assert blocking(issues) == set()

    def test_a_dropped_scripture_marker_still_withholds_the_lesson(self):
        # What a lost pointer is not: lost scripture. A quoted verse
        # travels as a marker, and that check keeps its veto — which is
        # the whole reason this one can give hers up.
        issues = validate_translation(
            source="Пётр процитировал EQVa3f9c2 перед всем народом.",
            translated="Peter quoted it before the whole crowd.",
            source_locale="ru",
            target_locale="en",
        )
        assert "scripture_marker_mismatch" in blocking(issues)


class TestEmphasisAddedIsEditingAndEmphasisLostIsNot:
    """``_check_tags`` compared two sorted lists of tag names and could
    not tell "the document lost a paragraph" from "the editor italicised
    a word". Both were blocking. Measured over the live catalogue, the
    second is real: an English translation put ``<em>`` around the
    transliterated Russian word *nedelya*, exactly as a copy editor
    would, and the lesson was withheld for it.
    """

    def test_an_added_emphasis_tag_is_not_an_issue_at_all(self):
        issues = validate_translation(
            source="<p>Слово «неделя» происходит от «не делать», но означает семь дней.</p>",
            translated="<p>The word <em>nedelya</em> comes from “not doing,” but means seven days.</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert issues == []

    def test_a_lost_emphasis_tag_is_named_but_does_not_withhold_the_lesson(self):
        issues = validate_translation(
            source="<p>Апостол <strong>Павел</strong> написал это послание церкви в Коринфе.</p>",
            translated="<p>The apostle Paul wrote this letter to the church in Corinth.</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert "emphasis_lost" in codes(issues)
        assert blocking(issues) == set()

    def test_emphasis_moved_from_one_tag_to_another_does_not_withhold_the_lesson(self):
        issues = validate_translation(
            source="<p>Апостол <strong>Павел</strong> написал это послание церкви в Коринфе.</p>",
            translated="<p>The apostle <em>Paul</em> wrote this letter to the church in Corinth.</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert blocking(issues) == set()

    def test_a_lost_paragraph_still_withholds_the_lesson(self):
        # The live catalogue's true positive: a chapter block that
        # dropped one whole definition out of a list of eight.
        issues = validate_translation(
            source=(
                "<p><strong>Псалом</strong> — песнь или поэма, которую пели.</p>"
                "<p><strong>Притча</strong> — короткое изречение мудрости из книги Притчей.</p>"
            ),
            translated="<p><strong>Proverb</strong> — a short, punchy line of wisdom from the book of Proverbs.</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert "markup_mismatch" in blocking(issues)

    def test_a_paragraph_that_stopped_being_one_still_withholds_the_lesson(self):
        # The other live true positive: the tags came off entirely and
        # the block came back as a bare sentence.
        issues = validate_translation(
            source="<p>Павел пишет церкви в Коринфе о единстве и о любви.</p>",
            translated="Paul writes to the church in Corinth about unity and love.",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert "markup_mismatch" in blocking(issues)

    def test_an_invented_paragraph_still_withholds_the_lesson(self):
        issues = validate_translation(
            source="<p>Павел пишет церкви в Коринфе о единстве и о любви к ближнему.</p>",
            translated="<p>Paul writes to the church in Corinth</p><p>about unity and love of neighbour.</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert "markup_mismatch" in blocking(issues)

    def test_a_lost_link_is_not_treated_as_emphasis(self):
        # ``<a>`` sits inside a sentence like ``<em>`` does and is not
        # decoration: losing it loses where it pointed.
        issues = validate_translation(
            source='<p>Смотрите <a href="/plan">учебный план</a> курса и расписание занятий.</p>',
            translated="<p>See the course syllabus and the class schedule.</p>",
            source_locale="ru",
            target_locale="en",
            content_kind="html",
        )
        assert "markup_mismatch" in blocking(issues)


class TestTheDetectorMayNotVetoWhatItCannotRead:
    """Measured over all 12,434 active rows that carry prose in a locale
    with a same-script rival, both sides at once — the correct rows it
    contradicts, and how much genuine wrong-language content it would
    catch in the same band:

        band    pair    rows  false pos   FP rate   caught if wrong
        12-19   ru/uk   1371          1     0.07%       899  65.6%
        20-29   ru/uk   1516          1     0.07%      1211  79.9%
        30-44   ru/uk   1344          0     0.00%      1265  94.1%
        45-59   ru/uk    637          0     0.00%       627  98.4%
        60-∞    ru/uk   1260          0     0.00%      1260 100.0%
        12-19   de/en   1105          0     0.00%       801  72.5%
        20-29   de/en   1400          0     0.00%      1314  93.9%
        30-44   de/en   1400          0     0.00%      1371  97.9%
        45-59   de/en    827          0     0.00%       826  99.9%
        60-∞    de/en   1574          0     0.00%      1574 100.0%

    Both errors are one pair's — Ukrainian read as Russian, at 18 and
    24 letters. de/en is clean at every band. So the floor is scoped to
    the pair that earns it rather than applied to every same-script
    pair, and these tests pin both halves: what a floor must still
    catch, and what it must stop burying.
    """

    def test_a_short_ukrainian_answer_read_as_russian_is_still_served(self):
        # The row parked in production: «кожному» and «рядку» do not
        # exist in Russian, and 24 letters with no і, ї or є do not
        # contain enough evidence to say so.
        issues = validate_translation(
            source="В каждой строке по два образа",
            translated="У кожному рядку по два образи",
            source_locale="ru",
            target_locale="uk",
            content_kind="quiz_option",
        )
        assert "wrong_language" in codes(issues)
        assert blocking(issues) == set()

    def test_a_short_ukrainian_sentence_read_as_russian_is_still_served(self):
        issues = validate_translation(
            source="God revealed Himself to Abraham.",
            translated="Бог об'явився Аврааму.",
            source_locale="en",
            target_locale="uk",
            content_kind="quiz_option",
        )
        assert blocking(issues) == set()

    @pytest.mark.parametrize(
        ("translated", "target"),
        [
            # The defect that reached production in this project:
            # German prose sitting in an English row. 53 letters — under
            # the 60-letter floor this check first shipped with, which
            # is why that floor was a hole rather than a narrowing.
            ("Paulus schreibt der Gemeinde in Korinth über Einheit und Liebe.", "en"),
            # And short, because de/en is measured clean at every band.
            ("Das Schlagen des Felsens durch Mose", "en"),
            ("Die Herde des Jitro", "en"),
            ("The flock of Jethro, his father-in-law", "de"),
            ("Because Noah had built the ark according to specifications.", "de"),
        ],
    )
    def test_german_and_english_are_told_apart_at_any_length(self, translated: str, target: str):
        issues = validate_translation(
            source="Павел пишет церкви в Коринфе о единстве и о любви.",
            translated=translated,
            source_locale="ru",
            target_locale=target,
        )
        assert "wrong_language" in blocking(issues)

    @pytest.mark.parametrize(
        ("translated", "target"),
        [
            ("«Всякий, кто родился иудеем, спасётся»", "uk"),
            ("Какую формулу соборного решения фиксирует послание в Деян. 15:28?", "uk"),
            ("Він успадкував маєток свого батька.", "ru"),
            ("Живучи праведним життям і дотримуючись Закону.", "ru"),
        ],
    )
    def test_russian_and_ukrainian_are_told_apart_once_there_are_thirty_letters(self, translated: str, target: str):
        # Real sentences from the live catalogue, asked about as if they
        # sat in the other locale's row. From 30 letters the detector
        # names them, and the veto is worth having.
        issues = validate_translation(
            source="A sentence of the source, long enough not to be measured by its ratio.",
            translated=translated,
            source_locale="en",
            target_locale=target,
        )
        assert "wrong_language" in blocking(issues)

    def test_the_wrong_script_withholds_the_lesson_however_short_it_is(self):
        # Script is counted, not weighed. Cyrillic served to a German
        # reader is not a judgement call at any length.
        issues = validate_translation(
            source="Введение в книгу Бытия",
            translated="Введение в книгу Бытия",
            source_locale="ru",
            target_locale="de",
            content_kind="title",
        )
        assert "wrong_language" in blocking(issues)

    def test_a_whole_paragraph_in_the_wrong_language_still_withholds_the_lesson(self):
        issues = validate_translation(
            source=(
                "Der Apostel Paulus schrieb diesen Brief an die Gemeinde in Korinth, "
                "als sie sich in Gruppen aufspaltete und über die Gaben stritt."
            ),
            translated=(
                "The apostle Paul wrote this letter to the church in Corinth, "
                "when the community split into groups and argued about the gifts."
            ),
            source_locale="de",
            target_locale="de",
        )
        assert "wrong_language" in blocking(issues)

    def test_a_lesson_that_quotes_the_language_it_teaches_is_still_served(self):
        # A grammar course keeps the English phrase on purpose, and the
        # detector reads both sides as English because both sides mostly
        # are. It has misread the source in front of us, so its reading
        # of the answer is not evidence.
        issues = validate_translation(
            source='Правило: "I have been working here since 2019" — Present Perfect Continuous',
            translated='Regel: "I have been working here since 2019" — Present Perfect Continuous',
            source_locale="ru",
            target_locale="de",
        )
        assert blocking(issues) == set()

    def test_a_source_the_detector_reads_correctly_is_still_a_witness(self):
        # The guard above must not become a general amnesty: when the
        # detector agrees with the source's declared locale it has shown
        # nothing wrong with itself, and a Russian answer to a German
        # question still withholds the lesson.
        issues = validate_translation(
            source=(
                "Der Apostel Paulus schrieb diesen Brief an die Gemeinde in Korinth, "
                "als sie sich in Gruppen aufspaltete und über die Gaben stritt."
            ),
            translated=(
                "Апостол Павел написал это послание церкви в Коринфе, когда община "
                "разделилась на группы и спорила о духовных дарах."
            ),
            source_locale="de",
            target_locale="en",
        )
        assert "wrong_language" in blocking(issues)


class TestAStringWithNoWordInIt:
    """``_carries_prose`` asked whether any token survived the markup
    and the code spans. A formula and an identifier both survive, and
    both are the same string in every language — so a correct answer
    that returned one unchanged came back ``not_translated``, blocking.
    """

    def test_an_identifier_returned_unchanged_is_not_an_untranslated_string(self):
        option = "array.prototype.flatMap()"
        issues = validate_translation(
            source=option,
            translated=option,
            source_locale="ru",
            target_locale="de",
            content_kind="quiz_option",
        )
        assert issues == []

    def test_a_formula_returned_unchanged_is_not_an_untranslated_string(self):
        formula = "<p>2 H₂ + O₂ → 2 H₂O + 2 C₆H₁₂O₆ + 6 O₂</p>"
        issues = validate_translation(
            source=formula,
            translated=formula,
            source_locale="ru",
            target_locale="de",
            content_kind="html",
        )
        assert issues == []

    def test_a_sentence_returned_unchanged_is_still_an_untranslated_string(self):
        sentence = "Апостол Павел написал это послание церкви в Коринфе"
        issues = validate_translation(
            source=sentence,
            translated=sentence,
            source_locale="ru",
            target_locale="en",
        )
        assert "not_translated" in blocking(issues)

    def test_a_short_slavic_title_is_still_prose(self):
        # Measured: the stricter "most tokens must be words" reading
        # called 112 live rows prose-free, because one-letter
        # prepositions are not words and a short Slavic title is half
        # made of them. This one has to keep being judged.
        from app.services.translation.validation import _carries_prose

        assert _carries_prose("З жертовника в храмі")
        assert _carries_prose("Кто-то что-то сказал")
        assert _carries_prose("«Слово» — это глагол")

    def test_a_bare_number_is_not_prose(self):
        from app.services.translation.validation import _carries_prose

        assert not _carries_prose("12")
        assert not _carries_prose("<p>64</p>")
