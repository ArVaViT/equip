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

The table used to stop at seventy, which was a fact about the three
biblical courses that existed rather than about the check. It now goes
to a thousand. The widening was measured the same way, against 11,149
live translation pairs: it reads nine more rows as a number (ninety, a
hundred, "One hundred", "A hundred") and flags none of them, because all
nine are translated correctly.

The tests below pin both halves — what the check now covers, and what it
still deliberately does not. The second half matters as much as the
first: allowing the number a tail, so that «Двенадцать процентов» would
be checked, was measured against the same corpus and produced 12 hits,
all 12 of them correct translations. This check blocks, so a false hit
is a correct page not served. Those tests say "passes" on purpose.
"""

from __future__ import annotations

import pytest

from app.services.translation.numerals import _NUMERALS, numbers_lost
from app.services.translation.validation import validate_translation

LANGUAGES = ("ru", "en", "de", "uk")


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


class TestTheTableReachesPastSeventy:
    """Eighty, ninety, a hundred and a thousand are numbers too.

    No biblical course counts with them, which is why the table stopped
    where it did. A course on arithmetic, money or physics does, and
    those are coming.
    """

    @pytest.mark.parametrize(
        ("source", "right", "wrong"),
        [
            ("Восемьдесят", "Achtzig", "Fünf"),
            ("Девяносто", "Neunzig", "Fünf"),
            ("Сто", "Hundert", "Fünf"),
            ("Тысяча", "Tausend", "Fünf"),
        ],
    )
    def test_the_new_values_are_checked_in_both_directions(self, source: str, right: str, wrong: str) -> None:
        assert numbers_lost(source, right, source_locale="ru", target_locale="de") == []
        assert numbers_lost(source, wrong, source_locale="ru", target_locale="de") != []

    def test_a_hundred_no_longer_needs_the_word_stoit_to_be_feared(self) -> None:
        """The reason «сто» was excluded does not survive the whole-string rule.

        It was excluded because three letters plus a permitted suffix
        matches «стоит», and a check that flags "es lohnt sich zu lesen"
        for losing a hundred is a check nobody keeps. That objection
        belonged to the version of the check that searched inside prose.
        Re-measured on the live catalogue: a substring rule would look at
        306 Russian rows and swallow «стоит» 153 times; the whole-string
        rule looks at 2, and both of them are the number.
        """
        assert numbers_lost("Стоит прочитать", "Es lohnt sich zu lesen", source_locale="ru", target_locale="de") == []
        assert numbers_lost("Сто", "Es lohnt sich zu lesen", source_locale="ru", target_locale="de") == [
            ("сто", "hundert")
        ]


class TestEveryRowIsCompleteInEveryLanguage:
    """An incomplete row is worse than no row.

    A row missing its German column would silently stop checking German
    for that number while looking, in the table, exactly like coverage.
    """

    def test_no_column_is_empty(self) -> None:
        for row in _NUMERALS:
            for language in LANGUAGES:
                assert getattr(row, language).strip(), f"{row.value} has no {language}"

    def test_the_values_are_the_ones_the_table_claims(self) -> None:
        values = [row.value for row in _NUMERALS]
        assert values == sorted(values), "the table reads as a list; keep it in order"
        assert set(values) >= set(range(2, 21)) | {30, 40, 50, 60, 70, 80, 90, 100, 1000}

    @pytest.mark.parametrize("source_language", LANGUAGES)
    @pytest.mark.parametrize("target_language", LANGUAGES)
    def test_every_row_survives_a_round_trip_between_every_pair(
        self, source_language: str, target_language: str
    ) -> None:
        if source_language == target_language:
            return
        for row in _NUMERALS:
            source = getattr(row, source_language)
            right = getattr(row, target_language)
            assert numbers_lost(source, right, source_locale=source_language, target_locale=target_language) == [], (
                f"{row.value}: {source_language} {source!r} -> {target_language} {right!r} was read as a loss"
            )

    @pytest.mark.parametrize("source_language", LANGUAGES)
    def test_a_number_replaced_by_another_number_is_caught_in_every_language(self, source_language: str) -> None:
        # Every row against a translation that says five instead. The
        # five row itself is skipped, since there it would be right.
        for row in _NUMERALS:
            if row.value == 5:
                continue
            source = getattr(row, source_language)
            target_language = "de" if source_language != "de" else "ru"
            wrong = "Fünf" if target_language == "de" else "Пять"
            assert numbers_lost(source, wrong, source_locale=source_language, target_locale=target_language), (
                f"{row.value} in {source_language} was not noticed going missing"
            )


class TestASuffixMayChangeTheFormNotTheNumber:
    """The matcher allows a short suffix because these languages decline.

    That is for «двенадцати» being twelve. It is not for one number
    standing in for another, and in German it would be: *acht* plus
    three letters is *achtzig*, which is not eight, it is eighty. Adding
    the eighty and ninety rows is what made the check able to tell.
    """

    @pytest.mark.parametrize(
        ("source", "translation", "source_locale", "target_locale"),
        [
            ("Восемь", "Achtzig", "ru", "de"),
            ("Девять", "Neunzig", "ru", "de"),
            ("Семь", "Seventy", "ru", "en"),
            ("Семь", "Сімнадцять", "ru", "uk"),
            ("Четыре", "Vierzig", "ru", "de"),
        ],
    )
    def test_a_bigger_number_does_not_stand_in_for_a_smaller_one(
        self, source: str, translation: str, source_locale: str, target_locale: str
    ) -> None:
        assert numbers_lost(source, translation, source_locale=source_locale, target_locale=target_locale) != []

    def test_the_right_number_further_along_the_sentence_still_counts(self) -> None:
        # The first «три» here is inside «тридцять» and is not a three.
        # The second one is, and the answer is not wrong for having both.
        assert numbers_lost("Три", "Тридцять три", source_locale="ru", target_locale="uk") == []


class TestGermanWritesAHundredAsPartOfTheWord:
    """*Einhundert* is one word, and it is a hundred.

    A word-boundary search cannot see the hundred in it, so for these
    two words the boundary is dropped. Being generous on the translation
    side can only make the check miss something; being strict there
    makes it flag a correct answer, which is the failure that gets a
    check switched off. Production has "One hundred" → *Einhundert* in
    the daily challenge today.
    """

    @pytest.mark.parametrize(
        ("source", "translation", "source_locale"),
        [
            ("One hundred", "Einhundert", "en"),
            ("A hundred", "Hundert", "en"),
            ("Сто", "Einhundert", "ru"),
            ("Тысяча", "Eintausend", "ru"),
        ],
    )
    def test_the_glued_form_is_the_number(self, source: str, translation: str, source_locale: str) -> None:
        assert numbers_lost(source, translation, source_locale=source_locale, target_locale="de") == []

    def test_a_leading_word_meaning_one_does_not_change_the_number(self) -> None:
        # "One hundred" is a hundred; every word allowed in front
        # multiplies by one, which is why "zweihundert" is not allowed.
        assert numbers_lost("One hundred", "Fünf", source_locale="en", target_locale="de") == [("hundred", "hundert")]
        assert numbers_lost("Одна тысяча", "Fünf", source_locale="ru", target_locale="de") == [("тысяча", "tausend")]


class TestADigitMayCarryAGroupSeparator:
    """A thousand written as "1.000" is still a thousand.

    German groups digits with a full stop, Russian with a space. The
    digit rendering was already accepted; it now survives being
    punctuated.
    """

    @pytest.mark.parametrize("translation", ["1000", "1.000", "1 000"])
    def test_a_thousand_in_digits_passes(self, translation: str) -> None:
        assert numbers_lost("Тысяча", translation, source_locale="ru", target_locale="de") == []

    def test_a_different_number_in_digits_does_not(self) -> None:
        assert numbers_lost("Тысяча", "1.001", source_locale="ru", target_locale="de") != []


class TestWhatIsDeliberatelyNotCovered:
    """These pass, and they are wrong, and that is the decision.

    Every one of them was measured on the live catalogue before being
    left alone. The relaxation that would catch the first three produces
    12 hits there, and all 12 are correct translations: «Шесть утра» →
    «Шоста ранку» (Ukrainian says six o'clock with an ordinal), "Two
    hundred" → «Двісті» (which contains no «два»), «Двадцать одно» →
    *Einundzwanzig*, "Seventy-two" → *Zweiundsiebzig*. A blocking check
    that flags correct answers is a check somebody turns off.

    If any of these is ever to be covered, it needs morphology — knowing
    that «шоста» is a form of six and that *zweiundsiebzig* contains
    seventy — not a wider regular expression.
    """

    def test_a_number_with_a_tail_is_not_checked(self) -> None:
        assert numbers_lost("Двенадцать процентов", "Fünf Prozent", source_locale="ru", target_locale="de") == []

    def test_a_compound_is_not_checked(self) -> None:
        assert numbers_lost("Сорок два", "Fünfzig", source_locale="ru", target_locale="de") == []
        assert numbers_lost("Seventy-two", "Fünfzig", source_locale="en", target_locale="de") == []

    def test_a_fraction_is_not_checked(self) -> None:
        assert numbers_lost("Две трети", "Ein Drittel", source_locale="ru", target_locale="de") == []

    def test_one_is_not_checked(self) -> None:
        assert numbers_lost("Один", "Zwei", source_locale="ru", target_locale="de") == []

    def test_zero_is_not_checked(self) -> None:
        """Two Russian spellings, «ноль» and «нуль», and an answer of
        zero is legitimately rendered "keine", "none", «жодного». The
        check would have to know that a word meaning *none* is the
        number."""
        assert numbers_lost("Ноль", "Fünf", source_locale="ru", target_locale="de") == []

    def test_an_ordinal_is_not_checked(self) -> None:
        # «Двенадцатый» is twelfth, not twelve. The suffix rule reads it
        # as twelve on the translation side, which is deliberate
        # generosity there, but the source side never starts from it.
        assert numbers_lost("Двенадцатый", "Fünfter", source_locale="ru", target_locale="de") == []


class TestUkrainianApostrophes:
    """«п'ять» arrives spelled two ways and is one word.

    The typewriter apostrophe these tables were written with, and the
    typographic one `typography.py` normalises to. Comparing them as
    different words is how a check goes quietly blind.
    """

    @pytest.mark.parametrize("source", ["П'ять", "П\u2019ять"])
    def test_both_spellings_are_the_number(self, source: str) -> None:
        assert numbers_lost(source, "Fünf", source_locale="uk", target_locale="de") == []
        assert numbers_lost(source, "Sechs", source_locale="uk", target_locale="de") == [("п'ять", "fünf")]

    @pytest.mark.parametrize("translation", ["Дев'ять", "Дев\u2019ять"])
    def test_both_spellings_are_found_in_a_translation(self, translation: str) -> None:
        assert numbers_lost("Девять", translation, source_locale="ru", target_locale="uk") == []
