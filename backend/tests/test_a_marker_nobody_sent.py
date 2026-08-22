# ruff: noqa: RUF001
"""A token the pipeline never handed out, standing where a verse belongs.

A live Russian row read

    «Блажен муж, который не ходит [[EQV0c0214d57ac3a0bb]]»

and a reader opening the Daily Challenge was shown that token instead of
Psalm 1:1. The English source of that row has no marker in it and never
had one, and the German and Ukrainian translations of the same sentence
are clean.

What singles Russian out is that the hex is *the same hex* the previous
Russian translation of that row carried. The model did not invent it out
of the air — it copied it from the term memory, which is seeded from
what this row was translated into last time. A marker leaked into that
row once, and every retranslation since has been repeating it.

``post_substitute`` cannot mend this. It replaces the markers *this run*
handed out, and a token quoted back from a run that finished yesterday
is not among them. So the guard has to be the validator, and the reason
it was not is one line: ``_check_markers`` returned early when the source
carried no marker, on the reading that a source with nothing to lose has
nothing to check. That reads a marker as a thing only the pipeline can
write into a string. It is not.
"""

from __future__ import annotations

from app.services.translation.validation import validate_translation

_ISSUE = "scripture_marker_mismatch"


def _codes(source: str, translated: str, *, target: str = "ru") -> list[str]:
    return [
        issue.code
        for issue in validate_translation(
            source=source,
            translated=translated,
            source_locale="en",
            target_locale=target,
            content_kind="plain",
        )
    ]


class TestAMarkerTheSourceNeverSent:
    def test_the_live_row_is_named(self) -> None:
        """The row as production actually carried it, down to the hex."""
        assert _ISSUE in _codes(
            'Psalm 1:1 states, "Blessed is the man that walketh not in the counsel of the ungodly..."',
            "В Псалме 1:1 сказано: «Блажен муж, который не ходит [[EQV0c0214d57ac3a0bb]]».",
        )

    def test_the_two_clean_translations_of_that_same_row_are_not(self) -> None:
        """German and Ukrainian came back from the same run with the verse
        in them. A check that flagged these would be flagging correct
        work, which is how a check gets switched off."""
        assert _ISSUE not in _codes(
            'Psalm 1:1 states, "Blessed is the man that walketh not in the counsel of the ungodly..."',
            "Psalm 1,1 besagt: „Wohl dem Mann, der nicht wandelt im Rat der Gottlosen…“",
            target="de",
        )
        assert _ISSUE not in _codes(
            'Psalm 1:1 states, "Blessed is the man that walketh not in the counsel of the ungodly..."',
            "Псалом 1:1 говорить: «Блажен муж, що не ходить за радою нечестивих...».",
            target="uk",
        )

    def test_the_older_spelling_of_the_same_leak_is_named_too(self) -> None:
        """The row carried ``**EQV…**`` before it carried ``[[EQV…]]``.
        The decoration is the model's; the token inside it is the same
        token, and the pattern reads it either way."""
        assert _ISSUE in _codes(
            'Psalm 1:1 states, "Blessed is the man..."',
            "Псалом 1:1 гласит: «Блажен муж, который не ходит во **EQV0c0214d57ac3a0bb**...»",
        )

    def test_the_retired_prefix_is_still_recognised(self) -> None:
        """``VERSE_`` was the marker before ``EQV``, and a row carrying
        one is the same defect wearing the old name."""
        assert _ISSUE in _codes("Psalm 1:1 states the man is blessed.", "Псалом 1:1 говорит VERSE_0c0214d5.")


class TestWhatItStillSays:
    def test_a_marker_that_went_out_and_did_not_come_back_is_still_named(self) -> None:
        """The direction the check was built for, unchanged."""
        assert _ISSUE in _codes("Paul writes EQVaaaabbbbccccdddd about grace.", "Павел пишет о благодати.")

    def test_a_marker_that_survives_the_journey_raises_nothing(self) -> None:
        assert _ISSUE not in _codes(
            "Paul writes EQVaaaabbbbccccdddd about grace.",
            "Павел пишет EQVaaaabbbbccccdddd о благодати.",
        )

    def test_a_marker_swapped_for_a_different_one_is_named(self) -> None:
        assert _ISSUE in _codes(
            "Paul writes EQVaaaabbbbccccdddd about grace.",
            "Павел пишет EQV1111222233334444 о благодати.",
        )

    def test_ordinary_prose_with_no_markers_either_way_is_silent(self) -> None:
        assert _ISSUE not in _codes("Paul writes about grace.", "Павел пишет о благодати.")
