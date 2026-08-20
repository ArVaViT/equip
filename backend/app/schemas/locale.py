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
  5. Nothing. Existing content re-translates itself.

     This step used to read "trigger ``POST /courses/{id}/translate``
     on every published course, or wait for the next teacher save" —
     a list somebody maintains by hand, which is fine for three
     courses and impossible for a thousand. The sweep in
     ``services/translation/reconciler.py`` now re-examines the least
     recently checked live courses a few per worker tick, and every
     course missing the new locale is queued without anyone asking.
     A catalogue of a thousand comes round in about five hours.

     Platform content that belongs to no course is swept too: the
     Daily Challenge rotation nightly and on every idle worker tick
     (``services/daily_challenge/translate.py``), and the site-wide
     announcement banner through ``sweep_global_announcements`` in
     ``services/translation/reconciler.py``.

     What still needs a person, and why: steps 2 and 4 are the
     interface catalogs, which are product copy rather than course
     content — a wrong word in a lesson is a bad translation, a wrong
     word on a button is a bug. ``scripts/translate_catalog.py``
     drafts them so the work is reviewing rather than typing.
"""

from __future__ import annotations

from typing import Final, Literal

LocaleCode = Literal["ru", "en", "de", "uk"]

LOCALE_CODES: Final[tuple[LocaleCode, ...]] = ("ru", "en", "de", "uk")

#: The last resort: what a request is answered in when nothing in it says
#: who is asking — no profile, and an ``Accept-Language`` naming only
#: languages this platform does not serve.
#:
#: It was ``"ru"``, set when the platform was Russian-only and "the language
#: we fall back to" and "the language the content is written in" were the
#: same fact. They stopped being the same fact the day a second language
#: shipped, and the constant never moved. A reader whose browser asks for
#: French is not a Russian speaker — they are somebody we know nothing
#: about, and the language to answer an unknown reader in is English.
#:
#: What this is **not**: it is not ``courses.source_locale`` (courses are
#: authored in Russian and translated out of it — see
#: ``models/course.py``), and it is not the content fallback in
#: ``services/content_versions/read.py`` (an untranslated lesson correctly
#: falls back to the text it was written in). Both of those are still
#: Russian and must stay that way.
DEFAULT_LOCALE: Final[LocaleCode] = "en"

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


# The pair of marks each language sets a quotation in. Two callers need
# the same answer and must not disagree: ``translation/typography.py``
# re-points the marks a translation came back with, and
# ``bible/substitution.py`` puts back the ones a canonical verse was
# quoted in before the substitution layer swallowed them. A table they
# both read is why "the marks the language uses" means one thing.
#
# English is *straight*, and that is a decision rather than an oversight
# — ``typography.py::_english_quote`` records why: straightening is a
# total mapping that cannot be got backwards, and the corpus is already
# 662 straight double quotes against 49 curly.
#
# ``test_a_quoted_verse_comes_back_quoted`` fails when a locale is added
# here and forgotten, the same guard the display-name table gets.
QUOTATION_MARKS: Final[dict[LocaleCode, tuple[str, str]]] = {
    "ru": ("«", "»"),
    "uk": ("«", "»"),
    "de": ("„", "“"),
    "en": ('"', '"'),
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
