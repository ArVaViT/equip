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

These are rules, not preferences, so they are tested as rules. Each
class below pins one of them, plus the three properties that make the
pass safe to run over stored content: it is idempotent, it never
changes the length of a string, and it cannot reach inside markup.

The last class is the one that matters most. Everything this module
does is an edit nobody will re-read, so the cases that must come out
byte-identical are worth more than the cases that must change.
"""

from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

import httpx

from app.schemas.locale import LOCALE_CODES
from app.services.translation.gemini import GeminiTranslationProvider
from app.services.translation.protocol import TranslationRequest
from app.services.translation.typography import normalize_typography

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode


# Shapes taken from what the corpus actually holds: TipTap HTML with
# callouts and embedded media, Daily Challenge explanations with no
# markup at all, quiz options that quote a verse with the reference in
# brackets.
CORPUS_SHAPES: tuple[tuple[LocaleCode, str], ...] = (
    ("de", '<p class="callout callout-info">Lies Apg. 8:26-40 und Apg 10:1-23; 11:3.</p>'),
    ("de", "<p>Philippus‘ Weg beginnt in Apg 8,26.</p>"),
    ("de", '<p>Er sagte «Ich glaube» und dann "Amen".</p>'),
    ("de", '<figure><img src="https://cdn.equip.test/a.png?a=1&amp;b=2" alt="Apg 8:26"></figure>'),
    ("en", "<p>“Peter’s answer” is not Paul's answer.</p>"),
    ("en", "<p>Read Acts 8:26 before 18:30.</p>"),
    ("uk", "<p>Це п'ять причин, і ім'я його відоме.</p>"),
    ("uk", '<p>Він сказав "мир вам".</p>'),
    ("ru", '<p>Он сказал "мир вам" в 18:30.</p>'),
    ("ru", "<p>«Уже правильно», — сказал он.</p>"),
)


class TestGermanPointsAReferenceItsOwnWay:
    """Comma between chapter and verse, full stop between verses, en dash
    for a range. The source's colon is not a German variant."""

    def test_a_colon_between_chapter_and_verse_becomes_a_comma(self) -> None:
        assert normalize_typography("Lies Apg. 8:26 heute.", "de") == "Lies Apg. 8,26 heute."

    def test_the_book_may_be_spelled_out(self) -> None:
        assert normalize_typography("Apostelgeschichte 8:26", "de") == "Apostelgeschichte 8,26"

    def test_a_hyphen_range_becomes_an_en_dash(self) -> None:
        assert normalize_typography("Apg 8,26-40", "de") == "Apg 8,26–40"

    def test_a_second_verse_of_the_same_chapter_is_listed_with_a_full_stop(self) -> None:
        # The Russian source writes 8:26,30 for two verses. Carried over
        # literally and then half-fixed, that reads 8,26,30 — three
        # numbers and no way to tell which is the chapter.
        assert normalize_typography("Apg 8:26,30", "de") == "Apg 8,26.30"

    def test_a_range_that_crosses_a_chapter_keeps_both_commas(self) -> None:
        assert normalize_typography("Apg 8:26-9:3", "de") == "Apg 8,26–9,3"

    def test_a_second_passage_after_a_semicolon_is_pointed_too(self) -> None:
        assert normalize_typography("Apg 10:1-23; 11:3", "de") == "Apg 10,1–23; 11,3"

    def test_a_chapter_with_no_verse_is_left_as_it_is(self) -> None:
        assert normalize_typography("Apostelgeschichte 8 erzählt davon.", "de") == "Apostelgeschichte 8 erzählt davon."

    def test_an_already_german_reference_is_untouched(self) -> None:
        assert normalize_typography("Apg 8,26.30–32", "de") == "Apg 8,26.30–32"

    def test_the_abbreviation_style_is_not_the_pass_job(self) -> None:
        # ``Apg`` and ``Apg.`` and ``Apostelgeschichte`` are three ways
        # of naming a book, not three ways of pointing a reference.
        # Choosing between them is an editorial decision; this pass only
        # moves punctuation, so all three survive with their own
        # spelling and the same commas.
        assert normalize_typography("Apg 8:26 / Apg. 8:26", "de") == "Apg 8,26 / Apg. 8,26"

    def test_a_number_too_large_to_be_a_verse_disqualifies_the_match(self) -> None:
        assert normalize_typography("Apg 8:2026", "de") == "Apg 8:2026"

    def test_a_weekday_that_reads_like_a_book_is_not_one(self) -> None:
        # ``Mi.`` is Micah in a reference and Mittwoch in a timetable.
        # One ambiguous abbreviation is not worth a repointed time.
        assert normalize_typography("Mi. 8:30 Uhr im Saal", "de") == "Mi. 8:30 Uhr im Saal"


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

    def test_but_not_when_the_string_also_opens_a_single_quotation(self) -> None:
        # U+2018 *closes* a German ``‚…‘``. With one of those in the
        # string there is no way to tell a closed quotation from a
        # misspelled apostrophe, so nothing is touched.
        text = "‚Ein Zitat‘ und Paulus‘ Brief."
        assert normalize_typography(text, "de") == text

    def test_an_unbalanced_quotation_mark_is_left_alone(self) -> None:
        # An odd count means one of them is not a quotation mark. The
        # inch mark is the case that made this a guard rather than an
        # alternation.
        assert normalize_typography('Das Brett ist 5" breit.', "de") == 'Das Brett ist 5" breit.'


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

    def test_a_bare_number_with_no_book_in_front_of_it(self) -> None:
        # The whole conservative stance in one test: without a book name
        # as evidence, ``10:1-23`` could be anything, so it stays as it
        # is even though it looks exactly like a reference.
        assert normalize_typography("Vergleiche 10:1-23 damit.", "de") == "Vergleiche 10:1-23 damit."

    def test_an_english_possessive_at_the_end_of_a_word(self) -> None:
        assert normalize_typography("the disciples' feet", "en") == "the disciples' feet"

    def test_russian_source_text_is_already_right(self) -> None:
        source = "Он сказал: «Идите и научите все народы» (Матф. 28:19)."
        assert normalize_typography(source, "ru") == source


class TestTheSecondPassChangesNothing:
    """Idempotence is what makes this safe to run over stored rows and
    not only over new ones."""

    def test_applying_it_twice_equals_applying_it_once(self) -> None:
        for locale, text in CORPUS_SHAPES:
            once = normalize_typography(text, locale)
            twice = normalize_typography(once, locale)
            assert twice == once, f"{locale}: {once!r} -> {twice!r}"

    def test_the_length_of_the_string_never_changes(self) -> None:
        # Every rule is one character for one. Nothing can be inserted
        # and nothing deleted, so the worst a bug here can do is make a
        # character wrong — it cannot lose a sentence.
        for locale, text in CORPUS_SHAPES:
            assert len(normalize_typography(text, locale)) == len(text)

    def test_an_empty_string_is_returned_as_it_is(self) -> None:
        assert normalize_typography("", "de") == ""

    def test_the_same_holds_for_strings_nobody_would_write(self) -> None:
        # The hand-written cases above all read like prose, and that is
        # their weakness: the two idempotence bugs found during this
        # change were both in strings prose never produces — a ``»`` at
        # the very start, and two quotation marks with nothing between
        # them. Both settled on one answer the first time and a
        # different one the second. So the pieces below are shuffled
        # into 2,000 seeded strings and the three properties are checked
        # on every one of them.
        random.seed(11)
        pieces = (
            '<p class="callout callout-info">',
            "</p>",
            "<em>",
            "</em>",
            '<img src="https://cdn.test/a.png?a=1&b=2">',
            "<code>",
            "</code>",
            "&amp;",
            "&#39;",
            "https://ex.test/it's-here",
            "Apg. 8:26",
            "Apg 8,26.30",
            "10:1-23",
            "18:30",
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
            "п'ять",
            "Peter's",
            "1.000",
            "-",
            "–",
            ",",
            ".",
            ";",
            ":",
            "<",
            ">",
        )
        for _ in range(2000):
            text = "".join(random.choice(pieces) for _ in range(random.randint(1, 12)))
            for locale in LOCALE_CODES:
                once = normalize_typography(text, locale)
                assert len(once) == len(text), f"{locale}: {text!r} -> {once!r}"
                assert normalize_typography(once, locale) == once, f"{locale}: {once!r}"


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

    def _translate(self, answer: str, target: LocaleCode) -> str:
        provider = _gemini_answering(answer)
        try:
            return provider.translate(
                TranslationRequest(
                    text="Прочитай это внимательно.",
                    source_locale="ru",
                    target_locale=target,
                    content_kind="plain",
                )
            ).text
        finally:
            provider.close()

    def test_a_german_answer_comes_back_pointed(self) -> None:
        assert self._translate('Lies Apg. 8:26 und sage "Amen".', "de") == "Lies Apg. 8,26 und sage „Amen“."

    def test_an_english_answer_comes_back_straight(self) -> None:
        assert self._translate("Read Acts 8:26 — “Peter’s word”.", "en") == 'Read Acts 8:26 — "Peter\'s word".'

    def test_an_answer_that_needs_nothing_is_returned_identically(self) -> None:
        answer = "Читай Дії 8:26 уважно."
        assert self._translate(answer, "uk") == answer
