"""An author who stops quoting partway is still quoting that verse.

    Psalm 1:1 states, "Blessed is the man that walketh not in the
    counsel of the ungodly..."

Word for word the opening of the verse. Measured against the whole of
it, 0.61 — below the threshold — so the substitution was declined and
the model was left to translate Scripture itself. It rendered *in the
counsel of the ungodly* into Russian as «во тьме нечестивых», *in the
darkness of the wicked*, and a reader was served that as the Psalm.
German and Ukrainian got the same sentence right, which is what a
paraphrase looks like when it is nobody's edition: sometimes right.

The module already states this rule. ``_MAX_CANONICAL_HEAD`` measures
what stands *in front of* the author's words and declines a quotation
that starts late, and says in as many words that the tail is
deliberately not measured — a quotation that stops early is still the
beginning of the verse the citation names. The similarity ratio was the
one place that had not been told: it compared against the whole verse
and read a partial quotation as a poor match rather than a partial one.

Measured over the 1 687 live English sources on 2026-08-22: 81 match
the whole verse and substitute today, 28 more match its opening exactly,
and 25 are paraphrases that match neither. The paraphrases are the
population this must not touch, and the test for them is at the bottom.
"""

from __future__ import annotations

import pytest

from app.services.bible.substitution import _same_words

_PSALM_1_1 = (
    "Blessed is the man that walketh not in the counsel of the ungodly, "
    "nor standeth in the way of sinners, nor sitteth in the seat of the scornful."
)
_THRESHOLD = 0.80


class TestTheOpeningWordsOfAVerse:
    def test_the_live_psalm_quotation_is_recognised(self) -> None:
        """The row that started this. Under the old reading it scored
        0.61 and the verse was left to the model."""
        quoted = "Blessed is the man that walketh not in the counsel of the ungodly..."
        assert _same_words(quoted, _PSALM_1_1) >= _THRESHOLD

    @pytest.mark.parametrize(
        "quoted,canonical",
        [
            (
                "Now it came to pass in the days when the judges ruled, that there was a famine in the land.",
                "Now it came to pass in the days when the judges ruled, that there was a famine in the land. "
                "And a certain man of Bethlehemjudah went to sojourn in the country of Moab, he, and his wife, "
                "and his two sons.",
            ),
            (
                "There was a man in the land of Uz, whose name was Job.",
                "There was a man in the land of Uz, whose name was Job; and that man was perfect and upright, "
                "and one that feared God, and eschewed evil.",
            ),
            (
                "Blow ye the trumpet in Zion, and sound an alarm in my holy mountain.",
                "Blow ye the trumpet in Zion, and sound an alarm in my holy mountain: let all the inhabitants "
                "of the land tremble: for the day of the LORD cometh, for it is nigh at hand.",
            ),
        ],
    )
    def test_more_of_the_live_corpus(self, quoted: str, canonical: str) -> None:
        """Three of the twenty-one documents the change reaches, each one
        an exact opening followed by a full stop the author chose."""
        assert _same_words(quoted, canonical) >= _THRESHOLD

    def test_the_whole_verse_quoted_whole_still_scores(self) -> None:
        """The case that always worked, unchanged — a rule that improves
        the hard case and breaks the easy one is not an improvement."""
        assert _same_words(_PSALM_1_1, _PSALM_1_1) == 1.0


class TestWhatItMustNotReach:
    def test_a_paraphrase_is_still_declined(self) -> None:
        """The 25 rows that match neither the whole verse nor its opening.
        These are the reason the ratio exists at all."""
        assert _same_words("The psalmist teaches that the happy person avoids bad company.", _PSALM_1_1) < _THRESHOLD

    def test_the_middle_of_a_verse_is_not_its_opening(self) -> None:
        """A span lifted from inside the verse scores low as a prefix,
        which is what leaves ``_MAX_CANONICAL_HEAD`` free to be the thing
        that decides where the author began."""
        assert (
            _same_words("nor standeth in the way of sinners, nor sitteth in the seat of the scornful.", _PSALM_1_1)
            < _THRESHOLD
        )

    def test_a_different_verse_is_not_this_one(self) -> None:
        assert _same_words("In the beginning God created the heaven and the earth.", _PSALM_1_1) < _THRESHOLD

    def test_a_quotation_too_short_to_place_is_asked_the_whole_verse(self) -> None:
        """Under forty characters only the whole verse is asked. A handful
        of words matched against the first handful of a verse is mostly
        noise, and acting on it would paste a whole verse where a phrase
        stood."""
        assert _same_words("Blessed is the man", _PSALM_1_1) < _THRESHOLD

    def test_a_quotation_longer_than_the_verse_has_no_prefix_to_be(self) -> None:
        longer = _PSALM_1_1 + " And also he was a very fine fellow indeed, said the commentator at length."
        assert _same_words(longer, _PSALM_1_1) < 1.0
