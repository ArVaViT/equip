# ruff: noqa: RUF002
"""A name inside the edition's verse is the edition's, not a substitution.

An author who quotes the opening of a verse is given the whole verse from
the edition — that is the substitution layer's rule for a quotation that
stops early. The name check then compared the author's fragment with the
edition's whole verse, found a name in the second the first never reached,
and called it a swap. Every such row was correct and every one was parked:

    Matthew 2:1 "…Bethlehem of Judaea in the days of Herod the king..."
        → НРП «…в Иерусалим пришли мудрецы с востока»   Judaea → Иерусалим
    Exodus 3:1 "Now Moses kept the flock of Jethro … priest of Midian."
        → Elberfelder „… an den Berg Gottes, an den Horeb.“   Jethro → Horeb

Replayed on 2026-09-27 over every row ever parked for a name (14 distinct):
the 11 that sat inside an edition's verse clear, the 3 real ones in course
lessons stay parked. Over the 465 live translations with a substituted
verse, no flag appears that was not there before.
"""

from __future__ import annotations

from app.services.translation.validation import validate_translation

_SOURCE = 'Exodus 3:1 states, "Now Moses kept the flock of Jethro his father in law, the priest of Midian."'
_QUOTED = "Now Moses kept the flock of Jethro his father in law, the priest of Midian."
_VERSE = (
    "Und Mose weidete die Herde Jethros, seines Schwiegervaters, des Priesters von Midian. "
    "Und er trieb die Herde hinter die Wüste und kam an den Berg Gottes, an den Horeb"
)
_TRANSLATION = f"Exodus 3,1 besagt: „{_VERSE}.“ Dieser Vers nennt Jethro als Besitzer der Herde."


def _codes(source: str, translated: str, scripture=()) -> list[str]:
    return [
        issue.code
        for issue in validate_translation(
            source=source, translated=translated, source_locale="en", target_locale="de", scripture=scripture
        )
    ]


def test_the_live_row_was_parked_without_being_told_about_the_verse() -> None:
    assert "proper_name_substituted" in _codes(_SOURCE + " This verse names Jethro.", _TRANSLATION)


def test_a_name_inside_the_editions_verse_is_not_a_swap() -> None:
    codes = _codes(_SOURCE + " This verse names Jethro.", _TRANSLATION, scripture=[(_QUOTED, _VERSE)])
    assert "proper_name_substituted" not in codes


def test_a_swap_outside_the_verse_is_still_a_swap() -> None:
    """The commentary around the verse is the model's, and is read as before."""
    translation = f"Exodus 3,1 besagt: „{_VERSE}.“ Dieser Vers nennt Horeb als Besitzer der Herde."
    codes = _codes(_SOURCE + " This verse names Jethro as the owner.", translation, scripture=[(_QUOTED, _VERSE)])
    assert "proper_name_substituted" in codes


def test_a_verse_that_is_not_in_the_text_changes_nothing() -> None:
    """A verse the provider could not find word for word is not masked."""
    elsewhere = [(_QUOTED, "Ein ganz anderer Vers, der nirgends steht")]
    assert _codes(_SOURCE + " This verse names Jethro.", _TRANSLATION, scripture=elsewhere) == _codes(
        _SOURCE + " This verse names Jethro.", _TRANSLATION
    )


class TestWhatTheProviderReports:
    """``_editions_verses`` reports a verse only when it is there as printed."""

    def _run(self, monkeypatch, text: str, lost: list[str]):
        from app.services.bible.references import BibleRef
        from app.services.bible.substitution import Substitution
        from app.services.translation import gemini

        monkeypatch.setattr(gemini, "canonical_for_display", lambda ref, locale: _VERSE + ".")
        sub = Substitution(
            marker="EQV0123456789abcdef",
            ref=BibleRef("exodus", 3, 1),
            original_inner=_QUOTED,
            ref_tail="",
            opening_quote_lost=True,
            closing_quote_lost=True,
        )
        return gemini._editions_verses([sub], text, "de", lost)

    def test_found_word_for_word(self, monkeypatch) -> None:
        assert self._run(monkeypatch, _TRANSLATION, []) == ((_QUOTED, _VERSE),)

    def test_a_dropped_marker_put_nothing_in(self, monkeypatch) -> None:
        assert self._run(monkeypatch, _TRANSLATION, ["EQV0123456789abcdef"]) == ()

    def test_not_in_the_text(self, monkeypatch) -> None:
        assert self._run(monkeypatch, "Exodus 3,1 besagt etwas anderes.", []) == ()
