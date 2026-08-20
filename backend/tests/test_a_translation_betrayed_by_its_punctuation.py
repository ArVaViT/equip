"""A translation reads as machine-made long before its meaning is wrong.

The reader of a German lesson does not check the vocabulary. They see
``Apg. 8:26`` — a Russian colon in a German citation — three lines above
``Apg 8,26``, and the page stops sounding like it was written for them.
The production count on 2026-08-19: 94 German references still pointed
with a colon against 274 with the comma; 662 straight English double
quotes against 49 curly, six of those six strings unbalanced; and the
Ukrainian apostrophe spelled both ways in the same words, 58 typographic
against 163 typewriter, where the Russian source has no apostrophes at
all and 388 unbroken ``«»`` pairs.

A second reading, of generation 8 on 2026-08-20 — 2,452 rows, de 819 /
en 815 / uk 816 — found what the first pass did not do. The book is
named three ways (``Apostelgeschichte 1,8`` ×48, ``Apg. 1,8`` ×40,
``Apg 1,8`` ×44, and 13 of 46 German lesson blocks mix at least two of
them); Russian abbreviations sit inside German tables (``Ин. 3:16``,
``1 Кор. 13``); English chapter titles are Title Case 35 times and
sentence case 11, inconsistently inside every course; and German carries
58 em dashes it has no use for against 411 correct en dashes, with 35
typewriter apostrophes in ``Paulus'`` against 3 correct ``Stephanus’``.

These are rules, not preferences, so they are tested as rules. Each
class below pins one of them, plus the properties that make the pass
safe to run over stored content: it is idempotent, it cannot reach
inside markup, it never deletes whitespace, and the half of it that is
one character for one still cannot change a string's length.

The class named for what must not change is the one that matters most.
Everything this module does is an edit nobody will re-read, so the
cases that must come out byte-identical are worth more than the cases
that must change.
"""

from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

import httpx

from app.schemas.locale import LOCALE_CODES
from app.services.translation.gemini import GeminiTranslationProvider
from app.services.translation.protocol import TranslationRequest
from app.services.translation.typography import (
    _scan_markup,  # the module's own idea of a tag — see ``_tags`` below
    normalize_characters,
    normalize_typography,
)

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode
    from app.services.translation.protocol import ContentKind


# Shapes taken from what the corpus actually holds: TipTap HTML with
# callouts and embedded media, Daily Challenge explanations with no
# markup at all, quiz options that quote a verse with the reference in
# brackets, and the two tables that kept their Russian abbreviations.
CORPUS_SHAPES: tuple[tuple[LocaleCode, ContentKind, str], ...] = (
    ("de", "html", '<p class="callout callout-info">Lies Apg. 8:26-40 und Apg 10:1-23; 11:3.</p>'),
    ("de", "html", "<p>Philippus‘ Weg beginnt in Apg 8,26.</p>"),
    ("de", "html", '<p>Er sagte «Ich glaube» und dann "Amen".</p>'),
    ("de", "html", '<figure><img src="https://cdn.equip.test/a.png?a=1&amp;b=2" alt="Apg 8:26"></figure>'),
    ("de", "html", "<table><tr><td>Ин. 3:16</td><td>1 Кор. 13</td></tr></table>"),
    ("de", "html", "<p>Paulus' Reise — etwa 3000 Menschen — endet in Rom.</p>"),
    ("de", "title", "Lektion 5. Apostelgeschichte 1,8 und der Auftrag"),
    ("en", "html", "<p>“Peter’s answer” is not Paul's answer.</p>"),
    ("en", "html", "<p>Read Acts 8:26 before 18:30.</p>"),
    ("en", "html", "<h2>check yourself</h2><p>the map that fits in your head</p>"),
    ("en", "title", "Lesson 5. Currents and ministries of the first century"),
    ("en", "plain", "The road—and it was a long road—ran east."),
    ("uk", "html", "<p>Це п'ять причин, і ім'я його відоме.</p>"),
    ("uk", "html", '<p>Він сказав "мир вам".</p>'),
    ("ru", "html", '<p>Он сказал "мир вам" в 18:30.</p>'),
    ("ru", "html", "<p>«Уже правильно», — сказал он.</p>"),
)


def _tags(html: str) -> list[str]:
    """Every tag, verbatim, as the pass itself delimits them.

    Read with the module's own scanner rather than a regex of our own:
    a test that disagrees with the code about where a tag starts proves
    nothing about whether the code stayed out of it.
    """
    _, found = _scan_markup(html)
    return [html[start:end] for _, _, start, end in found]


class TestGermanPointsAReferenceItsOwnWay:
    """Comma between chapter and verse, full stop between verses, en dash
    for a range. The source's colon is not a German variant."""

    def test_a_colon_between_chapter_and_verse_becomes_a_comma(self) -> None:
        assert normalize_typography("Lies Apg. 8:26 heute.", "de") == "Lies Apg. 8,26 heute."

    def test_a_hyphen_range_becomes_an_en_dash(self) -> None:
        assert normalize_typography("Apg. 8,26-40", "de") == "Apg. 8,26–40"

    def test_a_second_verse_of_the_same_chapter_is_listed_with_a_full_stop(self) -> None:
        # The Russian source writes 8:26,30 for two verses. Carried over
        # literally and then half-fixed, that reads 8,26,30 — three
        # numbers and no way to tell which is the chapter.
        assert normalize_typography("Apg. 8:26,30", "de") == "Apg. 8,26.30"

    def test_a_range_that_crosses_a_chapter_keeps_both_commas(self) -> None:
        assert normalize_typography("Apg. 8:26-9:3", "de") == "Apg. 8,26–9,3"

    def test_a_second_passage_after_a_semicolon_is_pointed_too(self) -> None:
        assert normalize_typography("Apg. 10:1-23; 11:3", "de") == "Apg. 10,1–23; 11,3"

    def test_a_chapter_with_no_verse_keeps_its_number_alone(self) -> None:
        assert normalize_typography("Apostelgeschichte 8 erzählt davon.", "de") == "Apostelgeschichte 8 erzählt davon."

    def test_an_already_german_reference_is_untouched(self) -> None:
        assert normalize_typography("Apg. 8,26.30–32", "de") == "Apg. 8,26.30–32"

    def test_a_number_too_large_to_be_a_verse_disqualifies_the_match(self) -> None:
        # And it disqualifies the *name* with it: if the numbers are not
        # a reference, the word in front of them is not established as a
        # book, so its spelling is left alone too.
        assert normalize_typography("Apg 8:2026", "de") == "Apg 8:2026"

    def test_a_weekday_that_reads_like_a_book_is_not_one(self) -> None:
        # ``Mi.`` is Micah in a reference and Mittwoch in a timetable.
        # One ambiguous abbreviation is not worth a repointed time.
        assert normalize_typography("Mi. 8:30 Uhr im Saal", "de") == "Mi. 8:30 Uhr im Saal"


class TestGermanNamesABookOneWay:
    """One form per book, and the form is the abbreviation with the
    period — what ``display_book_name`` already prints beside every
    canonically quoted verse, and what a German Bible prints in its own
    cross-references."""

    def test_the_spelled_out_name_becomes_the_abbreviation(self) -> None:
        assert normalize_typography("Apostelgeschichte 1,8", "de") == "Apg. 1,8"

    def test_the_abbreviation_without_its_period_gets_one(self) -> None:
        assert normalize_typography("Apg 1,8", "de") == "Apg. 1,8"

    def test_the_form_that_is_already_right_is_a_fixed_point(self) -> None:
        assert normalize_typography("Apg. 1,8", "de") == "Apg. 1,8"

    def test_all_three_forms_in_one_paragraph_end_up_the_same(self) -> None:
        # One production block (d26d485d) uses all three.
        text = "Apostelgeschichte 1,8 und Apg. 1,8 und Apg 1,8"
        assert normalize_typography(text, "de") == "Apg. 1,8 und Apg. 1,8 und Apg. 1,8"

    def test_a_numbered_book_keeps_its_number(self) -> None:
        assert normalize_typography("1. Korinther 13,4", "de") == "1. Kor. 13,4"

    def test_a_numbered_book_is_found_behind_other_words(self) -> None:
        assert normalize_typography("Siehe auch 1. Korinther 13,4 dazu.", "de") == "Siehe auch 1. Kor. 13,4 dazu."

    def test_the_pentateuch_is_numbered_the_way_luther_numbers_it(self) -> None:
        # ``display_book_name`` prints ``1. Mose``, because that is what
        # the German edition the platform quotes from prints.
        assert normalize_typography("Genesis 1,1", "de") == "1. Mose 1,1"

    def test_prose_that_spells_the_book_out_is_not_a_citation(self) -> None:
        # No chapter, no verse, no rewrite. This is the sentence the
        # whole "argue from the numbers" design exists to protect.
        text = "Die Apostelgeschichte erzählt von der frühen Gemeinde."
        assert normalize_typography(text, "de") == text

    def test_a_chapter_without_a_verse_is_not_evidence_enough(self) -> None:
        # ``Apostelgeschichte 8 erzählt davon`` is a sentence with the
        # book as its subject as readily as it is a citation, and the
        # counts the editor took are all chapter-and-verse.
        text = "Apostelgeschichte 8 erzählt davon."
        assert normalize_typography(text, "de") == text

    def test_a_book_behind_an_article_is_a_noun_and_stays_spelled_out(self) -> None:
        # ``die Apg. 1,8`` is not something anybody would write.
        assert normalize_typography("die Apostelgeschichte 1,8 sagt es", "de") == "die Apostelgeschichte 1,8 sagt es"

    def test_the_numbers_are_still_pointed_behind_an_article(self) -> None:
        # Declining to rename is not declining to punctuate.
        assert normalize_typography("die Apostelgeschichte 1:8 sagt es", "de") == "die Apostelgeschichte 1,8 sagt es"

    def test_the_evangelists_are_abbreviated_too(self) -> None:
        assert normalize_typography("Johannes 3,16 und Lukas 2,1", "de") == "Joh. 3,16 und Lk. 2,1"


class TestARussianAbbreviationDoesNotSurviveInGerman:
    """A reference written in the source language inside a translated
    document is the clearest tell a page can carry — and now that
    ``books.py`` reads Russian and writes German, it is convertible
    rather than merely detectable."""

    def test_a_russian_abbreviation_in_a_german_table_is_translated(self) -> None:
        assert normalize_typography("<td>Ин. 3:16</td>", "de") == "<td>Joh. 3,16</td>"

    def test_a_chapter_alone_is_evidence_enough_for_a_foreign_name(self) -> None:
        # A German name needs a verse before it is rewritten, because a
        # German word can be prose. A Cyrillic word in German prose
        # cannot be, so the chapter number is all the evidence needed.
        assert normalize_typography("<td>1 Кор. 13</td>", "de") == "<td>1. Kor. 13</td>"

    def test_a_ukrainian_abbreviation_is_converted_as_well(self) -> None:
        assert normalize_typography("Дії 1,8", "de") == "Apg. 1,8"

    def test_the_russian_column_keeps_its_own_abbreviations(self) -> None:
        # The rule is "write the reference in the language of the page",
        # not "write it in German".
        assert normalize_typography("Ин. 3:16", "ru") == "Ин. 3:16"


class TestEnglishTitlesAreTitleCase:
    """Title Case, because it is the only direction that cannot make a
    factual error: it raises words that are lower case and lowers a
    closed list of function words, and no word on that list is ever a
    proper noun."""

    def test_a_sentence_case_chapter_title_is_raised(self) -> None:
        assert (
            normalize_typography("Lesson 5. Currents and ministries of the first century", "en", "title")
            == "Lesson 5. Currents and Ministries of the First Century"
        )

    def test_a_title_that_is_already_right_is_a_fixed_point(self) -> None:
        title = "Lesson 6. The Map That Fits in Your Head"
        assert normalize_typography(title, "en", "title") == title

    def test_short_words_stay_lower_unless_they_start_something(self) -> None:
        assert normalize_typography("the map that fits in your head", "en", "title") == (
            "The Map That Fits in Your Head"
        )

    def test_the_first_word_after_a_colon_is_raised(self) -> None:
        # The broken cross-reference in the corpus: a chapter stored as
        # ``Appendix: course materials`` is quoted elsewhere as
        # ``"Appendix: Course Materials."``
        assert normalize_typography("Appendix: course materials", "en", "title") == "Appendix: Course Materials"

    def test_the_last_word_is_raised_even_when_it_is_a_short_one(self) -> None:
        assert normalize_typography("what are you looking for", "en", "title") == "What Are You Looking For"

    def test_the_recurring_heading_settles_on_one_spelling(self) -> None:
        # ``Check Yourself`` 9 against ``Check yourself`` 14.
        assert normalize_typography("Check yourself", "en", "title") == "Check Yourself"
        assert normalize_typography("Check Yourself", "en", "title") == "Check Yourself"

    def test_a_heading_inside_an_html_block_is_a_title(self) -> None:
        html = "<h2>check yourself</h2>"
        assert normalize_typography(html, "en", "html") == "<h2>Check Yourself</h2>"

    def test_the_paragraph_next_to_it_is_not(self) -> None:
        # 7 of 44 lesson blocks disagree with themselves inside their own
        # ``<h2>``s — and the prose one line down must not move at all.
        html = "<h2>check yourself</h2><p>the map that fits in your head</p>"
        assert (
            normalize_typography(html, "en", "html") == "<h2>Check Yourself</h2><p>the map that fits in your head</p>"
        )

    def test_markup_inside_a_heading_does_not_break_the_words(self) -> None:
        html = "<h3>The <em>real</em> question</h3>"
        assert normalize_typography(html, "en", "html") == "<h3>The <em>Real</em> Question</h3>"

    def test_a_shouted_word_is_left_shouting(self) -> None:
        # Lowering the initial of ``THE`` produces ``tHE``. A word
        # carrying a capital anywhere but the front was written that way
        # on purpose.
        assert normalize_typography("THE MAP and THE Territory", "en", "title") == "THE MAP and THE Territory"

    def test_a_word_that_starts_small_on_purpose_is_left_small(self) -> None:
        # ``iPhone`` and ``eBay`` are the mirror of ``THE``: raising only
        # the first letter gives ``IPhone`` and ``EBay``. A capital
        # anywhere but the front takes the word out of this rule's reach
        # in both directions.
        assert normalize_typography("iPhone and eBay in the church", "en", "title") == ("iPhone and eBay in the Church")

    def test_a_word_with_a_digit_in_it_is_left_alone(self) -> None:
        assert normalize_typography("a study of 1st century faith", "en", "title") == "A Study of 1st Century Faith"

    def test_a_hyphenated_word_is_raised_on_both_sides(self) -> None:
        assert normalize_typography("the well-known road", "en", "title") == "The Well-Known Road"

    def test_a_german_title_is_not_title_cased(self) -> None:
        # German capitalises its nouns by grammar and its titles by
        # sentence case. English Title Case in German is a different
        # kind of wrong from the one being fixed.
        title = "Lektion 5. Der Auftrag und die Zeugen"
        assert normalize_typography(title, "de", "title") == title


class TestGermanSetsItsQuotesAndItsApostrophe:
    def test_the_russian_guillemets_become_german_quotes(self) -> None:
        assert normalize_typography("Er sagte «Ich glaube».", "de") == "Er sagte „Ich glaube“."

    def test_straight_quotes_become_german_quotes(self) -> None:
        assert normalize_typography('Er sagte "Ich glaube".', "de") == "Er sagte „Ich glaube“."

    def test_an_english_pair_becomes_a_german_pair(self) -> None:
        assert normalize_typography("Er sagte “Ich glaube”.", "de") == "Er sagte „Ich glaube“."

    def test_a_half_typed_pair_is_finished(self) -> None:
        assert normalize_typography('„Ich glaube".', "de") == "„Ich glaube“."

    def test_a_genitive_apostrophe_is_the_right_one(self) -> None:
        assert normalize_typography("Paulus‘ Brief und Petrus‘ Wort", "de") == "Paulus’ Brief und Petrus’ Wort"

    def test_a_typewriter_genitive_is_the_right_one_too(self) -> None:
        # 35 German strings against 3 with the correct ``Stephanus’``.
        assert normalize_typography("Paulus' Brief, Petrus' Wort, Lukas' Bericht", "de") == (
            "Paulus’ Brief, Petrus’ Wort, Lukas’ Bericht"
        )

    def test_an_elision_is_the_same_character(self) -> None:
        assert normalize_typography("Und wie geht's weiter?", "de") == "Und wie geht’s weiter?"

    def test_but_not_when_the_string_also_opens_a_single_quotation(self) -> None:
        # U+2018 *closes* a German ``‚…‘``. With one of those in the
        # string there is no way to tell a closed quotation from a
        # misspelled apostrophe, so nothing is touched.
        text = "‚Ein Zitat‘ und Paulus‘ Brief."
        assert normalize_typography(text, "de") == text

    def test_and_not_when_a_straight_mark_is_quoting_instead(self) -> None:
        # ``'Wort'`` is somebody setting an English-style single
        # quotation in German. Its closing mark sits behind a letter and
        # looks exactly like a genitive; the opening one is what gives
        # the string away, and it disarms the rule for the whole string.
        text = "Er sagte 'Wort' und Paulus' Brief."
        assert normalize_typography(text, "de") == text

    def test_an_unbalanced_quotation_mark_is_left_alone(self) -> None:
        # An odd count means one of them is not a quotation mark. The
        # inch mark is the case that made this a guard rather than an
        # alternation.
        assert normalize_typography('Das Brett ist 5" breit.', "de") == 'Das Brett ist 5" breit.'


class TestGermanHasNoEmDash:
    """58 em dashes against 411 en dashes. German sets a parenthetical
    with an en dash and a range with the same en dash; the em dash is
    not one of its glyphs."""

    def test_an_em_dash_becomes_an_en_dash(self) -> None:
        assert normalize_typography("Der Weg — und er war lang — endet hier.", "de") == (
            "Der Weg – und er war lang – endet hier."
        )

    def test_a_range_keeps_its_tight_setting(self) -> None:
        # Only the glyph is swapped, never the spacing: an unspaced en
        # dash is how German sets a range, so spacing carries meaning
        # this rule cannot recover from the character alone.
        assert normalize_typography("Die Jahre 30—33", "de") == "Die Jahre 30–33"

    def test_an_en_dash_is_already_right(self) -> None:
        assert normalize_typography("Der Weg – und er war lang – endet hier.", "de") == (
            "Der Weg – und er war lang – endet hier."
        )


class TestEnglishSetsOneDashStyle:
    """163 spaced against 37 unspaced and one stray spaced en dash —
    three styles, sometimes in one paragraph. The majority wins, and it
    is the house style of everything this reads like."""

    def test_an_unspaced_em_dash_gets_its_spaces(self) -> None:
        assert normalize_typography("The road—and it was long—ran east.", "en") == (
            "The road — and it was long — ran east."
        )

    def test_a_spaced_en_dash_becomes_a_spaced_em_dash(self) -> None:
        assert normalize_typography("The road – and it was long – ran east.", "en") == (
            "The road — and it was long — ran east."
        )

    def test_the_spaced_form_is_a_fixed_point(self) -> None:
        text = "The road — and it was long — ran east."
        assert normalize_typography(text, "en") == text

    def test_a_range_of_numbers_stays_tight(self) -> None:
        assert normalize_typography("The war ran 1914–1918 in Europe.", "en") == "The war ran 1914–1918 in Europe."

    def test_a_verse_range_stays_tight(self) -> None:
        assert normalize_typography("Read Acts 8:26–40 tonight.", "en") == "Read Acts 8:26–40 tonight."

    def test_a_hyphen_is_never_a_dash(self) -> None:
        assert normalize_typography("a well-known first-century road", "en") == "a well-known first-century road"


class TestGermanGroupsItsThousands:
    """``3.000 Menschen`` and ``3000`` in the same quiz, describing the
    same crowd."""

    def test_a_bare_thousand_is_grouped(self) -> None:
        assert normalize_typography("Etwa 3000 Menschen kamen dazu.", "de") == "Etwa 3.000 Menschen kamen dazu."

    def test_a_grouped_thousand_is_a_fixed_point(self) -> None:
        assert normalize_typography("Etwa 3.000 Menschen kamen dazu.", "de") == "Etwa 3.000 Menschen kamen dazu."

    def test_a_larger_count_is_grouped_from_the_right(self) -> None:
        assert normalize_typography("144000 Versiegelte", "de") == "144.000 Versiegelte"

    def test_a_year_is_never_grouped(self) -> None:
        # German writes ``1517`` and ``2026`` without a separator,
        # always. Four digits in that range are far likelier to be a
        # year than a count, so the whole range is left alone.
        assert normalize_typography("Im Jahr 1517 und im Jahr 2026.", "de") == "Im Jahr 1517 und im Jahr 2026."


class TestEnglishIsMadeStraight:
    """Straight, not curly. Curly requires deciding which way each mark
    points; straight is a total mapping that cannot be got backwards —
    and it is where 93% of the corpus already sits."""

    def test_curly_doubles_become_straight(self) -> None:
        assert normalize_typography("He said “yes”.", "en") == 'He said "yes".'

    def test_a_curly_possessive_becomes_straight(self) -> None:
        assert normalize_typography("Paul’s letter", "en") == "Paul's letter"

    def test_the_two_spellings_in_one_paragraph_end_up_the_same(self) -> None:
        assert normalize_typography("Peter's and Paul’s", "en") == "Peter's and Paul's"

    def test_quotes_that_do_not_balance_are_fixed_anyway(self) -> None:
        # Six production strings open a curly quote and never close it.
        # Straightening needs no partner, so the unbalanced case has no
        # special handling — it simply stops being visible.
        assert normalize_typography("He said “yes.", "en") == 'He said "yes.'

    def test_a_possessive_at_the_end_of_a_word_is_not_disturbed(self) -> None:
        assert normalize_typography("Jesus' disciples", "en") == "Jesus' disciples"

    def test_the_russian_guillemets_do_not_survive_into_english(self) -> None:
        # The source is Russian. A quotation the verse-substitution layer
        # does not recognise travels to the model as ordinary prose and
        # comes back wearing the author's own marks, so an English lesson
        # could hold a restored verse in ``"…"`` and the same verse in
        # ``«…»`` twenty lines further down.
        assert normalize_typography("He said «yes».", "en") == 'He said "yes".'

    def test_nor_do_the_german_ones(self) -> None:
        assert normalize_typography("He said „yes“.", "en") == 'He said "yes".'


class TestUkrainianHasOneApostrophe:
    def test_a_typewriter_apostrophe_inside_a_word_becomes_typographic(self) -> None:
        assert normalize_typography("Це п'ять днів", "uk") == "Це п’ять днів"

    def test_the_same_word_spelled_both_ways_ends_up_spelled_once(self) -> None:
        assert normalize_typography("ім'я та ім’я", "uk") == "ім’я та ім’я"

    def test_a_mark_that_is_not_inside_a_word_is_not_an_apostrophe(self) -> None:
        # Ukrainian never puts an apostrophe at the edge of a word, so
        # anything not flanked by two Cyrillic letters is something else
        # — a quotation mark, a foreign name, a stray character — and is
        # left for a human.
        assert normalize_typography("'цитата' та d'Artagnan", "uk") == "'цитата' та d'Artagnan"

    def test_ukrainian_quotes_are_guillemets(self) -> None:
        assert normalize_typography('Він сказав "мир".', "uk") == "Він сказав «мир»."


class TestRussianKeepsItsGuillemets:
    def test_straight_quotes_become_guillemets(self) -> None:
        assert normalize_typography('Он сказал "мир".', "ru") == "Он сказал «мир»."

    def test_a_correct_russian_string_is_a_fixed_point(self) -> None:
        assert normalize_typography("«Уже правильно»", "ru") == "«Уже правильно»"


class TestMarkupIsNotProse:
    """An attribute is delimited by the same straight quote the German
    rule rewrites. Mangling one does not degrade a page, it deletes
    it."""

    def test_an_image_source_survives_byte_for_byte(self) -> None:
        html = '<img src="https://cdn.equip.test/a.png?a=1&b=2" alt="Bild">'
        assert normalize_typography(html, "de") == html

    def test_an_iframe_source_survives_byte_for_byte(self) -> None:
        html = '<iframe src="https://www.youtube.com/embed/xyz?rel=0&start=30"></iframe>'
        assert normalize_typography(html, "ru") == html

    def test_a_class_attribute_survives_byte_for_byte(self) -> None:
        html = '<div class="callout callout-info"><p>Text</p></div>'
        assert normalize_typography(html, "de") == html

    def test_the_prose_around_the_markup_is_still_pointed(self) -> None:
        html = '<p class="callout">Lies Apg. 8:26 dazu.</p>'
        assert normalize_typography(html, "de") == '<p class="callout">Lies Apg. 8,26 dazu.</p>'

    def test_a_code_sample_keeps_its_straight_quotes(self) -> None:
        html = '<p><code>print("hallo")</code> und "Wort".</p>'
        assert normalize_typography(html, "de") == '<p><code>print("hallo")</code> und „Wort“.</p>'

    def test_an_entity_is_never_split(self) -> None:
        html = "<p>Gr&ouml;&szlig;e und &quot;Wort&quot;</p>"
        assert normalize_typography(html, "de") == html

    def test_an_unterminated_tag_makes_the_rest_markup(self) -> None:
        # ``strip_tags`` makes the same call: once a ``<`` opens with no
        # ``>`` to close it, we no longer know what is prose.
        broken = '<p>Text</p><img src="a.png?x=1'
        assert normalize_typography(broken, "de") == broken

    def test_the_tag_stream_comes_out_identical(self) -> None:
        # The span layer can move characters around, which the character
        # layer could not. This is what says it never moved one that
        # belonged to a tag.
        for locale, kind, text in CORPUS_SHAPES:
            assert _tags(normalize_typography(text, locale, kind)) == _tags(text), f"{locale}: {text!r}"


class TestWhatMustNotChange:
    def test_a_straight_apostrophe_inside_a_url(self) -> None:
        text = "Siehe https://example.com/it's-here für mehr."
        assert normalize_typography(text, "en") == text
        assert normalize_typography(text, "uk") == text

    def test_a_colon_in_a_time(self) -> None:
        assert normalize_typography("Der Gottesdienst beginnt um 18:30 Uhr.", "de") == (
            "Der Gottesdienst beginnt um 18:30 Uhr."
        )

    def test_a_colon_in_a_ratio(self) -> None:
        assert normalize_typography("Das Verhältnis war 3:1.", "de") == "Das Verhältnis war 3:1."

    def test_a_number_with_a_thousands_separator(self) -> None:
        assert normalize_typography("Er zahlte 1.000 Euro.", "de") == "Er zahlte 1.000 Euro."

    def test_a_number_that_is_not_a_thousands_separator(self) -> None:
        # A dot in a German number is a thousands separator or an
        # ordinal, and the two are told apart by the space that follows
        # the ordinal. Neither the date nor the decimal moves.
        assert normalize_typography("Am 3. Mai, bei 3,5 Grad, in Raum 1234b.", "de") == (
            "Am 3. Mai, bei 3,5 Grad, in Raum 1234b."
        )

    def test_a_bare_number_with_no_book_in_front_of_it(self) -> None:
        # The whole conservative stance in one test: without a book name
        # as evidence, ``10:1-23`` could be anything, so it stays as it
        # is even though it looks exactly like a reference.
        assert normalize_typography("Vergleiche 10:1-23 damit.", "de") == "Vergleiche 10:1-23 damit."

    def test_an_english_possessive_at_the_end_of_a_word(self) -> None:
        assert normalize_typography("the disciples' feet", "en") == "the disciples' feet"

    def test_a_genuine_em_dash_quoting_an_english_source(self) -> None:
        # English keeps the em dash — it is the glyph English uses, and
        # the German rule that demotes it to an en dash is a rule about
        # German and not about the character.
        text = 'Lewis wrote: "There is — I think — no other way home."'
        assert normalize_typography(text, "en") == text

    def test_a_german_sentence_that_spells_out_a_book(self) -> None:
        text = "Die Apostelgeschichte erzählt, wie das Evangelium nach Rom kam."
        assert normalize_typography(text, "de") == text

    def test_english_prose_is_never_title_cased(self) -> None:
        # The same words that read as a heading read as a sentence one
        # line down. Only a ``title`` field and a heading element are
        # titles.
        text = "the map that fits in your head"
        assert normalize_typography(text, "en", "plain") == text
        assert normalize_typography(text, "en", "quiz_option") == text
        assert normalize_typography(text, "en", "html") == text

    def test_russian_source_text_is_already_right(self) -> None:
        source = "Он сказал: «Идите и научите все народы» (Матф. 28:19)."
        assert normalize_typography(source, "ru") == source


class TestTheSecondPassChangesNothing:
    """Idempotence is what makes this safe to run over stored rows and
    not only over new ones."""

    def test_applying_it_twice_equals_applying_it_once(self) -> None:
        for locale, kind, text in CORPUS_SHAPES:
            once = normalize_typography(text, locale, kind)
            twice = normalize_typography(once, locale, kind)
            assert twice == once, f"{locale}: {once!r} -> {twice!r}"

    def test_the_character_layer_never_changes_the_length_of_a_string(self) -> None:
        # Half the pass is still one character for one — quotation
        # marks, apostrophes, the German dash glyph, English title
        # casing. Nothing there can be inserted or deleted, so the worst
        # a bug in it can do is make a character wrong.
        for locale, kind, text in CORPUS_SHAPES:
            assert len(normalize_characters(text, locale, kind)) == len(text), f"{locale}: {text!r}"

    def test_no_whitespace_is_ever_deleted(self) -> None:
        # What is left of "a paragraph cannot disappear" once the span
        # layer is allowed to change a string's length: it may add a
        # space around a dash, it may shorten a book's name, and it may
        # never run two words together.
        for locale, kind, text in CORPUS_SHAPES:
            once = normalize_typography(text, locale, kind)
            assert sum(char.isspace() for char in once) >= sum(char.isspace() for char in text), f"{locale}: {text!r}"

    def test_an_empty_string_is_returned_as_it_is(self) -> None:
        assert normalize_typography("", "de") == ""

    def test_the_same_holds_for_strings_nobody_would_write(self) -> None:
        # The hand-written cases above all read like prose, and that is
        # their weakness: the two idempotence bugs found when this
        # module was first written were both in strings prose never
        # produces — a ``»`` at the very start, and two quotation marks
        # with nothing between them. Both settled on one answer the
        # first time and a different one the second. So the pieces below
        # are shuffled into 2,000 seeded strings and the properties are
        # checked on every one of them, for every locale and every
        # content kind.
        random.seed(11)
        pieces = (
            '<p class="callout callout-info">',
            "</p>",
            "<em>",
            "</em>",
            "<h2>",
            "</h2>",
            '<img src="https://cdn.test/a.png?a=1&b=2">',
            "<code>",
            "</code>",
            "&amp;",
            "&#39;",
            "https://ex.test/it's-here",
            "Apg. 8:26",
            "Apg 8,26.30",
            "Apostelgeschichte 1,8",
            "Ин. 3:16",
            "1 Кор. 13",
            "1. Korinther 13,4",
            "die Apostelgeschichte 1,8",
            "10:1-23",
            "18:30",
            "3000",
            "1.000",
            "2026",
            '"',
            "'",
            "«",
            "»",
            "„",
            "“",
            "”",
            "‘",
            "’",
            "‚",
            " ",
            "Wort",
            "the map",
            "check yourself",
            "п'ять",
            "Peter's",
            "Paulus'",
            "-",
            "–",
            "—",
            ",",
            ".",
            ";",
            ":",
            "<",
            ">",
        )
        kinds: tuple[ContentKind, ...] = ("plain", "html", "title", "quiz_question", "quiz_option")
        for _ in range(2000):
            text = "".join(random.choice(pieces) for _ in range(random.randint(1, 12)))
            kind = random.choice(kinds)
            for locale in LOCALE_CODES:
                once = normalize_typography(text, locale, kind)
                assert normalize_typography(once, locale, kind) == once, f"{locale}/{kind}: {once!r}"
                assert _tags(once) == _tags(text), f"{locale}/{kind}: {text!r} -> {once!r}"
                assert sum(c.isspace() for c in once) >= sum(c.isspace() for c in text), f"{locale}/{kind}: {text!r}"
                assert len(normalize_characters(text, locale, kind)) == len(text), f"{locale}/{kind}: {text!r}"


class TestEveryLanguageIsPointed:
    def test_no_served_locale_falls_through_unpointed(self) -> None:
        # A locale nobody wrote a rule for is not a crash — it is a page
        # that quietly keeps the source's punctuation, which is the
        # defect this module exists to remove. Same guard the book-name
        # table gets in ``test_every_language_names_the_books``.
        marker = 'Er sagte “Wort” und "Wort".'
        for locale in LOCALE_CODES:
            assert normalize_typography(marker, locale) != marker, locale


def _gemini_answering(text: str) -> GeminiTranslationProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content.decode())["contents"]
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": text}]}}],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 5},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    return GeminiTranslationProvider(
        api_key="fake-key",
        model="gemini-flash-latest",
        timeout_seconds=5.0,
        max_output_tokens=256,
        max_retries=0,
        client=client,
    )


class TestNothingReachesTheDatabaseUnpointed:
    """The rules are worth nothing in a module nobody calls. They run in
    the provider, after the canonical verses are restored, so a stored
    translation is pointed before anybody reads it."""

    def _translate(self, answer: str, target: LocaleCode, kind: ContentKind = "plain") -> str:
        provider = _gemini_answering(answer)
        try:
            return provider.translate(
                TranslationRequest(
                    text="Прочитай это внимательно.",
                    source_locale="ru",
                    target_locale=target,
                    content_kind=kind,
                )
            ).text
        finally:
            provider.close()

    def test_a_german_answer_comes_back_pointed(self) -> None:
        assert self._translate('Lies Apg 8:26 und sage "Amen".', "de") == "Lies Apg. 8,26 und sage „Amen“."

    def test_an_english_answer_comes_back_straight(self) -> None:
        assert self._translate("Read Acts 8:26 — “Peter’s word”.", "en") == 'Read Acts 8:26 — "Peter\'s word".'

    def test_the_content_kind_travels_with_the_text(self) -> None:
        # Only the field it came from knows a title is a title, so the
        # provider has to hand that on or the rule cannot fire at all.
        assert self._translate("check yourself", "en", "title") == "Check Yourself"
        assert self._translate("check yourself", "en", "plain") == "check yourself"

    def test_an_answer_that_needs_nothing_is_returned_identically(self) -> None:
        answer = "Читай Дії 8:26 уважно."
        assert self._translate(answer, "uk") == answer
