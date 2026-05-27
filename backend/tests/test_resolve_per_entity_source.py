# ruff: noqa: RUF001
"""TDD spec: per-entity source-language detection at RESOLVE time.

Companion to PR #528 (per-entity detection at PIPELINE time). #528
makes the orchestrator create translation rows in the correct
direction when an entity is authored in a language different from
its course's declared source. This file pins the symmetric contract
on the display side: when a student requests a chapter whose actual
text is in a language different from the course's declared source,
the resolve path must honour the entity's actual language, not the
course's stated one.

The bug closed here:
  * course.source_locale='ru', chapter title base text='Welcome' (EN)
  * RU student visits → today: ``normalize_locale('ru') == display_locale 'ru'``
    short-circuit → returns base ``'Welcome'`` (English text shown
    to Russian user)
  * After this PR: ``detect_locale('Welcome') == 'en'`` ≠ ``'ru'`` →
    looks up overlay → returns Russian translation row (which #528's
    pipeline now correctly produces)

Tests are written BEFORE the resolve-side change — RED first.
"""

from __future__ import annotations

import pytest

from app.services.translation.resolve_for_display import pick_overlay_value


# Shorthand for the resolver: explicit kwargs in every test row for
# clarity; default empty overlay so each test composes only what it
# needs.
def _pick(
    base: str | None,
    *,
    source_locale: str = "ru",
    display_locale: str = "en",
    overlay: dict[tuple[str, str, str], str] | None = None,
    entity_type: str = "chapter",
    entity_id: str = "ent-1",
    field: str = "title",
) -> str | None:
    return pick_overlay_value(
        overlay or {},
        entity_type,
        entity_id,
        field,
        base,
        source_locale=source_locale,  # type: ignore[arg-type]
        display_locale=display_locale,  # type: ignore[arg-type]
    )


class TestResolveDetectsBaseTextLanguage:
    """The core contract: when the base text's actual language differs
    from the course's declared source_locale, the resolve path uses
    the detected language for the display-vs-source equality check.
    """

    def test_english_base_in_russian_course_shown_in_russian_returns_overlay(self):
        """The exact bug: a chapter authored in English inside a
        Russian-source course. RU student should get the RU overlay
        translation, not the EN base text."""
        overlay = {("chapter", "ent-1", "title"): "Перевод на русский"}
        # Source says ``ru`` (course's declaration), but actual base
        # text is English. Display is ``ru``. Today's broken behaviour:
        # source==display → return base ``Welcome to the chapter``.
        # After fix: detect base → en, en≠ru → return overlay.
        result = _pick(
            "Welcome to the chapter on Genesis",
            source_locale="ru",
            display_locale="ru",
            overlay=overlay,
        )
        assert result == "Перевод на русский"

    def test_english_base_in_russian_course_shown_in_english_returns_base(self):
        """EN student looking at the same chapter: detect → en, en==en →
        return base text (the English source), not the overlay."""
        # Even if a ``ru`` overlay row exists for the en student's
        # display key, the detection rules it out — but the lookup
        # is keyed on display_locale='en' so the ru-keyed overlay
        # wouldn't appear anyway. Test that the fast-path returns base.
        result = _pick(
            "Welcome to the chapter on Genesis",
            source_locale="ru",
            display_locale="en",
            overlay={},
        )
        assert result == "Welcome to the chapter on Genesis"

    def test_russian_base_in_english_course_shown_in_english_returns_overlay(self):
        """Symmetric case: RU chapter in EN-source course, EN student."""
        overlay = {("chapter", "ent-1", "title"): "English translation"}
        result = _pick(
            "Введение в книгу Бытия и её первую главу",
            source_locale="en",
            display_locale="en",
            overlay=overlay,
        )
        assert result == "English translation"

    def test_matched_base_and_display_returns_base(self):
        """No regression for the common case: course and chapter agree."""
        result = _pick(
            "Введение в книгу Бытия",
            source_locale="ru",
            display_locale="ru",
        )
        assert result == "Введение в книгу Бытия"


class TestResolveFallsBackToCourseSourceForAmbiguousText:
    """When the detector has no signal (empty, sub-threshold, pure
    punctuation), the resolve path falls back to the course's
    declared source_locale — same fallback contract the pipeline
    uses on the write side."""

    def test_empty_base_returns_none(self):
        """Existing contract preserved: empty base → None."""
        assert _pick(None, source_locale="ru", display_locale="en") is None

    def test_below_threshold_base_uses_declared_source(self):
        """A title like ``OK`` is below the 3-letter detection
        threshold. The detector returns None → fall back to
        ``source_locale`` for the equality check, matching the
        legacy behaviour for short titles."""
        # source ru, display en → returns base via overlay fallback
        result = _pick("OK", source_locale="ru", display_locale="en", overlay={})
        assert result == "OK"

    def test_below_threshold_base_in_matching_display_returns_base(self):
        # Below-threshold falls back to declared source. source==display
        # short-circuit kicks in.
        result = _pick("OK", source_locale="ru", display_locale="ru", overlay={})
        assert result == "OK"


class TestResolveExplicitOverlayWins:
    """When the lookup key IS in the overlay map AND detection
    confirms the base is in a DIFFERENT language than display, the
    overlay wins. This preserves the existing always-prefer-overlay
    rule for legitimate translations. The detection-based skip below
    is the ONLY case the overlay loses."""

    def test_overlay_wins_when_base_actually_differs_from_display(self):
        # Base is Russian, display is English: detection agrees that
        # we need a translation, overlay provides one → use it.
        overlay = {("chapter", "ent-1", "title"): "Explicit English translation"}
        result = _pick(
            "Длинный русский заголовок для теста",
            source_locale="ru",
            display_locale="en",
            overlay=overlay,
        )
        assert result == "Explicit English translation"


class TestResolveSkipsStaleWrongDirectionOverlay:
    """The bug this fix actually closes: pre-#528 rows where the
    pipeline ran with the wrong source direction and produced an
    overlay that, when served, gives the wrong language to the user.

    Concrete scenario: a chapter authored in English inside a
    course that was incorrectly marked source_locale='ru'. The
    pre-#528 pipeline read source='ru' and produced an overlay row
    for locale='en' that's actually... Russian text (because the
    pipeline tried to translate English-as-Russian into English and
    got noop / garbage). The English student then receives that
    stale row instead of the correct base text.

    After this fix, detection runs on the base text — when the
    detected language matches the display locale, we return the
    base text and skip the (provably stale) overlay.
    """

    def test_stale_wrong_direction_overlay_skipped_when_detection_matches_display(self):
        overlay = {("chapter", "ent-1", "title"): "Stale wrong-direction translation"}
        result = _pick(
            "Welcome to the chapter on Genesis",
            source_locale="ru",  # course's declaration is wrong
            display_locale="en",  # student is English
            overlay=overlay,
        )
        # Detected source = 'en' (the base IS English), display = 'en',
        # they match → return base, skip the stale overlay.
        assert result == "Welcome to the chapter on Genesis"

    def test_stale_overlay_skipped_in_russian_direction_too(self):
        overlay = {("chapter", "ent-1", "title"): "Stale wrong-direction translation"}
        result = _pick(
            "Длинное название главы на русском языке",
            source_locale="en",  # course's declaration is wrong
            display_locale="ru",  # student is Russian
            overlay=overlay,
        )
        # Detected ru == display ru → return base.
        assert result == "Длинное название главы на русском языке"


class TestResolveBackwardCompat:
    """The new behaviour is opt-in via detection; for entities whose
    base text agrees with the declared source (the entire production
    corpus today), nothing observable changes."""

    @pytest.mark.parametrize(
        "base,source,display,expected",
        [
            ("Russian title here", "ru", "ru", "Russian title here"),  # source match
            ("Some English title here", "en", "en", "Some English title here"),
            ("Russian title that's long enough", "ru", "en", "Russian title that's long enough"),
        ],
    )
    def test_no_overlay_returns_base(self, base: str, source: str, display: str, expected: str):
        result = _pick(base, source_locale=source, display_locale=display, overlay={})
        assert result == expected
