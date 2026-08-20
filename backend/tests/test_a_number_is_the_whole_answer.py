"""A quiz option that is a number has nothing else to be right about.

`validation.py` checks digits with some care — a chapter-and-verse
reference must survive, a year must survive. It had nothing to say about
a number written as a word, and production served this, marked ok: the
Russian option «Двенадцать» came back in German as *Fünf*. Twelve became
five, in a question where the number is the entire answer. Every
structural check passed, because nothing was malformed, and the reviewer
passed it too, because "Fünf" is a perfectly good German word.

The check that catches it is narrow on purpose, and the width was
measured rather than chosen. Searching for numerals inside prose was
tried against all 8,492 short production strings and produced 61 hits,
every one false — «двадцать» contains «два», «семье» contains «семь»,
German "Sechzig" does not contain "sechs". Restricted to strings that
ARE a number, the same corpus of 9,083 rows produces exactly one hit:
the real one.
"""

from __future__ import annotations

import pytest

from app.services.translation.numerals import numbers_lost
from app.services.translation.validation import validate_translation


class TestTheNumberThatChanged:
    def test_twelve_becoming_five_is_caught(self) -> None:
        assert numbers_lost("Двенадцать", "Fünf", source_locale="ru", target_locale="de") == [("двенадцать", "zwölf")]

    def test_the_right_number_passes(self) -> None:
        assert numbers_lost("Двенадцать", "Zwölf", source_locale="ru", target_locale="de") == []

    def test_a_digit_is_an_acceptable_rendering(self) -> None:
        # "12" says what "twelve" says, and reads fine as a short answer.
        assert numbers_lost("Двенадцать", "12", source_locale="ru", target_locale="de") == []

    def test_it_blocks_because_a_wrong_number_is_a_wrong_answer(self) -> None:
        issues = validate_translation(
            source="Двенадцать",
            translated="Fünf",
            source_locale="ru",
            target_locale="de",
            content_kind="quiz_option",
        )
        assert [i.code for i in issues] == ["numeral_lost"]
        assert issues[0].blocking is True


class TestItDoesNotFlagCorrectProse:
    @pytest.mark.parametrize(
        ("source", "translation", "target"),
        [
            # «двадцать» contains «два»; the numeral is not the string.
            ("Урок 13. Найти место за двадцать секунд", "Lektion 13. Eine Stelle in zwanzig Sekunden", "de"),
            # «семье» — a family, not a seven.
            ("Письмо семье Еноха", "Лист родині Еноха", "uk"),
            # German compounds: "Sechzig" does not contain "sechs".
            ("Шестьдесят", "Sechzig", "de"),
            ("Сорок", "Vierzig", "de"),
            # A numeral rendered correctly, with punctuation around it.
            ("Двенадцать.", "Zwölf.", "de"),
        ],
    )
    def test_these_are_left_alone(self, source: str, translation: str, target: str) -> None:
        assert numbers_lost(source, translation, source_locale="ru", target_locale=target) == []

    def test_one_is_never_counted(self) -> None:
        # An article, a pronoun and an intensifier far more often than a
        # count. Flagging it would flag half the catalogue.
        assert numbers_lost("Один", "Ein", source_locale="ru", target_locale="de") == []

    def test_prose_is_out_of_scope_entirely(self) -> None:
        assert (
            numbers_lost(
                "Ученики собирались по домам в двенадцати городах каждую неделю",
                "In den Städten versammelten sich die Brüder wöchentlich",
                source_locale="ru",
                target_locale="de",
            )
            == []
        )
