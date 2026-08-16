"""Locale primitives shared across schemas, services, and the translation
pipeline.

Adding a new language is a **five-step change** — all in this order:

  1. Append the code to ``LOCALE_CODES`` and the ``LocaleCode`` literal
     below. Add the human-readable name to ``LOCALE_DISPLAY_NAMES``
     (used by the translation prompt builder to address the model in
     a natural form: "translate from Russian to French").
  2. Add a key block for the new locale to
     ``app/core/i18n.py::_CATALOG`` with translations for every key.
     The ``test_i18n_catalog_covers_every_locale`` test would fail CI
     otherwise — so this step is enforced, not optional.
  3. Ship a Supabase migration that extends every ``CHECK`` constraint
     covering a locale column:
     * ``profiles.preferred_locale``
     * ``courses.source_locale``
     * ``content_versions.locale``  (the post Phase 5c store; the
       legacy ``content_translations`` table was dropped in 5aj)
  4. Add the frontend bundle ``frontend/src/i18n/locales/<code>.json``
     with full key coverage (the ``keyCoverage`` test enforces parity).
     Wire it into ``frontend/src/i18n/config.ts::SUPPORTED_LOCALES``.
  5. Re-translate existing content into the new locale by triggering
     ``POST /api/v1/courses/{id}/translate`` on every published course
     (or wait for the next teacher save — the orchestrator will run
     the new target automatically because ``other_locales`` derives
     from ``LOCALE_CODES``).
"""

from __future__ import annotations

from typing import Final, Literal

LocaleCode = Literal["ru", "en", "de", "uk"]

LOCALE_CODES: Final[tuple[LocaleCode, ...]] = ("ru", "en", "de", "uk")
DEFAULT_LOCALE: Final[LocaleCode] = "ru"

# Human-readable language names used by the translation prompt builder
# to address the upstream model ("translate from Russian to English").
# Keep keys aligned with ``LOCALE_CODES`` — the
# ``test_locale_display_names_cover_every_locale`` regression test
# catches drift.
LOCALE_DISPLAY_NAMES: Final[dict[LocaleCode, str]] = {
    "ru": "Russian",
    "en": "English",
    "de": "German",
    "uk": "Ukrainian",
}


def normalize_locale(value: str | None, *, fallback: LocaleCode = DEFAULT_LOCALE) -> LocaleCode:
    """Coerce arbitrary input to a supported locale.

    Accepts BCP-47-ish strings (``ru-RU``, ``en_US``) and degrades gracefully
    to ``fallback`` when the language is unsupported. Used both at API edges
    (Accept-Language header) and inside the translation pipeline.
    """
    if not value:
        return fallback

    # A real ``Accept-Language`` is a ranked list, not one tag:
    # ``de,en-US;q=0.7,en;q=0.3`` is what Firefox sends. Splitting the
    # whole header on the first "-" produced "de,en" — a language nobody
    # serves — and every such reader silently got the default. The web
    # app was unaffected because it sends a bare code, which is exactly
    # why this survived: the client that trusts the platform's own
    # convention was the one getting it wrong.
    #
    # Ranked in the order the client stated. ``q`` is deliberately not
    # parsed: browsers list their preference first, and a served language
    # further down the list is still a language this reader reads.
    for entry in value.split(","):
        tag = entry.split(";", 1)[0]
        head = tag.replace("_", "-").split("-", 1)[0].strip().lower()
        # Compare element-wise so the returned value is the typed
        # ``LocaleCode`` element from the tuple itself — no cast or
        # ``type: ignore`` needed, and mypy versions that narrow ``in``
        # checks won't flag a redundancy.
        for code in LOCALE_CODES:
            if head == code:
                return code
    return fallback
