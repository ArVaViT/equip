# ruff: noqa: RUF001
# Cyrillic and Latin side by side is the subject matter here, not a typo.
"""The nine failures three native editors found, and the prose around them.

Every source string below is quoted from the live catalogue, and every
translation is either what production actually served or — where the
defect sits in a chapter nobody has published since — the wording the
editors reported. The point of writing them out is that a later edit to
the table cannot quietly stop catching one of them.

The negative half matters at least as much. A check that flags correct
prose gets switched off by a person and is worth less than nothing, so
the rows that must stay quiet are here too: a name transliterated three
ways, a German Bible citing *1. Mose* where the Russian cites «Бытие»,
the same lesson's city called by its own name, and the four rows the
first measurements got wrong.
"""

from __future__ import annotations

import pytest

from app.services.translation.proper_names import substituted_names
from app.services.translation.validation import validate_translation

# ---------------------------------------------------------------------
# The five the check is built to see
# ---------------------------------------------------------------------


def test_a_synagogue_ruler_answered_with_the_other_one_from_the_same_chapter() -> None:
    """Acts 18:8. Crispus believes; Sosthenes is beaten in verse 17."""
    assert substituted_names(
        "Сам начальник синагоги Крисп уверовывает.",
        "Der Synagogenvorsteher Sosthenes selbst kommt zum Glauben.",
        source_locale="ru",
        target_locale="de",
    ) == [("Крисп", "Sosthenes")]


def test_the_apostle_chosen_to_replace_judas_answered_with_the_evangelist() -> None:
    """Matthias is elected in Acts 1. Matthew wrote a Gospel."""
    assert substituted_names(
        "Избрание Матфия восстанавливает символическое число «нового Израиля».",
        "Die Wahl des Matthäus stellt die symbolische Zahl des „neuen Israel“ wieder her.",
        source_locale="ru",
        target_locale="de",
    ) == [("Матфия", "Matthäus")]


def test_the_same_apostle_is_answered_with_the_evangelist_in_ukrainian_too() -> None:
    """«Матвій» is Matthew; Matthias is «Матій». Live, and unreported."""
    assert substituted_names(
        "Избрание Матфия восстанавливает символическое число «нового Израиля».",
        "Обрання Матвія відновлює символічне число «нового Ізраїлю».",
        source_locale="ru",
        target_locale="uk",
    ) == [("Матфия", "Матвія")]


def test_a_lesson_about_the_evangelist_titled_with_the_name_of_a_city() -> None:
    """Philip preaches in Acts 8. Philippi is Acts 16, eight lessons later."""
    assert substituted_names(
        "Урок 5. Филипп: Евангелие пересекает границы (Деяния 8)",
        "Lektion 5. Philippi: Das Evangelium überschreitet Grenzen (Apostelgeschichte 8)",
        source_locale="ru",
        target_locale="de",
    ) == [("Филипп", "Philippi")]


def test_a_sentence_that_contradicts_itself_about_which_name_is_the_greek_one() -> None:
    """Dorcas *is* the Greek name, so «Дорка (грецькою Серна)» is nonsense."""
    assert substituted_names(
        "Воскрешением Тавифы (арамейское имя; по-гречески Серна) в Иоппии.",
        "Воскресінням Дорки (арамейське ім’я; грецькою Серна) в Йопії.",
        source_locale="ru",
        target_locale="uk",
    ) == [("Тавифы", "Дорки")]


# ---------------------------------------------------------------------
# What it found that nobody had reported
# ---------------------------------------------------------------------


def test_a_wrong_answer_rewritten_into_the_subject_of_the_right_one() -> None:
    """The question is which passage the eunuch was reading; the correct
    answer is Isaiah 53. The distractor «Книгу Иова» came back as *the
    book of Isaiah*, so the English quiz offers Isaiah twice."""
    assert substituted_names(
        "Книгу Иова",
        "The book of Isaiah",
        source_locale="ru",
        target_locale="en",
    ) == [("Иова", "Isaiah")]


def test_a_wrong_answer_rewritten_into_the_place_the_question_names() -> None:
    """ "To whom is Paul's farewell speech in Miletus addressed?" — and one
    of the options is now *To the inhabitants of Miletus*."""
    assert substituted_names(
        "К жителям Троады",
        "To the inhabitants of Miletus",
        source_locale="ru",
        target_locale="en",
    ) == [("Троады", "Miletus")]


# ---------------------------------------------------------------------
# The four this check is silent about, and each is silent on purpose
# ---------------------------------------------------------------------


def test_a_name_mangled_into_three_spellings_is_not_a_substitution() -> None:
    """«Лій», «Лісій» and «Лисий» are three attempts at Lysias, one of
    which reads as the adjective *bald*. None of them is another person,
    so nothing here can name what went wrong; that wants a check about
    spelling, which this deliberately is not."""
    for mangled in ("Клавдій Лій", "Клавдій Лісій", "Клавдій Лисий"):
        assert substituted_names("Клавдий Лисий", mangled, source_locale="ru", target_locale="uk") == [], mangled


def test_a_mountain_shortened_into_a_divine_title_is_not_a_substitution() -> None:
    """«Син» is the Ukrainian for "the Son" — not a person or a place, and
    putting titles in the table takes the live catalogue from nine flags
    to twenty-eight. See the module docstring for the measurement."""
    assert (
        substituted_names(
            "Моисей поднимается на гору Синай.",
            "Мойсей піднімається на гору Син.",
            source_locale="ru",
            target_locale="uk",
        )
        == []
    )


def test_a_gate_named_for_its_beauty_translated_as_a_colour_is_not_a_substitution() -> None:
    """Ὡραία is *Beautiful*; «Красные» is the archaic Russian for it and
    the modern word for red. What came back is an adjective, and no
    different name appeared."""
    assert (
        substituted_names(
            "Исцеление у Красных ворот (3:1–10).",
            "Зцілення біля Червоних воріт (3:1–10).",
            source_locale="ru",
            target_locale="uk",
        )
        == []
    )


def test_one_russian_word_for_two_cities_cannot_say_which_one_was_meant() -> None:
    """Russian spells Babel and Babylon «Вавилон». The source names both
    rows at once, so the English naming one of them introduces nothing —
    and telling Genesis 11 from Revelation 17 needs the chapter, not the
    word."""
    assert (
        substituted_names(
            "Смешение языков в Вавилоне.",
            "The confusion of tongues at Babylon.",
            source_locale="ru",
            target_locale="en",
        )
        == []
    )


def test_a_divine_title_answered_with_a_common_noun_is_not_a_substitution() -> None:
    """«Господь» → *the Gospel* is wrong and this check will not say so.
    Neither word is the name of a person or a place, and the table that
    would hold them is the one measured above at nineteen extra flags."""
    assert (
        substituted_names(
            "Господь отверз сердце её внимать тому, что говорил Павел.",
            "The Gospel opened her heart to pay attention to what Paul was saying.",
            source_locale="ru",
            target_locale="en",
        )
        == []
    )


# ---------------------------------------------------------------------
# Correct prose, which must stay quiet
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "translation", "target"),
    [
        # The same lesson's city, called by its own name. One letter and
        # one grammatical number away from the row above that flags.
        (
            "Урок 9. Евангелие в Европе: Филиппы, Афины, Коринф (Деяния 16–18)",
            "Lektion 9. Das Evangelium in Europa: Philippi, Athen, Korinth (Apostelgeschichte 16–18)",
            "de",
        ),
        (
            "Урок 9. Евангелие в Европе: Филиппы, Афины, Коринф (Деяния 16–18)",
            "Урок 9. Євангеліє в Європі: Филипи, Афіни, Коринф (Дії 16–18)",
            "uk",
        ),
        # The evangelist, correctly, in both other languages.
        (
            "Урок 5. Филипп: Евангелие пересекает границы (Деяния 8)",
            "Lesson 5. Philip: The Gospel Crosses Borders (Acts 8)",
            "en",
        ),
        (
            "Урок 5. Филипп: Евангелие пересекает границы (Деяния 8)",
            "Урок 5. Филип: Євангеліє перетинає кордони (Дії 8)",
            "uk",
        ),
        # Three spellings of one man is what transliteration is for.
        ("Пётр и Иоанн идут в Храм на час молитвы.", "Petrus und Johannes gehen zur Gebetsstunde in den Tempel.", "de"),
        ("Пётр и Иоанн идут в Храм на час молитвы.", "Петро та Іван ідуть до Храму на годину молитви.", "uk"),
        # Luther addresses the apostle as *Saul* and names him *Saulus*.
        # Both are him, and the king of the same English name is not.
        ("«Савл, Савл! что ты гонишь Меня?»", "„Saul, Saul, warum verfolgst du mich?“", "de"),
        # Genesis is «Бытие» in Russian and *1. Mose* in German. A book
        # cited by number is a citation, not Moses being named.
        (
            "Прямое противопоставление вавилонскому смешению языков (Бытие 11).",
            "Ein direkter Gegensatz zur babylonischen Sprachverwirrung (1. Mose 11).",
            "de",
        ),
        (
            "Чтение Писания: Деяния 10–12; Левит 11 (кратко); Исаия 49:6.",
            "Schriftlesung: Apostelgeschichte 10–12; 3. Mose 11 (kurz); Jes. 49,6.",
            "de",
        ),
        # «Иудеи» is "Jews" here and not a case of Judea, and the English
        # quotation of Acts 21:28 carries more of the verse than the
        # Russian one does.
        (
            "Иудеи из Асии, узнав Павла в Храме, поднимают мятеж: «Этот человек всех повсюду учит против народа».",
            'Jews from Asia, recognizing Paul in the Temple, stir up a riot: "Men of Israel, help! '
            'This is the man who is teaching everywhere against our people."',
            "en",
        ),
        # Both names kept, which is what the Russian says.
        (
            "Воскрешением Тавифы (арамейское имя; по-гречески Серна) в Иоппии.",
            "The raising of Tabitha (an Aramaic name; in Greek, Dorcas) in Joppa.",
            "en",
        ),
        # Rome is three letters in German and has no row at all; a
        # translation that renders it perfectly must not be accused of
        # losing it.
        (
            "Кораблекрушение, прибытие в Рим, открытый финал книги Деяний.",
            "Schiffbruch, Ankunft in Rom, das offene Ende der Apostelgeschichte.",
            "de",
        ),
    ],
)
def test_correct_prose_is_never_called_a_substitution(source: str, translation: str, target: str) -> None:
    assert substituted_names(source, translation, source_locale="ru", target_locale=target) == []


def test_a_translation_into_the_language_it_was_written_in_is_not_compared() -> None:
    assert substituted_names("Крисп", "Крисп", source_locale="ru", target_locale="ru") == []


# ---------------------------------------------------------------------
# How the pipeline sees it
# ---------------------------------------------------------------------


def test_a_swapped_name_withholds_the_row() -> None:
    """Blocking, and the same reasoning as a lost number: a reader is
    being told something false, and a gap teaches less badly than that."""
    issues = validate_translation(
        source="Сам начальник синагоги Крисп уверовывает, и весь дом его вместе с ним.",
        translated="Der Synagogenvorsteher Sosthenes selbst kommt zum Glauben, samt seinem ganzen Haus.",
        source_locale="ru",
        target_locale="de",
    )
    swapped = [issue for issue in issues if issue.code == "proper_name_substituted"]
    assert len(swapped) == 1
    assert swapped[0].blocking is True
    assert swapped[0].advisory is False
    assert "Крисп" in swapped[0].detail
    assert "Sosthenes" in swapped[0].detail


def test_a_correct_translation_carries_no_name_issue() -> None:
    issues = validate_translation(
        source="Пётр и Иоанн идут в Храм на час молитвы.",
        translated="Petrus und Johannes gehen zur Gebetsstunde in den Tempel.",
        source_locale="ru",
        target_locale="de",
    )
    assert [issue.code for issue in issues if issue.code == "proper_name_substituted"] == []


def test_a_language_the_table_does_not_carry_is_refused_not_ignored() -> None:
    """The cells are positional, so a table one column short does not
    check that language badly — it stops having an opinion about it, and
    silence reads exactly like a pass. Same guard, same reasoning, as
    ``glossary._verify_every_term_is_written_in_every_language``."""
    from app.schemas.locale import LanguageNotInTable
    from app.services.translation.proper_names import _verify_every_name_is_written_in_every_language

    with pytest.raises(LanguageNotInTable, match="proper-name table"):
        _verify_every_name_is_written_in_every_language(("ru", "en", "de", "uk", "pl"))
