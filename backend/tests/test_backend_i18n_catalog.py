"""Catalog-coverage regression for ``app.core.i18n``.

These tests pin two architectural invariants:

1. Every locale registered in ``LOCALE_CODES`` MUST appear in the
   backend i18n catalog. Otherwise a recipient whose
   ``preferred_locale`` is registered but unmapped would silently fall
   back to English, undoing the whole reason the catalog exists.

2. Every key in the catalog MUST exist for every locale. Otherwise a
   partial translation deployment would mix English and the target
   locale at random within one notification body.

Adding a new locale or a new key trips one of these tests until every
block is updated — which is exactly the forcing function we want.
"""

from __future__ import annotations

from app.core.i18n import _CATALOG, catalog_keys, t
from app.schemas.locale import LOCALE_CODES, LOCALE_DISPLAY_NAMES


def test_catalog_covers_every_registered_locale():
    missing = [code for code in LOCALE_CODES if code not in _CATALOG]
    assert not missing, (
        "Every locale in LOCALE_CODES must have an entry in _CATALOG. "
        f"Missing: {missing}. Add a key block to ``app/core/i18n.py``."
    )


def test_every_locale_has_every_key():
    union = catalog_keys()
    drift: dict[str, set[str]] = {}
    for locale, entries in _CATALOG.items():
        missing_for_locale = union - entries.keys()
        if missing_for_locale:
            drift[locale] = missing_for_locale
    assert not drift, (
        "Every locale block in _CATALOG must share the same key set. "
        f"Missing per locale: {drift}. Add the missing keys to that "
        "locale block in ``app/core/i18n.py``."
    )


def test_locale_display_names_cover_every_locale():
    missing = [code for code in LOCALE_CODES if code not in LOCALE_DISPLAY_NAMES]
    assert not missing, (
        "LOCALE_DISPLAY_NAMES must have a human-readable label for "
        "every locale in LOCALE_CODES. Missing: "
        f"{missing}. Add to ``app/schemas/locale.py``."
    )


def test_a_recipient_whose_language_we_do_not_serve_is_written_to_in_english():
    # Caller passed a locale not registered in LOCALE_CODES — a
    # notification for somebody whose language this platform does not
    # have. They get English, which is what ``t``'s own docstring has
    # always promised.
    #
    # It did not do that. The lookup read
    # ``_CATALOG.get(normalized) or _CATALOG[DEFAULT_LOCALE]``, and with
    # that constant set to "ru" the unknown locale took the *Russian*
    # block whole, found the key in it, and never reached the English
    # branch: ``t("es", "notif.cert_approved.title")`` returned
    # 'Сертификат одобрен'. Measured, not hypothesised.
    assert t("fr", "notif.new_announcement.title") == _CATALOG["en"]["notif.new_announcement.title"]
    assert t("es", "notif.cert_approved.title") == "Certificate Approved"


def test_a_served_language_is_still_written_in_that_language():
    # The other half of the same rule: falling back to English must not
    # mean drifting to English. A recipient we *do* serve gets their own
    # catalog, untouched by any of the above.
    assert t("ru", "notif.cert_approved.title") == _CATALOG["ru"]["notif.cert_approved.title"]
    assert t("de", "notif.cert_approved.title") == _CATALOG["de"]["notif.cert_approved.title"]
    assert t("uk", "notif.cert_approved.title") == _CATALOG["uk"]["notif.cert_approved.title"]


def test_t_falls_back_to_english_on_unknown_key():
    # Unknown key returns the literal key (so a missing translation in
    # prod surfaces as visible "notif.something" instead of an empty
    # cell).
    assert t("ru", "this.key.does.not.exist") == "this.key.does.not.exist"


def test_t_formats_placeholders():
    rendered = t(
        "ru",
        "notif.new_announcement.body",
        title="Привет",
        course="Курс",  # noqa: RUF001
    )
    assert rendered == "Привет — в «Курс»"  # noqa: RUF001


def test_t_returns_template_when_no_kwargs():
    # Calling without kwargs returns the template verbatim — useful
    # for keys that have no placeholders (titles, fixed labels).
    assert t("en", "notif.cert_approved.title") == "Certificate Approved"
