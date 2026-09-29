# ruff: noqa: RUF001, RUF002 — the mixed alphabets below are the defect under test.
"""A German lesson with English sentences in it was served as ``ok``.

Production, 2026-09-29: two German blocks carried five English sentences —
«Open the first two or three verses of a prophetic book…» — because the
whole-text language check reads a mostly German block as German, which it
is. Two Ukrainian explanations carried «щz», one German block «Demтріус».
Measured over all 11,268 live machine rows the passage check flags exactly
those five and nothing else.
"""

from __future__ import annotations

from app.services.translation.validation import _check_passage_language, validate_translation

SOURCE_RU = (
    "<p>Пророческие книги легче читать, если знать эпоху.</p>"
    "<p>Приём. Откройте первые два-три стиха пророческой книги: там почти всегда назван царь или год.</p>"
)


def test_an_english_paragraph_in_a_german_lesson_is_caught() -> None:
    translated = (
        "<p>Prophetische Bücher lassen sich leichter lesen, wenn man die Epoche kennt, in der sie entstanden sind.</p>"
        "<p>Open the first two or three verses of a prophetic book: there, a king or a year is almost always named.</p>"
    )
    issue = _check_passage_language(SOURCE_RU, translated, source_locale="ru", target_locale="de")
    assert issue is not None
    assert issue.code == "wrong_language_passage"
    assert issue.blocking


def test_an_english_sentence_inside_a_german_paragraph_is_caught() -> None:
    translated = (
        "<p>Die Gemeinde in Antiochia wächst, und die Apostel müssen entscheiden, wie Heiden aufgenommen werden. "
        "This decision lays the groundwork for the Council of Jerusalem in chapter 15.</p>"
    )
    issue = _check_passage_language(SOURCE_RU, translated, source_locale="ru", target_locale="de")
    assert issue is not None and issue.code == "wrong_language_passage"


def test_a_word_in_two_alphabets_is_caught() -> None:
    translated = "<p>Demтріус der Silberschmied (Apg 19) – Initiator des Aufstands in Ephesus.</p>"
    issue = _check_passage_language(SOURCE_RU, translated, source_locale="ru", target_locale="de")
    assert issue is not None and issue.code == "mixed_script"


def test_a_clean_german_lesson_passes() -> None:
    translated = (
        "<p>Prophetische Bücher lassen sich leichter lesen, wenn man die Epoche kennt.</p>"
        "<p>Trick: Öffnen Sie die ersten zwei oder drei Verse eines prophetischen Buches – dort wird fast immer ein König oder ein Jahr genannt.</p>"
    )
    assert _check_passage_language(SOURCE_RU, translated, source_locale="ru", target_locale="de") is None


def test_a_quote_the_source_makes_on_purpose_is_left_alone() -> None:
    # A lesson about English Bibles quotes English in the Russian source;
    # the German translation keeps the quote.
    source = (
        "<p>В английской Библии короля Якова сказано так:</p>"
        "<p>In the beginning was the Word, and the Word was with God, and the Word was God.</p>"
    )
    translated = (
        "<p>In der englischen King-James-Bibel heißt es so:</p>"
        "<p>In the beginning was the Word, and the Word was with God, and the Word was God.</p>"
    )
    assert _check_passage_language(source, translated, source_locale="ru", target_locale="de") is None


def test_a_short_quote_in_another_alphabet_is_left_alone() -> None:
    # Under the 45-letter floor a passage in the source was not counted as
    # quoted, while the same passage in the translation was judged from 20
    # letters: a short Russian quote kept in a German lesson taught in
    # English was withheld.
    source = (
        "<p>The Russian Synodal Bible renders the opening line like this:</p>"
        "<p>В начале было Слово, и Слово было у Бога.</p>"
    )
    translated = (
        "<p>Die russische Synodalbibel gibt die erste Zeile so wieder:</p>"
        "<p>В начале было Слово, и Слово было у Бога.</p>"
    )
    assert _check_passage_language(source, translated, source_locale="en", target_locale="de") is None


def test_a_stray_passage_is_still_caught_when_it_is_not_in_the_source() -> None:
    source = "<p>The Russian Synodal Bible renders the opening line in its own way.</p>"
    translated = (
        "<p>Die russische Synodalbibel gibt die erste Zeile auf eigene Weise wieder.</p>"
        "<p>Откройте первые два-три стиха пророческой книги.</p>"
    )
    issue = _check_passage_language(source, translated, source_locale="en", target_locale="de")
    assert issue is not None and issue.code == "wrong_language_passage"


def test_it_withholds_the_row_through_the_full_validator() -> None:
    translated = (
        "<p>Prophetische Bücher lassen sich leichter lesen, wenn man die Epoche kennt, in der sie entstanden sind.</p>"
        "<p>Open the first two or three verses of a prophetic book: there, a king or a year is almost always named.</p>"
    )
    issues = validate_translation(
        source=SOURCE_RU, translated=translated, source_locale="ru", target_locale="de", content_kind="html"
    )
    assert any(i.code == "wrong_language_passage" and i.blocking for i in issues)
