"""Backend-side i18n catalog for strings the server must localize before
the frontend gets a chance to.

Why this exists
---------------
Most user-visible text lives in ``frontend/src/i18n/locales/<code>.json``
and is rendered by react-i18next. The server only stays out of i18n
when it can: every entity-owned string (titles, descriptions, content)
travels through ``content_versions`` and the user's UI locale resolves
the right row at read time.

But two flows force the **server** to pick a locale BEFORE the response
ships:

1. **Notification fan-out.** When a teacher posts an announcement, the
   server writes a ``new_announcement`` row per enrolled student with
   the ``title`` and ``message`` columns already populated. The
   notification feed renders those columns verbatim — there is no
   server round trip when the user later opens their bell. So the
   message text has to land in the recipient's preferred locale at
   write time.

2. **Certificate notifications.** Same shape — approval / rejection
   notifications fan out with a hardcoded title and a message that
   embeds the course title.

Before this module those localized strings lived in per-route helper
functions (``_localize_announcement_notification``,
``_localize_cert_notification``) that hardcoded ``if locale == 'ru'`` /
``else`` branches. Adding a third locale meant editing every helper
and remembering every key. This catalog inverts that: every locale's
keys live in one place, and CI enforces parity (see
``tests/test_backend_i18n_catalog.py``).

Adding a new locale
-------------------
Append a key block to ``_CATALOG`` with the same key set as the other
locales. The regression test ``test_i18n_catalog_covers_every_locale``
fails otherwise. The ``t()`` helper falls back to ``en`` for any
missing key so a partial deployment never crashes the request — but
the test catches partial deployments at PR time.

Adding a new key
----------------
Add it to every locale block, then call ``t(recipient_locale, key,
**format_args)`` at the use site. The test also catches missing keys.
"""

from __future__ import annotations

from typing import Final

from app.schemas.locale import DEFAULT_LOCALE, LOCALE_CODES, LocaleCode, normalize_locale

# Single source of truth for every backend-rendered string. Keys use
# dot-notation by feature (``notif.<type>.<title|body>``,
# ``fallback.<noun>``) so a future contributor can find related keys
# quickly. Every locale block MUST share the same key set — the
# ``test_i18n_catalog_covers_every_locale`` regression catches drift.
#
# Format strings use ``str.format`` placeholders (``{title}``,
# ``{course}``). Reordering is fine; renaming a placeholder is a
# breaking change that needs every locale touched in the same PR.
_CATALOG: Final[dict[LocaleCode, dict[str, str]]] = {
    "en": {
        "notif.new_announcement.title": "New Announcement",
        "notif.new_announcement.body": "{title} — in «{course}»",
        "notif.cert_approved.title": "Certificate Approved",
        "notif.cert_approved.body": 'Your certificate for "{course}" has been approved!',
        "notif.cert_rejected.title": "Certificate Rejected",
        "notif.cert_rejected.body": 'Your certificate request for "{course}" was rejected.',
        "fallback.course": "a course",
        "fallback.your_course": "your course",
    },
    "ru": {
        "notif.new_announcement.title": "Новое объявление",
        "notif.new_announcement.body": "{title} — в «{course}»",
        "notif.cert_approved.title": "Сертификат одобрен",
        "notif.cert_approved.body": "Ваш сертификат за «{course}» одобрен!",
        "notif.cert_rejected.title": "Сертификат отклонён",
        "notif.cert_rejected.body": "Ваша заявка на сертификат за «{course}» отклонена.",
        "fallback.course": "курс",
        "fallback.your_course": "ваш курс",
    },
}


def t(locale: str | None, key: str, /, **kwargs: str) -> str:
    """Resolve ``key`` in ``locale``'s catalog and format with ``kwargs``.

    ``locale`` may be any string the route receives (Accept-Language
    header value, ``user.preferred_locale``, etc); it's normalized via
    ``normalize_locale`` before lookup. Unsupported locales fall back
    to ``DEFAULT_LOCALE``.

    Unknown keys fall back to the English catalog and then to the
    literal key. The lookup never crashes the request; the
    catalog-coverage test is what guarantees no key reaches prod
    without a translation in every supported locale.
    """
    normalized = normalize_locale(locale)
    catalog = _CATALOG.get(normalized) or _CATALOG[DEFAULT_LOCALE]
    template = catalog.get(key) or _CATALOG["en"].get(key) or key
    if not kwargs:
        return template
    return template.format(**kwargs)


def catalog_keys() -> set[str]:
    """Return the union of keys across every locale catalog.

    Used by ``tests/test_backend_i18n_catalog.py`` — the test
    re-derives the key set per locale and asserts no diff against this
    union.
    """
    keys: set[str] = set()
    for entries in _CATALOG.values():
        keys.update(entries.keys())
    return keys


__all__ = ["LOCALE_CODES", "catalog_keys", "t"]
