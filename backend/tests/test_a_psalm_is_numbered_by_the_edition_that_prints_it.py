# ruff: noqa: RUF001
# Cyrillic book abbreviations and the numbers beside them are the subject
# matter here, not typos.
"""The validator blocked the psalm reference that was right and passed the one that was wrong.

The Synodal Psalter runs one behind every other edition this platform
serves for most of the book — Synodal 109 is 110 everywhere else — and
``app.services.bible.psalm_numbering`` has known that since 2026-08-16.
Rule 2a of the system prompt tells the model to rewrite a reference in
the form the target-language Bible prints. It does.

``_check_verse_refs`` then compared the bare digits of the two sides and
called the correctly renumbered reference a lost one. Found on
2026-08-19 in production, entity ``c18954e1-6652-4fa8-8062-538483ce789b``,
field ``chapter_block/content``: the Russian source cites Пс. 109:1, the
German row prints Ps. 110,1 and sat at ``needs_review``; the English and
Ukrainian rows kept 109:1, point their readers at Psalm 109 — a
different psalm — and were marked ``ok``.

The blocking half is what costs a course. ``executor`` skips a parked
row whose source hash has not moved, and the reconciler then reads the
course as waiting on a person and stops queueing it, so a row parked for
being right is parked for good.
"""

from __future__ import annotations

from app.services.bible.psalm_numbering import renumber_between
from app.services.bible.references import BibleRef
from app.services.translation.validation import ValidationIssue, validate_translation


def codes(issues: list[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues}


def blocking(issues: list[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues if issue.blocking}


class TestTheCorrectlyRenumberedReferenceIsNotLost:
    def test_a_russian_psalm_reprinted_in_german_numbers_passes(self):
        # The production row. Synodal 109:1 is Luther 110,1.
        issues = validate_translation(
            source="<p>Как сказано в Пс. 109:1, Господь сказал Господу моему: сиди одесную Меня.</p>",
            translated="<p>Wie es in Ps. 110,1 heißt, sprach der HERR zu meinem Herrn: Setze dich zu meiner Rechten.</p>",
            source_locale="ru",
            target_locale="de",
        )
        assert blocking(issues) == set()

    def test_an_english_psalm_reprinted_in_synodal_numbers_passes(self):
        # And the other direction, which is the one the rest of the
        # platform already handles: Hebrew 110:1 is Synodal 109:1.
        issues = validate_translation(
            source="<p>As Psalm 110:1 says, the LORD said to my Lord: sit at my right hand.</p>",
            translated="<p>Как говорит Пс. 109:1, сказал Господь Господу моему: седи одесную Меня.</p>",
            source_locale="en",
            target_locale="ru",
        )
        assert blocking(issues) == set()

    def test_two_hebrew_numbered_editions_still_have_to_agree(self):
        # Neither German nor English is Septuagint-numbered, so nothing
        # is remapped between them and a changed digit is a real change.
        issues = validate_translation(
            source="<p>As Psalm 110:1 says, the LORD said to my Lord: sit at my right hand today.</p>",
            translated="<p>Wie Ps. 109,1 sagt, sprach der HERR zu meinem Herrn: Setze dich zu meiner Rechten.</p>",
            source_locale="en",
            target_locale="de",
        )
        assert "verse_reference_lost" in blocking(issues)


class TestTheReferenceThatKeptTheWrongNumbers:
    """The other half of the same defect, and the reason the fix is not
    simply "accept both numberings and move on"."""

    def test_a_synodal_number_left_standing_in_english_is_reported(self):
        issues = validate_translation(
            source="<p>Как сказано в Пс. 109:1, Господь сказал Господу моему: сиди одесную Меня.</p>",
            translated="<p>As Ps. 109:1 says, the LORD said to my Lord: sit at my right hand today.</p>",
            source_locale="ru",
            target_locale="en",
        )
        assert "psalm_numbering_not_localised" in codes(issues)

    def test_and_it_does_not_park_the_row(self):
        # Non-blocking on purpose. The premise — that a Russian source
        # carries Synodal numbers — is inferred from its locale, and an
        # author who copied a reference out of an English commentary
        # breaks the inference. A guess earns a second pass; it does not
        # withhold a lesson.
        issues = validate_translation(
            source="<p>Как сказано в Пс. 109:1, Господь сказал Господу моему: сиди одесную Меня.</p>",
            translated="<p>As Ps. 109:1 says, the LORD said to my Lord: sit at my right hand today.</p>",
            source_locale="ru",
            target_locale="en",
        )
        assert blocking(issues) == set()


class TestARealLossIsStillARealLoss:
    def test_a_psalm_reference_that_vanished_is_caught(self):
        issues = validate_translation(
            source="<p>Как сказано в Пс. 109:1, Господь сказал Господу моему: сиди одесную Меня.</p>",
            translated="<p>Wie es an jener Stelle heißt, sprach der HERR zu meinem Herrn: Setze dich zu mir.</p>",
            source_locale="ru",
            target_locale="de",
        )
        assert "verse_reference_lost" in blocking(issues)

    def test_a_book_that_is_not_the_psalter_is_not_renumbered(self):
        # Only the Psalms are numbered twice. Genesis 1:26 is 1:26 in
        # every edition served here, so an off-by-one there is a defect.
        issues = validate_translation(
            source="<p>Прочитайте Бытие 1:26 и запишите свои наблюдения об образе Божьем.</p>",
            translated="<p>Lesen Sie 1. Mose 1,27 und notieren Sie Ihre Beobachtungen zum Bilde Gottes.</p>",
            source_locale="ru",
            target_locale="de",
        )
        assert "verse_reference_lost" in blocking(issues)


class TestRenumberBetween:
    """The mapping itself, apart from the validator that uses it."""

    def test_septuagint_source_to_hebrew_target(self):
        assert renumber_between(
            BibleRef("psalms", 109, 1),
            source_locale="ru",
            target_locale="de",
        ) == (BibleRef("psalms", 110, 1),)

    def test_hebrew_source_to_septuagint_target(self):
        assert renumber_between(
            BibleRef("psalms", 110, 1),
            source_locale="en",
            target_locale="ru",
        ) == (BibleRef("psalms", 109, 1),)

    def test_two_editions_on_the_same_side_change_nothing(self):
        ref = BibleRef("psalms", 110, 1)
        assert renumber_between(ref, source_locale="en", target_locale="uk") == (ref,)
        ref_ru = BibleRef("psalms", 109, 1)
        assert renumber_between(ref_ru, source_locale="ru", target_locale="ru") == (ref_ru,)

    def test_a_book_that_is_not_the_psalter_passes_through(self):
        ref = BibleRef("acts", 1, 8)
        assert renumber_between(ref, source_locale="ru", target_locale="de") == (ref,)

    def test_a_range_moves_with_its_ends(self):
        # The superscription is numbered in the Slavic tradition and not
        # in the Hebrew one, so the verse shifts as well as the chapter.
        assert renumber_between(
            BibleRef("psalms", 22, 1, 6),
            source_locale="ru",
            target_locale="en",
        ) == (BibleRef("psalms", 23, 1, 6),)

    def test_the_one_septuagint_verse_that_answers_to_two_hebrew_ones(self):
        # Hebrew 13:5 and 13:6 both land on Septuagint 12:6, so read
        # backwards that verse has two right answers and the caller is
        # handed both rather than a coin flip.
        assert renumber_between(
            BibleRef("psalms", 12, 6),
            source_locale="ru",
            target_locale="en",
        ) == (BibleRef("psalms", 13, 5), BibleRef("psalms", 13, 6))
