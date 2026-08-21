# ruff: noqa: RUF001, RUF002
"""A quotation around a verse that ends in a colon never visually closed.

Found by census, read one by one on 2026-08-21. Thirty-one live German
and Ukrainian rows served a quotation whose *closing* mark was written
as an opening one, so the reader met a quotation that opens twice and
never ends. Every one of them has the same shape — a daily-challenge
explanation or a chapter block quoting Scripture, cut where the question
needs it, so the verse ends in the punctuation it ends in:

    2. Mose 20,1 besagt: „Und Gott redete alle diese Worte und sprach:„
    Вихід 20:1 свідчить: «І глаголав Господь всї словеса оцї, глаголючи:«
    Johannes 1,1 besagt: „Am Anfang war das Wort…„ (Lutherbibel 2017).

The cause is that ``:`` and ``…`` were in ``_OPENING_CONTEXT``. Both
look like they belong there — a colon does introduce a quotation. But
German, Ukrainian and Russian all write that colon with a **space**
after it, and when the space is there the space is what the rule reads.
The colon itself was therefore only ever consulted welded to the mark,
``sprach:„``, which is not a quotation being introduced but one being
closed around a verse that ends in a colon. Counted over the whole
catalogue: 34 marks stand welded to a colon or an ellipsis and every one
of them closes by meaning.

Three of the thirty-one end in a dash rather than a colon — a stray
character left on the end of a truncated verse, ``auf meine Klage. –„``.
The dash already had a rule of its own, and it reads the character
before the dash; these three stand after a space, so it called them
punctuation and opened. They are settled by asking the *other* side as
well: an opening mark is welded to the text it introduces, and there is
no text here, only a space and then commentary.

The general form of that lookahead — every mark, not only one after a
dash — was measured and rejected. See ``TestWhatTheLookaheadMustNotDo``.
"""

from __future__ import annotations

import pytest

from app.services.translation.typography import normalize_typography
from scripts.repoint_unclosed_quotations import _marks_pair_up, _only_marks_moved

# Verbatim from ``content_versions``, all live rows on 2026-08-21.
DE_COLON = (
    "2. Mose 20,1 besagt: „Und Gott redete alle diese Worte und sprach:„, "
    "was darauf hindeutet, dass Gott selbst der Sprecher war."
)
DE_ELLIPSIS = (
    "Johannes 1,1 besagt: „Am Anfang war das Wort…„ (Lutherbibel 2017). "
    "Dies identifiziert das Wort direkt als die Entität, die von Anfang an präsent war."
)
DE_DASH = (
    "Habakuk 2,1 spricht: „Auf meine Warte will ich treten und auf den Turm mich stellen "
    "und will spähen, um zu sehen, was er mit mir reden wird und was ich erwidern soll "
    "auf meine Klage. –„ Dies zeigt, dass der Prophet darauf wartete, Gottes Antwort zu hören."
)
UK_COLON = (
    "Вихід 20:1 свідчить: «І глаголав Господь всї словеса оцї, глаголючи:«, що вказує на те, що промовляв сам Бог."
)
UK_DASH = (
    "1 Івана 1:1 зазначає: «Що було від почину, про що ми чули, що бачили очима нашими, "
    "і на що дивили ся, і чого руки наші дотикали ся, про Слово життя, -«. "
    "Це прямо стосується їхнього чуттєвого досвіду Ісуса."
)
DE_COLON_AT_END = (
    "Judas 1,1 gibt an: „Judas, Knecht Jesu Christi und Bruder des Jakobus, "
    "den in Gott, dem Vater, geliebten und in Jesus Christus bewahrten Berufenen:„"
)
# The same defect inside a large chapter block, where it is not the last
# mark in the string — which is why a lookahead for "is there a later
# mark that could close this one" does not reach it.
DE_IN_A_BLOCK = (
    '<div class="callout callout-verse">\n<blockquote>„Denn es hat dem Heiligen Geist und '
    "uns gefallen, euch keine größere Last auf euch zu legen als diese notwendigen Stücke:„ "
    "(Apg. 15,28).</blockquote>\n</div>\n\n<p>Von diesem Zeitpunkt an wird „Saulus“ häufiger "
    "„Paulus“ genannt.</p>"
)

DE_IN_A_BLOCK_REPAIRED = DE_IN_A_BLOCK.replace("Stücke:„ (Apg.", "Stücke:“ (Apg.")

# Russian got this right in the source, and the pass would have
# overwritten it. Not a repair — a row this change stops us breaking.
RU_ALREADY_RIGHT = (
    "Исход 20:1 гласит: «И говорил Бог все слова сии, говоря:», указывая на то, что Сам Бог был говорящим."
)


def _marks(text: str) -> list[str]:
    return [c for c in text if c in '«»„“”"']


class TestAQuotationAroundAVerseThatEndsInAColon:
    def test_the_german_row_from_production_gets_its_closing_mark(self) -> None:
        assert _marks(normalize_typography(DE_COLON, "de")) == ["„", "“"]

    def test_the_ukrainian_row_from_production_gets_its_closing_mark(self) -> None:
        assert _marks(normalize_typography(UK_COLON, "uk")) == ["«", "»"]

    def test_a_verse_truncated_with_an_ellipsis_closes_too(self) -> None:
        assert _marks(normalize_typography(DE_ELLIPSIS, "de")) == ["„", "“"]

    def test_a_verse_left_with_a_stray_dash_closes_too(self) -> None:
        assert _marks(normalize_typography(DE_DASH, "de")) == ["„", "“"]

    def test_the_ukrainian_stray_dash_closes_as_well(self) -> None:
        assert _marks(normalize_typography(UK_DASH, "uk")) == ["«", "»"]

    def test_a_colon_at_the_very_end_of_the_string_closes(self) -> None:
        assert _marks(normalize_typography(DE_COLON_AT_END, "de")) == ["„", "“"]

    def test_the_same_defect_inside_a_chapter_block_closes(self) -> None:
        """Three of the thirty-one live rows are large chapter blocks
        where the mis-pointed mark has a dozen marks after it. Any rule
        that asked "is there a later mark to close this one" would call
        this one opening and leave the block broken."""
        # Asserted on the whole string rather than on a mark census,
        # because the ``class="…"`` attribute carries straight quotes
        # that are markup and must come through untouched.
        assert normalize_typography(DE_IN_A_BLOCK, "de", content_kind="html") == DE_IN_A_BLOCK_REPAIRED

    def test_the_russian_row_that_was_already_right_stays_right(self) -> None:
        """The control. Russian wrote the closing mark correctly; the
        old rule read the colon and would have replaced it with an
        opening one the next time the row was pointed."""
        assert normalize_typography(RU_ALREADY_RIGHT, "ru") == RU_ALREADY_RIGHT

    def test_a_colon_that_introduces_a_quotation_still_opens_it(self) -> None:
        """With the space that every one of these languages writes, the
        space is what the rule reads and the colon never comes up."""
        assert normalize_typography('Er sagte: "Ich glaube".', "de") == "Er sagte: „Ich glaube“."

    def test_the_ukrainian_form_of_that_opens_too(self) -> None:
        assert normalize_typography('Він сказав: "Я вірю".', "uk") == "Він сказав: «Я вірю»."


class TestWhatTheLookaheadMustNotDo:
    """The obvious general rule is that an opening mark is welded to the
    text it introduces, so a mark followed by a space is closing. It is
    wrong, and a live row proves it — which is why the lookahead is
    asked on one branch only."""

    def test_a_sloppy_space_after_an_opening_mark_does_not_close_it(self) -> None:
        # ``d684f145``, live Ukrainian chapter block. The space after
        # ``«`` is untidy, not a mis-pointed mark, and a general
        # lookahead would answer it by turning the opening mark into a
        # closing one — a real error traded for a cosmetic one.
        html = "<li>формулювати принцип « угодно Святому Духу і нам» як модель соборного рішення.</li>"
        assert _marks(normalize_typography(html, "uk", content_kind="html")) == ["«", "»"]

    def test_a_german_opening_mark_followed_by_a_space_is_left_opening(self) -> None:
        assert _marks(normalize_typography("Das Prinzip „ Wort und Tat“ gilt.", "de")) == ["„", "“"]


class TestTheNestedQuotationsMustSurvive:
    """Both languages set an inner quotation in the same characters as
    the outer one. These two live rows are why depth was rejected when
    the dash rule was written, and they have to keep working."""

    def test_the_german_psalm_heading_keeps_its_inner_pair(self) -> None:
        text = (
            "Psalm 22,1 besagt: „(Dem Vorsänger, nach: „Hirschkuh der Morgenröte“. "
            "Ein Psalm von David.)“. Dies drückt direkt das Gefühl aus, von Gott "
            "verlassen worden zu sein."
        )
        assert normalize_typography(text, "de") == text

    def test_the_ukrainian_question_in_a_question_keeps_its_inner_pair(self) -> None:
        text = (
            "У Буття 3:1 змій починає з запитання: «Чи справді Бог сказав: "
            "«Не їжте плодів з будь-якого дерева в саду»?»"
        )
        assert normalize_typography(text, "uk") == text


class TestWhatTheColonRuleMustNotBreak:
    """Everything the module had already earned, re-asserted here
    because this change is in the same loop."""

    def test_the_truncated_word_still_closes(self) -> None:
        # The hyphen rule, shipped just before this one.
        text = "nicht nach dem häufigen: „Senf-“, nicht „Korn“."
        assert normalize_typography(text, "de", content_kind="html") == text

    def test_a_dash_standing_free_still_opens_a_quotation(self) -> None:
        assert _marks(normalize_typography('— "Komm her", sagte er.', "de")) == ["„", "“"]

    def test_a_dash_at_the_very_start_of_the_string_still_opens_one(self) -> None:
        assert _marks(normalize_typography('—"Komm her"', "de")) == ["„", "“"]

    def test_the_verse_that_opens_a_block_still_gets_its_opening_mark(self) -> None:
        html = "<p>Vorher.</p><blockquote>“Doch weil ihr an Christi Leiden teilhabt, freut euch.“</blockquote>"
        assert _marks(normalize_typography(html, "de", content_kind="html")) == ["„", "“"]

    def test_a_quotation_that_closes_across_a_block_still_closes(self) -> None:
        html = "<p>Er sagte: „Geht hin</p><p>und kommt wieder.“</p>"
        assert _marks(normalize_typography(html, "de", content_kind="html")) == ["„", "“"]

    def test_an_inch_mark_is_still_left_alone(self) -> None:
        assert normalize_typography('Das Brett ist 5" breit.', "de") == 'Das Brett ist 5" breit.'

    def test_an_unbalanced_string_keeps_every_mark_it_has(self) -> None:
        text = 'Das Brett ist 5" breit, und er sagte: „Wort“.'
        assert normalize_typography(text, "de") == text

    @pytest.mark.parametrize(
        "text",
        [
            'Look for the rare word: "mustard-", not "seed".',
            'And the LORD spake unto Moses, saying:" This verse identifies Moses.',
            '<p>Before.</p><blockquote>"Go therefore"</blockquote>',
            '— "Come here"',
        ],
    )
    def test_english_is_a_no_op_because_its_marks_are_the_same_character(self, text: str) -> None:
        assert normalize_typography(text, "en", content_kind="html") == text


class TestTheSecondPassStillChangesNothing:
    @pytest.mark.parametrize(
        ("text", "locale"),
        [
            (DE_COLON, "de"),
            (DE_ELLIPSIS, "de"),
            (DE_DASH, "de"),
            (DE_COLON_AT_END, "de"),
            (DE_IN_A_BLOCK, "de"),
            (UK_COLON, "uk"),
            (UK_DASH, "uk"),
            (RU_ALREADY_RIGHT, "ru"),
            ("<li>формулювати принцип « угодно Святому Духу і нам» як модель.</li>", "uk"),
        ],
    )
    def test_applying_it_twice_equals_applying_it_once(self, text: str, locale: str) -> None:
        once = normalize_typography(text, locale, content_kind="html")  # type: ignore[arg-type]
        assert normalize_typography(once, locale, content_kind="html") == once  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("text", "locale"),
        [(DE_COLON, "de"), (UK_COLON, "uk"), (DE_DASH, "de"), (DE_IN_A_BLOCK, "de")],
    )
    def test_the_repaired_string_is_itself_a_fixed_point(self, text: str, locale: str) -> None:
        """What the production repair rests on: pointing a row that has
        already been pointed changes nothing, so the UPDATE can be run
        again without further effect."""
        once = normalize_typography(text, locale, content_kind="html")  # type: ignore[arg-type]
        assert once != text
        assert normalize_typography(once, locale, content_kind="html") == once  # type: ignore[arg-type]


class TestTheRepairRefusesWhatItCannotProve:
    """``scripts/repoint_unclosed_quotations`` mends the rows written
    before the fix. Its guards are what keep a targeted UPDATE from
    becoming a re-point of the whole catalogue, and one of them exists
    because the dry run against production caught a regression dressed
    as a repair."""

    def test_a_russian_inner_quotation_is_not_flattened(self) -> None:
        # ``«“…”»`` is an inner quotation set the way Russian sets one.
        # It fails a naive pair test, and "repairing" it would give
        # ``««…»»``. The guard is that a row must already be pointed in
        # the language's own two marks before it is eligible at all.
        assert not _marks_pair_up(["«", "“", "”", "»"], "«", "»")
        assert _marks_pair_up(["«", "»"], "«", "»")
        assert _marks_pair_up(["«", "«", "»", "»"], "«", "»")

    def test_a_quotation_opened_twice_is_what_it_is_looking_for(self) -> None:
        assert not _marks_pair_up(["„", "„"], "„", "“")
        assert _marks_pair_up(["„", "“"], "„", "“")

    def test_english_is_asked_only_for_an_even_count(self) -> None:
        assert _marks_pair_up(['"', '"'], '"', '"')
        assert not _marks_pair_up(['"', '"', '"'], '"', '"')

    def test_only_a_quotation_mark_may_move(self) -> None:
        assert _only_marks_moved("sprach:„ Dies", "sprach:“ Dies")
        assert not _only_marks_moved("Apg 8:26", "Apg 8,26")
        assert not _only_marks_moved("„Wort“", "„Wort“ ")

    def test_the_repair_of_a_production_row_moves_nothing_but_the_mark(self) -> None:
        assert _only_marks_moved(DE_COLON, normalize_typography(DE_COLON, "de"))
        assert _only_marks_moved(UK_COLON, normalize_typography(UK_COLON, "uk"))
        assert _only_marks_moved(DE_DASH, normalize_typography(DE_DASH, "de"))
