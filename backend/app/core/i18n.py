# ruff: noqa: RUF001
# This module is four languages of user-facing strings; Cyrillic
# letters that look like Latin ones are the content, not a slip.
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

from app.schemas.locale import LOCALE_CODES, LocaleCode, normalize_locale

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
        "email.invitation.subject": "You're invited to join {brand} as a {role}",
        "email.invitation.heading": "You're invited to {brand}",
        "email.invitation.body": "You've been invited to join {brand} as a {role}. Click below to accept the invitation and set up your account.",
        "email.invitation.cta": "Accept invitation",
        "email.invitation.footer": "This invitation expires in 7 days. If you weren't expecting this, you can safely ignore this email.",
        "role.teacher": "teacher",
        "role.student": "student",
        "notif.new_announcement.title": "New Announcement",
        "notif.new_announcement.body": "{title} — in «{course}»",
        "notif.cert_approved.title": "Certificate Approved",
        "notif.cert_approved.body": 'Your certificate for "{course}" has been approved!',
        "notif.cert_rejected.title": "Certificate Rejected",
        "notif.cert_rejected.body": 'Your certificate request for "{course}" was rejected.',
        "notif.assignment_graded.title": "Assignment graded",
        "notif.assignment_graded.body": 'Your submission for "{title}" has been graded: {grade}/{max_score}.',
        "notif.retake_requested.title": "Retake requested",
        "notif.retake_requested.body": "{student} is asking for a chance to retake work in «{course}».",
        "fallback.your_assignment": "your assignment",
        "fallback.announcement": "an announcement",
        "fallback.course": "a course",
        "fallback.your_course": "your course",
    },
    "ru": {
        "email.invitation.subject": "Вас приглашают в {brand} — роль: {role}",
        "email.invitation.heading": "Вас приглашают в {brand}",
        "email.invitation.body": "Вас пригласили в {brand}. Ваша роль — {role}. Нажмите кнопку ниже, чтобы принять приглашение и настроить учётную запись.",
        "email.invitation.cta": "Принять приглашение",
        "email.invitation.footer": "Приглашение действует 7 дней. Если вы его не ждали, просто не отвечайте на это письмо.",
        "role.teacher": "преподаватель",
        "role.student": "студент",
        "notif.new_announcement.title": "Новое объявление",
        "notif.new_announcement.body": "{title} — в «{course}»",
        "notif.cert_approved.title": "Сертификат одобрен",
        "notif.cert_approved.body": "Ваш сертификат за «{course}» одобрен!",
        "notif.cert_rejected.title": "Сертификат отклонён",
        "notif.cert_rejected.body": "Ваша заявка на сертификат за «{course}» отклонена.",
        "notif.assignment_graded.title": "Работа проверена",
        "notif.assignment_graded.body": "Ваша работа «{title}» проверена: {grade} из {max_score}.",
        "notif.retake_requested.title": "Просят пересдачу",
        "notif.retake_requested.body": "{student} просит о пересдаче в курсе «{course}».",
        "fallback.your_assignment": "ваша работа",
        "fallback.announcement": "объявление",
        "fallback.course": "курс",
        "fallback.your_course": "ваш курс",
    },
    "de": {
        "email.invitation.subject": "Sie sind zu {brand} eingeladen — als {role}",
        "email.invitation.heading": "Sie sind zu {brand} eingeladen",
        "email.invitation.body": "Sie wurden eingeladen, {brand} als {role} beizutreten. Klicken Sie unten, um die Einladung anzunehmen und Ihr Konto einzurichten.",
        "email.invitation.cta": "Einladung annehmen",
        "email.invitation.footer": "Diese Einladung gilt 7 Tage. Wenn Sie sie nicht erwartet haben, können Sie diese E-Mail einfach ignorieren.",
        "role.teacher": "Dozent",
        "role.student": "Studierende Person",
        "notif.new_announcement.title": "Neue Ankündigung",
        "notif.new_announcement.body": "{title} — in „{course}“",
        "notif.cert_approved.title": "Zertifikat bestätigt",
        "notif.cert_approved.body": "Ihr Zertifikat für „{course}“ wurde bestätigt!",
        "notif.cert_rejected.title": "Zertifikat abgelehnt",
        "notif.cert_rejected.body": "Ihr Antrag auf ein Zertifikat für „{course}“ wurde abgelehnt.",
        "notif.assignment_graded.title": "Aufgabe bewertet",
        "notif.assignment_graded.body": "Ihre Abgabe „{title}“ wurde bewertet: {grade} von {max_score}.",
        "notif.retake_requested.title": "Wiederholung angefragt",
        "notif.retake_requested.body": "{student} bittet um eine Wiederholung im Kurs „{course}“.",
        "fallback.your_assignment": "Ihre Aufgabe",
        "fallback.announcement": "eine Ankündigung",
        "fallback.course": "ein Kurs",
        "fallback.your_course": "Ihr Kurs",
    },
    "uk": {
        "email.invitation.subject": "Вас запрошують до {brand} — роль: {role}",
        "email.invitation.heading": "Вас запрошують до {brand}",
        "email.invitation.body": "Вас запросили приєднатися до {brand}. Ваша роль — {role}. Натисніть кнопку нижче, щоб прийняти запрошення і налаштувати обліковий запис.",
        "email.invitation.cta": "Прийняти запрошення",
        "email.invitation.footer": "Запрошення дійсне 7 днів. Якщо ви його не очікували, просто не відповідайте на цей лист.",
        "role.teacher": "викладач",
        "role.student": "студент",
        "notif.new_announcement.title": "Нове оголошення",
        "notif.new_announcement.body": "{title} — у «{course}»",
        "notif.cert_approved.title": "Сертифікат схвалено",
        "notif.cert_approved.body": "Ваш сертифікат за «{course}» схвалено!",
        "notif.cert_rejected.title": "Сертифікат відхилено",
        "notif.cert_rejected.body": "Вашу заявку на сертифікат за «{course}» відхилено.",
        "notif.assignment_graded.title": "Роботу перевірено",
        "notif.assignment_graded.body": "Вашу роботу «{title}» перевірено: {grade} з {max_score}.",
        "notif.retake_requested.title": "Просять перескладання",
        "notif.retake_requested.body": "{student} просить про перескладання в курсі «{course}».",
        "fallback.your_assignment": "ваша робота",
        "fallback.announcement": "оголошення",
        "fallback.course": "курс",
        "fallback.your_course": "ваш курс",
    },
}


#: The block every lookup falls through to. English, and named here rather
#: than reached through ``DEFAULT_LOCALE`` so the two facts stay separable:
#: this one is "the catalogue that is guaranteed complete" — the same
#: reference role English plays in ``frontend/scripts/i18n-check.mjs``,
#: where ``REFERENCE = "en"`` — and it stays English even if the platform's
#: last resort were ever to move again.
_FALLBACK_CATALOG: Final[dict[str, str]] = _CATALOG["en"]


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
    # ``_CATALOG.get(normalized, {})`` rather than a whole-catalog default.
    # This line read ``or _CATALOG[DEFAULT_LOCALE]``, and while that constant
    # was ``"ru"`` it quietly broke the promise two paragraphs up: a locale
    # with no catalog took the Russian block entire, found the key there, and
    # never reached the English branch below — ``t("es", ...)`` answered a
    # Spanish speaker in Russian. Missing the catalog and missing the key are
    # the same situation ("we do not have this in your language") and both now
    # land in the same place: English, the one block guaranteed complete.
    catalog = _CATALOG.get(normalized, {})
    template = catalog.get(key) or _FALLBACK_CATALOG.get(key) or key
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
