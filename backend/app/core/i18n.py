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
        "email.invitation.subject": "You are invited to {title}",
        "email.invitation.subject.course": "Invitation to {title}",
        "email.invitation.eyebrow.course": "Course invitation",
        "email.invitation.eyebrow.organization": "You are invited",
        "email.invitation.eyebrow.platform": "You are invited",
        "email.invitation.lede.course": "{inviter} invites you to study at {org}.",
        "email.invitation.lede.organization": "{inviter} invites you to join, as a {role}.",
        "email.invitation.lede.platform": "{inviter} invites you to {brand}, as a {role}.",
        "email.invitation.fact.lessons": "Lessons",
        "email.invitation.fact.role": "Your role",
        "email.invitation.cta": "Accept invitation",
        "email.invitation.preview": "You are invited to {title}. The link is in this email.",
        "email.invitation.expires": "The link works until {date}. It creates your account and takes you straight in.",
        "email.invitation.ignore": "If you were not expecting this, simply do not reply.",
        "email.invitation.footer": "Equip — a platform for Bible schools.",
        "role.teacher": "teacher",
        "role.student": "student",
        "notif.new_announcement.title": "New Announcement",
        "notif.new_announcement.body": "{title} — in «{course}»",
        "notif.new_event.title": "New event in your course",
        "notif.new_event.body": "{kind}: {title} — in «{course}». The date and time are in your calendar.",
        "notif.event_rescheduled.title": "Event moved",
        "notif.event_rescheduled.body": "{kind}: {title} — in «{course}». Check the new date and time in your calendar.",
        "event_type.deadline": "Deadline",
        "event_type.live_session": "Live session",
        "event_type.exam": "Exam",
        "event_type.other": "Event",
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
        "fallback.event": "an event",
        "fallback.course": "a course",
        "fallback.your_course": "your course",
    },
    "ru": {
        "email.invitation.subject": "Вас приглашают: {title}",
        "email.invitation.subject.course": "Приглашение на курс «{title}»",
        "email.invitation.eyebrow.course": "Приглашение на курс",
        "email.invitation.eyebrow.organization": "Вас приглашают",
        "email.invitation.eyebrow.platform": "Вас приглашают",
        "email.invitation.lede.course": "{inviter} приглашает вас учиться в школе {org}.",
        "email.invitation.lede.organization": "{inviter} приглашает вас присоединиться в роли: {role}.",
        "email.invitation.lede.platform": "{inviter} приглашает вас в {brand} в роли: {role}.",
        "email.invitation.fact.lessons": "Уроков",
        "email.invitation.fact.role": "Ваша роль",
        "email.invitation.cta": "Принять приглашение",
        "email.invitation.preview": "Вас приглашают: {title}. Ссылка — в этом письме.",
        "email.invitation.expires": "Ссылка действует до {date}. По ней вы создадите учётную запись и сразу попадёте внутрь.",
        "email.invitation.ignore": "Если приглашения вы не ждали — просто не отвечайте на это письмо.",
        "email.invitation.footer": "Equip — платформа библейских школ.",
        "role.teacher": "преподаватель",
        "role.student": "студент",
        "notif.new_announcement.title": "Новое объявление",
        "notif.new_announcement.body": "{title} — в «{course}»",
        "notif.new_event.title": "Новое событие в курсе",
        "notif.new_event.body": "{kind}: {title} — в «{course}». Дата и время — в вашем календаре.",
        "notif.event_rescheduled.title": "Событие перенесено",
        "notif.event_rescheduled.body": "{kind}: {title} — в «{course}». Новая дата и время — в вашем календаре.",
        "event_type.deadline": "Дедлайн",
        "event_type.live_session": "Прямая сессия",
        "event_type.exam": "Экзамен",
        "event_type.other": "Событие",
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
        "fallback.event": "событие",
        "fallback.course": "курс",
        "fallback.your_course": "ваш курс",
    },
    "de": {
        "email.invitation.subject": "Sie sind eingeladen: {title}",
        "email.invitation.subject.course": "Einladung zum Kurs «{title}»",
        "email.invitation.eyebrow.course": "Kurseinladung",
        "email.invitation.eyebrow.organization": "Sie sind eingeladen",
        "email.invitation.eyebrow.platform": "Sie sind eingeladen",
        "email.invitation.lede.course": "{inviter} lädt Sie ein, an der Schule {org} zu lernen.",
        "email.invitation.lede.organization": "{inviter} lädt Sie ein, als {role} beizutreten.",
        "email.invitation.lede.platform": "{inviter} lädt Sie zu {brand} ein, als {role}.",
        "email.invitation.fact.lessons": "Lektionen",
        "email.invitation.fact.role": "Ihre Rolle",
        "email.invitation.cta": "Einladung annehmen",
        "email.invitation.preview": "Sie sind eingeladen: {title}. Der Link steht in dieser E-Mail.",
        "email.invitation.expires": "Der Link gilt bis {date}. Er legt Ihr Konto an und führt Sie direkt hinein.",
        "email.invitation.ignore": "Wenn Sie das nicht erwartet haben, antworten Sie einfach nicht.",
        "email.invitation.footer": "Equip — eine Plattform für Bibelschulen.",
        "role.teacher": "Dozent",
        "role.student": "Studierende Person",
        "notif.new_announcement.title": "Neue Ankündigung",
        "notif.new_announcement.body": "{title} — in „{course}“",
        "notif.new_event.title": "Neuer Termin in Ihrem Kurs",
        "notif.new_event.body": "{kind}: {title} — in „{course}“. Datum und Uhrzeit finden Sie in Ihrem Kalender.",
        "notif.event_rescheduled.title": "Termin verschoben",
        "notif.event_rescheduled.body": "{kind}: {title} — in „{course}“. Das neue Datum und die Uhrzeit finden Sie in Ihrem Kalender.",
        "event_type.deadline": "Frist",
        "event_type.live_session": "Live-Termin",
        "event_type.exam": "Prüfung",
        "event_type.other": "Termin",
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
        "fallback.event": "ein Termin",
        "fallback.course": "ein Kurs",
        "fallback.your_course": "Ihr Kurs",
    },
    "uk": {
        "email.invitation.subject": "Вас запрошують: {title}",
        "email.invitation.subject.course": "Запрошення на курс «{title}»",
        "email.invitation.eyebrow.course": "Запрошення на курс",
        "email.invitation.eyebrow.organization": "Вас запрошують",
        "email.invitation.eyebrow.platform": "Вас запрошують",
        "email.invitation.lede.course": "{inviter} запрошує вас навчатися у школі {org}.",
        "email.invitation.lede.organization": "{inviter} запрошує вас приєднатися у ролі: {role}.",
        "email.invitation.lede.platform": "{inviter} запрошує вас до {brand} у ролі: {role}.",
        "email.invitation.fact.lessons": "Уроків",
        "email.invitation.fact.role": "Ваша роль",
        "email.invitation.cta": "Прийняти запрошення",
        "email.invitation.preview": "Вас запрошують: {title}. Посилання — у цьому листі.",
        "email.invitation.expires": "Посилання діє до {date}. За ним ви створите обліковий запис і одразу потрапите всередину.",
        "email.invitation.ignore": "Якщо ви не чекали на запрошення — просто не відповідайте на цей лист.",
        "email.invitation.footer": "Equip — платформа біблійних шкіл.",
        "role.teacher": "викладач",
        "role.student": "студент",
        "notif.new_announcement.title": "Нове оголошення",
        "notif.new_announcement.body": "{title} — у «{course}»",
        "notif.new_event.title": "Нова подія в курсі",
        "notif.new_event.body": "{kind}: {title} — у «{course}». Дата й час — у вашому календарі.",
        "notif.event_rescheduled.title": "Подію перенесено",
        "notif.event_rescheduled.body": "{kind}: {title} — у «{course}». Нова дата й час — у вашому календарі.",
        "event_type.deadline": "Термін",
        "event_type.live_session": "Жива зустріч",
        "event_type.exam": "Іспит",
        "event_type.other": "Подія",
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
        "fallback.event": "подія",
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
