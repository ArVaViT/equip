# ruff: noqa: RUF001
# «Стефан» beside «Степан» and «Лісій» beside «Лисий» is the subject
# matter, not a typo.
"""The names the live catalogue printed, and the ones it printed correctly.

Every string below is quoted from production. The first half is what a
native Ukrainian editor found: the first martyr examined under a name
the lessons never use, «Степан» — the ordinary Ukrainian given name
Stepan — and the tribune Claudius Lysias called by the Ukrainian for
*bald* and by a word that is a name in no language at all.

The second half is the half that decides whether this check survives
contact with a person. Eight Ukrainian rows print «Стефан» correctly,
fourteen German rows write *Stephans Rede* — which is correct German,
the feast being der Stephanstag — and one Ukrainian quiz option prints
«Клавдій Лісій». All of them must stay quiet. A check that names
correct prose gets switched off, and then it catches nothing at all.
"""

from __future__ import annotations

import pytest

from app.schemas.locale import LOCALE_CODES, LanguageNotInTable
from app.services.translation.person_names import foreign_person_names
from app.services.translation.proper_names import named_in, not_printed_in, printed_in, substituted_names
from app.services.translation.validation import validate_translation

# ---------------------------------------------------------------------
# The two tables underneath, and the line between them
# ---------------------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALE_CODES)
def test_every_language_prints_a_form_for_the_people_it_is_refused_a_form_for(locale: str) -> None:
    """A spelling can only be called wrong by a language that has a right
    one to offer instead — otherwise the sentence a reviewer reads names
    a defect and no remedy."""
    for form, key in not_printed_in(locale):
        printed = printed_in(key, locale)
        assert printed is not None, f"{locale} has no printed form for {key}"
        assert printed.casefold() != form.casefold(), f"{form!r} is listed as not printed and is what {locale} prints"


def test_the_misspelling_still_reads_as_the_man_it_misspells() -> None:
    """The reason «Степан» is moved rather than deleted.

    If it stopped resolving to Stephen, «Стефан» → «Степана» would read
    as a name vanishing and an unknown one arriving — which is the shape
    ``substituted_names`` reports, and it would be a false accusation of
    putting a different person in the sentence.
    """
    assert named_in("Степана", "uk") == frozenset({"stephen"})
    assert named_in("Степанові", "uk") == frozenset({"stephen"})
    assert (
        substituted_names(
            "Кто одобрил казнь Стефана?",
            "Хто схвалив страту Степана?",
            source_locale="ru",
            target_locale="uk",
        )
        == []
    )


def test_the_check_that_reports_a_swapped_name_still_reports_one() -> None:
    """The live row that check was measured on, unmoved by this work:
    «Тавифа (по-гречески Серна)» answered with «Дорки» leaves a sentence
    that contradicts itself."""
    assert substituted_names(
        "воскрешением Тавифы (арамейское имя; по-гречески Серна) в Иоппии",
        "воскрешенням Дорки (арамейське ім’я; грецькою Серна) в Йопії",
        source_locale="ru",
        target_locale="uk",
    ) == [("Тавифы", "Дорки")]


# ---------------------------------------------------------------------
# What the catalogue printed, and had to be caught
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "translated"),
    [
        (
            "На каком основном тезисе построена речь Стефана в Деян. 7?",
            "На якій основній тезі побудована промова Степана в Діян. 7?",
        ),
        (
            "Кто из будущих апостолов присутствует при смерти Стефана и одобряет её?",
            "Хто з майбутніх апостолів присутній при смерті Степана і схвалює її?",
        ),
        (
            "Как книга Деяний объясняет распространение Евангелия после смерти Стефана (8:4)?",
            "Як книга Дій пояснює поширення Євангелія після смерті Степана (8:4)?",
        ),
    ],
)
def test_the_ukrainian_quiz_examines_a_student_on_a_name_the_lesson_never_used(source: str, translated: str) -> None:
    """Three questions, each of them live in two courses."""
    assert foreign_person_names(source, translated, source_locale="ru", target_locale="uk") == [("Степана", "Стефан")]


def test_the_daily_challenge_asks_and_then_explains_using_the_wrong_name() -> None:
    """The question and its explanation, both live, both «Степана»."""
    assert foreign_person_names(
        "Согласно Деяниям 8:1, кто одобрил казнь Стефана?",
        "Згідно з Діяннями 8:1, хто схвалив страту Степана?",
        source_locale="ru",
        target_locale="uk",
    ) == [("Степана", "Стефан")]
    assert foreign_person_names(
        "В Деяниях 8:1 сказано: «Савл же одобрял убиение его». Это указывает на одобрение Савлом казни Стефана.",
        "Дії 8:1 зазначає: «А Савло схвалював його смерть». Це вказує на схвалення Савлом страти Степана.",
        source_locale="ru",
        target_locale="uk",
    ) == [("Степана", "Стефан")]


def test_the_tribune_called_by_the_ukrainian_word_for_bald() -> None:
    """One lesson names him three ways: «Клавдій Лісій» in one
    paragraph and bare «Лисий» two paragraphs later, which a Ukrainian
    reader meets as an adjective."""
    assert foreign_person_names(
        "Лисий ночью отправляет Павла под сильной охраной в Кесарию.",
        "Лисий вночі відправляє Павла під сильним конвоєм до Кесарії.",
        source_locale="ru",
        target_locale="uk",
    ) == [("Лисий", "Лісій")]


def test_the_tribune_called_by_a_word_that_is_a_name_in_no_language() -> None:
    """From the course's own list of names and terms — the page a
    student revises from."""
    assert foreign_person_names(
        "<li><strong>Клавдий Лисий</strong> — тысяченачальник в Иерусалиме, спасает Павла от толпы.</li>",
        "<li><strong>Клавдій Лій</strong> — тисячоначальник в Єрусалимі, рятує Павла від натовпу.</li>",
        source_locale="ru",
        target_locale="uk",
    ) == [("Лій", "Лісій")]


# ---------------------------------------------------------------------
# The half that decides whether the check survives a person reading it
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "translated"),
    [
        (
            "Урок 4. Стефан: первый мученик и его речь (Деяния 6–7)",
            "Урок 4. Стефан: перший мученик та його промова (Дії 6–7)",
        ),
        (
            "Служение Стефана и его мученичество, Филипп в Самарии и с эфиопским евнухом.",
            "Служіння Стефана та його мученицька смерть, Филип у Самарії та з ефіопським скопцем.",
        ),
        (
            "Согласно Деяниям 7, кто непосредственно задал Стефану вопросы относительно обвинений против него?",
            "Згідно з Діяннями 7, хто безпосередньо поставив Стефану запитання щодо звинувачень проти нього?",
        ),
        (
            "<li>пересказывать основные ходы речи Стефана и её богословский центр;</li>",
            "<li>переказувати основні тези промови Стефана та її богословський центр;</li>",
        ),
    ],
)
def test_the_ukrainian_rows_that_print_the_martyrs_name_correctly_are_left_alone(source: str, translated: str) -> None:
    assert foreign_person_names(source, translated, source_locale="ru", target_locale="uk") == []


@pytest.mark.parametrize(
    ("source", "translated"),
    [
        (
            "Проверка знаний по материалам Стефана, Филиппа, обращения Савла (Деян. 6–12).",
            "Prüfung des Wissens über Stephans Dienst, Philippus und die Bekehrung des Saulus (Apg. 6–12).",
        ),
        (
            "Как книга Деяний объясняет распространение Евангелия после смерти Стефана (8:4)?",
            "Wie erklärt die Apostelgeschichte die Verbreitung des Evangeliums nach dem Tod Stephans (8,4)?",
        ),
        (
            "На каком основном тезисе построена речь Стефана в Деян. 7?",
            "Auf welchem Hauptargument basiert Stephans Rede in Apostelgeschichte 7?",
        ),
    ],
)
def test_german_prose_that_calls_the_martyr_stephan_is_not_a_defect(source: str, translated: str) -> None:
    """Fourteen live German rows write it this way, and German prints
    that name for that man: the feast is der Stephanstag and the
    cathedral in Vienna is der Stephansdom. A row for it in the
    not-printed table would flag every one of them."""
    assert foreign_person_names(source, translated, source_locale="ru", target_locale="de") == []


def test_the_spelling_ukrainian_does_print_for_the_tribune_passes() -> None:
    """The same lesson, and the quiz option that answers it."""
    assert (
        foreign_person_names(
            "Римский тысяченачальник Клавдий Лисий вырывает Павла из рук толпы.",
            "Римський тисячоначальник Клавдій Лісій вириває Павла з рук натовпу.",
            source_locale="ru",
            target_locale="uk",
        )
        == []
    )
    assert foreign_person_names("Клавдий Лисий", "Клавдій Лісій", source_locale="ru", target_locale="uk") == []


def test_nothing_is_reported_unless_the_source_named_the_same_person() -> None:
    """The anchor, and the whole reason an ordinary Ukrainian adjective
    may be listed at all. Without a source that names the man, «Лисий»
    is *bald*, «Лій» is tallow and «Степан» is somebody's uncle."""
    for translated in ("Степан прийшов додому.", "Лисий чоловік стояв біля дверей.", "Лій горів у лампі."):
        assert (
            foreign_person_names(
                "Урок о ранней церкви и её служении.",
                translated,
                source_locale="ru",
                target_locale="uk",
            )
            == []
        )


def test_a_language_with_nothing_written_down_says_nothing() -> None:
    assert (
        foreign_person_names(
            "Кто одобрил казнь Стефана?",
            "Who approved the execution of Stephen?",
            source_locale="ru",
            target_locale="en",
        )
        == []
    )


def test_a_language_this_table_cannot_read_is_refused_rather_than_passed() -> None:
    with pytest.raises(LanguageNotInTable):
        foreign_person_names(
            "Кто одобрил казнь Стефана?",
            "Хто схвалив страту Степана?",
            source_locale="ru",
            target_locale="fr",
        )


def test_a_row_translated_into_its_own_language_is_not_a_translation() -> None:
    assert foreign_person_names("Степана", "Степана", source_locale="uk", target_locale="uk") == []


# ---------------------------------------------------------------------
# What the validator does with it
# ---------------------------------------------------------------------


def test_the_validator_withholds_the_page_and_names_both_spellings() -> None:
    """Blocking, where the book-name check is not. A student who reads
    «Діїв. 1:8» still finds Acts 1:8; a student examined on «страту
    Степана» has no way back to «Стефан», and every one of these rows is
    an assessment item."""
    issues = validate_translation(
        source="Согласно Деяниям 8:1, кто одобрил казнь Стефана?",
        translated="Згідно з Діяннями 8:1, хто схвалив страту Степана?",
        source_locale="ru",
        target_locale="uk",
    )
    named = [issue for issue in issues if issue.code == "person_name_not_printed_here"]
    assert len(named) == 1
    assert named[0].blocking is True
    assert named[0].advisory is False
    assert "Степана" in named[0].detail
    assert "Стефан" in named[0].detail


def test_a_correct_translation_of_the_same_question_raises_nothing() -> None:
    issues = validate_translation(
        source="Согласно Деяниям 8:1, кто одобрил казнь Стефана?",
        translated="Згідно з Діяннями 8:1, хто схвалив страту Стефана?",
        source_locale="ru",
        target_locale="uk",
    )
    assert [issue.code for issue in issues if issue.code == "person_name_not_printed_here"] == []
