# ruff: noqa: RUF001
# «Дії» beside `Діїв.` and `Rut` beside `Ruth` is the subject matter, not
# a typo.
"""The spellings the live catalogue printed, and the ones it printed correctly.

Every string below is quoted from production. The first half is what
native editors found — one book of the Bible printed several ways inside
one language, including two books that do not exist in the language they
were printed in. The second half is the half that decides whether this
check survives contact with a person: correct German, correct English
and correct Ukrainian that must stay quiet, including the four
spellings an earlier version of this work reported as defects.

The negative cases are not decoration. ``Isaiah`` in English prose was
flagged by the first attempt, because the alias table held sixty-six
English abbreviations and no full names. A check that names correct
prose gets switched off, and then it catches nothing at all.
"""

from __future__ import annotations

import pytest

from app.services.bible.books import (
    all_canonical_slugs,
    display_book_name,
    find_book,
    find_book_written_in,
    not_printed_in,
)
from app.services.translation.book_names import foreign_book_names
from app.services.translation.validation import validate_translation

LOCALES = ("ru", "en", "de", "uk")


# ---------------------------------------------------------------------
# The table underneath, which is what the first attempt got wrong
# ---------------------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_every_language_can_read_back_the_abbreviation_it_prints(locale: str) -> None:
    for slug in all_canonical_slugs():
        printed = display_book_name(slug, locale)
        assert printed is not None, f"{locale} does not print {slug}"
        assert find_book_written_in(printed, locale) == slug, f"{locale} cannot read back {printed!r}"


@pytest.mark.parametrize(
    ("name", "locale", "slug"),
    [
        # The refusals that made the first version of this check report
        # correct prose as a defect.
        ("Isaiah", "en", "isaiah"),
        ("Philippians", "en", "philippians"),
        ("Song of Songs", "en", "songofsolomon"),
        ("Esther", "de", "esther"),
        ("Daniel", "de", "daniel"),
        ("Titus", "de", "titus"),
        ("Бытие", "ru", "genesis"),
        ("Деяний", "ru", "acts"),
        ("Откровение", "ru", "revelation"),
        # Two spellings both legitimate: the check's job is to catch a
        # spelling the language does not print, not to impose a style.
        ("1. Mose", "de", "genesis"),
        ("Genesis", "de", "genesis"),
        ("Rut", "de", "ruth"),
        ("Ruth", "de", "ruth"),
        ("Hiob", "de", "job"),
        ("Ijob", "de", "job"),
        ("Псалтирь", "ru", "psalms"),
        ("Псалом", "ru", "psalms"),
        ("Дії", "uk", "acts"),
        ("Діяння", "uk", "acts"),
        ("Рут", "uk", "ruth"),
    ],
)
def test_a_language_recognises_a_name_it_really_does_print(name: str, locale: str, slug: str) -> None:
    assert find_book_written_in(name, locale) == slug


@pytest.mark.parametrize(
    ("name", "locale"),
    [
        ("Руф", "uk"),  # Russian; Ukrainian prints Рут
        ("Rev.", "de"),  # English; a German reader meets Revision
        ("Ex.", "de"),  # English; a German reader meets Exemplar
        ("Ин.", "de"),  # Russian abbreviation inside a German page
        ("Hoheslied", "de"),  # not a German word — the noun is das Hohelied
        ("3. Könige", "de"),  # no German Bible has a third book of Kings
        ("Діїв.", "uk"),
        ("Ді.", "uk"),
        ("Деянь", "uk"),
    ],
)
def test_a_language_refuses_a_name_it_does_not_print(name: str, locale: str) -> None:
    assert find_book_written_in(name, locale) is None


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Руф", "ruth"),
        ("Ин.", "john"),
        ("Rev.", "revelation"),
        ("Hoheslied", "songofsolomon"),
    ],
)
def test_the_wide_lookup_still_reads_what_the_narrow_one_refuses(name: str, slug: str) -> None:
    """A Russian abbreviation inside a German page still has to be
    readable — that is what makes the German typography rule work, and
    what lets the substitution layer protect a verse in a row whose
    reference is misspelled."""
    assert find_book(name) == slug


@pytest.mark.parametrize("locale", LOCALES)
def test_nothing_is_both_printed_and_not_printed_here(locale: str) -> None:
    for form, slug in not_printed_in(locale):
        assert find_book_written_in(form, locale) is None, f"{form!r} is listed as not printed and is native"
        assert find_book(form, locale) == slug, f"{form!r} is listed and the wide lookup cannot read it"


# ---------------------------------------------------------------------
# What the catalogue printed, and had to be caught
# ---------------------------------------------------------------------


def test_ukrainian_acts_abbreviated_to_a_word_ukrainian_does_not_have() -> None:
    """Thirteen key passages in one appendix, every one of them «Діїв.»."""
    assert foreign_book_names(
        "<li><strong>Деян. 1:8</strong> — программа книги.</li>",
        "<li><strong>Діїв. 1:8</strong> — програма книги.</li>",
        source_locale="ru",
        target_locale="uk",
    ) == [("Діїв.", "Дії")]


def test_ukrainian_acts_cut_down_to_two_letters() -> None:
    assert foreign_book_names(
        "Какие четыре столпа первой общины перечислены в Деян. 2:42?",
        "Які чотири стовпи першої громади перелічені в Ді. 2:42?",
        source_locale="ru",
        target_locale="uk",
    ) == [("Ді.", "Дії")]


def test_a_russian_stem_wearing_a_ukrainian_ending_with_no_numbers_near_it() -> None:
    """«Люди книги Деянь» — a heading, so nothing anchors it to a verse.
    It is caught because somebody read it and wrote it down, which is
    the only way an invented spelling can be caught."""
    assert foreign_book_names(
        "<h2>Люди книги Деяний: кто есть кто</h2>",
        "<h2>Люди книги Деянь: хто є хто</h2>",
        source_locale="ru",
        target_locale="uk",
    ) == [("Деянь", "Дії")]


def test_ukrainian_ruth_left_in_its_russian_form() -> None:
    assert foreign_book_names(
        "Согласно Руфь 1:1, из какого города отправился человек со своей семьей?",
        "Згідно з Руф 1:1, з якого міста вирушив чоловік та його родина?",
        source_locale="ru",
        target_locale="uk",
    ) == [("Руф", "Рут")]


def test_german_sent_to_a_book_of_kings_that_is_not_in_a_german_bible() -> None:
    """Luther numbers Kings 1-2, having numbered Samuel 1-2. The Slavonic
    «3 Царств» counts Samuel in; carrying the digit across invents a book."""
    assert foreign_book_names(
        "«...не в рукотворенных храмах живёт» (7:47–50; ср. 3 Цар. 8:27).",
        "„...nicht in von Menschenhand gemachten Tempeln wohnt“ (7,47–50; vgl. 3. Könige 8,27).",
        source_locale="ru",
        target_locale="de",
    ) == [("3. Könige", "1. Kön.")]


def test_ukrainian_makes_the_same_mistake_with_the_same_book() -> None:
    assert foreign_book_names(
        "В 3 Царств 18:1 сказано: «По прошествии многих дней слово Господне было к Илии...»",
        "3 Царів 18:1 говорить: «А як минуло багато днів, то слово Господнє стало до Іллі...»",
        source_locale="ru",
        target_locale="uk",
    ) == [("3 Царів", "1 Цар.")]


def test_a_german_explanation_citing_the_english_name_of_the_gospel() -> None:
    """The same Daily Challenge item's question correctly says
    «Markus 5,1»; its explanation says «Mark 5,1»."""
    assert foreign_book_names(
        "Марка 5:1 гласит: «И прибыли в страну Гадаринскую по ту сторону моря».",
        "Mark 5,1 besagt: „Und sie kamen an das jenseitige Ufer des Sees.“",
        source_locale="ru",
        target_locale="de",
    ) == [("Mark", "Mk.")]


def test_a_ukrainian_question_that_its_own_answer_contradicts() -> None:
    """The question asks about «Галатам 2:1»; the explanation of the same
    item cites «Галатів 2:1», which is what Ukrainian prints."""
    assert foreign_book_names(
        "Согласно Галатам 2:1, сколько лет прошло между первой поездкой Павла в Иерусалим?",
        "Згідно з Галатам 2:1, скільки років минуло між першою подорожжю Павла до Єрусалима?",
        source_locale="ru",
        target_locale="uk",
    ) == [("Галатам", "Гал.")]


# ---------------------------------------------------------------------
# What the catalogue printed correctly, and must never be named
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "translated", "locale"),
    [
        # Both spellings of the German Pentateuch are real German, and
        # the catalogue prints both: 1./2./5. Mose in 102 rows,
        # Genesis/Exodus/Levitikus in 52.
        ("Бытие 1:1 говорит...", "1. Mose 1,1 sagt...", "de"),
        ("Бытие 1:1 говорит...", "Genesis 1,1 sagt...", "de"),
        ("Левит 23:3 говорит...", "Levitikus 23,3 sagt...", "de"),
        ("Левит 23:3 говорит...", "3. Mose 23,3 sagt...", "de"),
        ("Есфирь 4:14 говорит...", "Esther 4,14 sagt...", "de"),
        ("Есфирь 4:14 говорит...", "Est. 4,14 sagt...", "de"),
        ("Руфь 1:16 говорит...", "Rut 1,16 sagt...", "de"),
        ("Руфь 1:16 говорит...", "Ruth 1,16 sagt...", "de"),
        # Correct English, which the first attempt reported as a defect.
        ("Исаия 40:31 говорит...", "Isaiah 40:31 says...", "en"),
        ("Исаия 40:31 говорит...", "Isa. 40:31 says...", "en"),
        ("Филиппийцам 4:13 говорит...", "Philippians 4:13 says...", "en"),
        # Correct Ukrainian, in the two spellings the catalogue uses.
        ("Деян. 2:42 говорит...", "Дії 2:42 говорить...", "uk"),
        ("Деян. 2:42 говорит...", "Дії апостолів 2:42 говорить...", "uk"),
        ("Руфь 1:16 говорит...", "Рут 1:16 говорить...", "uk"),
    ],
)
def test_a_spelling_the_language_really_prints_is_never_named(source: str, translated: str, locale: str) -> None:
    assert foreign_book_names(source, translated, source_locale="ru", target_locale=locale) == []


@pytest.mark.parametrize(
    ("source", "translated"),
    [
        # Ukrainian declines a book name in running prose. Every one of
        # these is correct, and every one of them is what a scan reading
        # the word in front of the numbers offers up as an invented book.
        (
            "Согласно Исаии 7:1, ...",
            "Згідно з Ісаєю 7:1, ...",
        ),
        (
            "В Бытие 1:1 сказано...",
            "У Бутті 1:1 сказано...",
        ),
        (
            "Согласно книге Числа 13:2, ...",
            "Згідно з книгою Чисел 13:2, ...",
        ),
        (
            "Во Второзаконии 34:1 сказано...",
            "У Повторенні Закону 34:1 сказано...",
        ),
        (
            "В Псалом 51:1 сказано...",
            "У Псалмі 51:1 сказано...",
        ),
        (
            "В Откровении 3:1 сказано...",
            "В Об’явленні 3:1 сказано...",
        ),
        (
            "Согласно Деяниям 9:5, ...",
            "Згідно з Діяннями 9:5, ...",
        ),
        (
            "Согласно Осии 11:1, ...",
            "Згідно з Осією 11:1, ...",
        ),
        (
            "В книге Иисуса Навина 6:1 ...",
            "У книзі Ісуса Навина 6:1 ...",
        ),
    ],
)
def test_an_ordinary_ukrainian_declension_is_not_an_invented_book(source: str, translated: str) -> None:
    assert foreign_book_names(source, translated, source_locale="ru", target_locale="uk") == []


def test_an_ordinary_german_word_in_front_of_two_numbers_is_not_a_book() -> None:
    """«Schlüsselstellen 1,8» is a heading over a list of key passages."""
    assert (
        foreign_book_names(
            "Деян. 1:8 — программа книги.",
            "Schlüsselstellen 1,8 — das Programm des Buches.",
            source_locale="ru",
            target_locale="de",
        )
        == []
    )


def test_a_clock_is_still_not_a_chapter_and_verse() -> None:
    assert (
        foreign_book_names(
            "Занятие начинается в 14:30.",
            "Der Kurs beginnt um 14:30 Uhr.",
            source_locale="ru",
            target_locale="de",
        )
        == []
    )


def test_a_psalm_renumbered_between_editions_is_not_a_wrong_name() -> None:
    """The Russian source cites Synodal Пс. 109:1 and correct German
    prints Ps. 110,1. Comparing bare numbers would lose the anchor."""
    assert (
        foreign_book_names(
            "«Сказал Господь Господу моему» (Пс. 109:1).",
            "„Der HERR sprach zu meinem Herrn“ (Ps. 110,1).",
            source_locale="ru",
            target_locale="de",
        )
        == []
    )


def test_a_row_translated_into_its_own_language_is_left_alone() -> None:
    assert foreign_book_names("Деян. 1:8", "Деян. 1:8", source_locale="ru", target_locale="ru") == []


# ---------------------------------------------------------------------
# What the validator does with it
# ---------------------------------------------------------------------


def test_the_validator_names_the_spelling_and_does_not_withhold_the_lesson() -> None:
    """A student who reads «Діїв. 1:8» finds Acts 1:8; a student who
    reads a blank finds nothing. So the issue is reported, earns its
    retry, and is served — it is not a veto and it is not advisory."""
    issues = validate_translation(
        source="<p>Деян. 1:8 — программа книги.</p>",
        translated="<p>Діїв. 1:8 — програма книги.</p>",
        source_locale="ru",
        target_locale="uk",
    )
    named = [issue for issue in issues if issue.code == "book_name_not_printed_here"]
    assert len(named) == 1
    assert named[0].blocking is False
    assert named[0].advisory is False
    assert "Діїв." in named[0].detail
    assert "Дії" in named[0].detail


def test_a_correct_translation_of_the_same_sentence_raises_nothing() -> None:
    issues = validate_translation(
        source="<p>Деян. 1:8 — программа книги.</p>",
        translated="<p>Дії 1:8 — програма книги.</p>",
        source_locale="ru",
        target_locale="uk",
    )
    assert [issue.code for issue in issues if issue.code == "book_name_not_printed_here"] == []
