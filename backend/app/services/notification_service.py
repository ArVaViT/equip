"""Notifications, and the language they are read in.

A notification used to be written once, in whatever language the writer
resolved at the time, and stored as finished text. That is wrong twice
over: it freezes the reader's language at the moment of the event, so
somebody who switches to German keeps a bell full of Russian, and it
means a defect in a template can never be fixed for rows already sent.

So a notification now carries its own recipe — the catalog key and the
values to fill it with — alongside the rendered text. The list route
renders it in the language the reader is asking in right now. The
stored text stays as the fallback for rows written before this, and as
a last resort if a key is ever removed from the catalog.

``meta`` carries it rather than a new column: it is already a JSON blob
on every row, and adding a column to a production table for the sake of
a nested dict is a migration nobody needs.
"""

import logging
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.i18n import t
from app.models.notification import Notification

logger = logging.getLogger(__name__)

#: Where the render recipe lives inside ``meta``.
I18N_KEY = "i18n"


#: A parameter that is itself a catalog key: ``{TRANSLATE: "event_type.exam"}``.
#: Stored like that it is translated when the row is shown, in the reader's
#: language at that moment — not frozen in the language they read when the
#: row was written. «Neues Ereignis: Экзамен „…“» after a switch to German
#: was the frozen kind (2026-09-29).
TRANSLATE = "$t"


#: A parameter that is a teacher's text — the title of an announcement or
#: an event — read when the row is shown, from released rows only:
#: ``{CONTENT: {"type": "announcement", "id": …, "field": "title",
#: "else": "fallback.announcement"}}``.
#:
#: It used to be resolved once, at fan-out, and frozen into the row. On a
#: live course a new post is not released until every language has it,
#: and the fan-out handed the reader of the author's language the author's
#: words from the staging table meanwhile — an early copy in one language,
#: which is exactly what the release rule forbids (the calendar tried the
#: same and was reverted, b38d7556). Frozen, the row then kept «an
#: announcement» for good once the title did come out. Read at render
#: time, it says «an announcement» until the title is released and the
#: title from then on, in whatever language the reader is in by then; a
#: held edit to a released title keeps the released wording until the
#: edit itself is out.
CONTENT = "$cv"

#: ``(entity_type, entity_id, field)`` — what a ``CONTENT`` parameter names.
ContentKey = tuple[str, str, str]


def translatable(key: str) -> dict[str, str]:
    """A parameter that is a catalog key, translated at render."""
    return {TRANSLATE: key}


def content_text(entity_type: str, entity_id: uuid.UUID | str, field: str, *, fallback_key: str) -> dict[str, Any]:
    """A parameter that is a teacher's text, read from released rows at
    render; ``fallback_key`` names it in the catalog until it is out."""
    return {CONTENT: {"type": entity_type, "id": str(entity_id), "field": field, "else": fallback_key}}


def _content_ref(value: Any) -> tuple[ContentKey, str] | None:
    ref = value.get(CONTENT) if isinstance(value, dict) else None
    if not isinstance(ref, dict):
        return None
    etype, eid, field, fallback_key = (ref.get("type"), ref.get("id"), ref.get("field"), ref.get("else"))
    if not (
        isinstance(etype, str) and isinstance(eid, str) and isinstance(field, str) and isinstance(fallback_key, str)
    ):
        return None
    return (etype, eid, field), fallback_key


def released_texts(db: Session, params_list: Iterable[Mapping[str, Any]], locale: str) -> dict[ContentKey, str]:
    """Every ``content_text`` parameter in ``params_list``, as a reader in
    ``locale`` may read it now: released rows only, never the staging
    table. One query per (type, field), however many rows ask.

    Nothing comes back for a text that has no released version in the
    reader's language — the render says its catalog name instead.
    """
    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    wanted: dict[tuple[str, str], set[str]] = {}
    for params in params_list:
        for value in params.values():
            found = _content_ref(value)
            if found is not None:
                (etype, eid, field), _ = found
                wanted.setdefault((etype, field), set()).add(eid)
    out: dict[ContentKey, str] = {}
    for (etype, field), ids in wanted.items():
        texts = fetch_cv_entity_texts_with_fallback(
            db,
            entity_type=etype,
            entity_ids=sorted(ids),
            fields=[field],
            display_locale=locale,
            # The reader's language is the only one they may be given; on a
            # deploy that does not translate, ``auto`` serves the one text
            # there is.
            source_locale=locale,
            include_author_edits=False,
        )
        for (eid, fld), text in texts.items():
            if text:
                out[(etype, eid, fld)] = text
    return out


def resolve_params(
    params: Mapping[str, Any], locale: str, texts: Mapping[ContentKey, str] | None = None
) -> dict[str, Any]:
    """Every ``translatable`` and ``content_text`` parameter in the
    reader's language. ``texts`` is what ``released_texts`` found; a
    teacher's text it does not have is named by its catalog fallback."""
    out: dict[str, Any] = {}
    for name, value in params.items():
        if isinstance(value, dict) and isinstance(value.get(TRANSLATE), str):
            out[name] = t(locale, value[TRANSLATE])
            continue
        found = _content_ref(value)
        if found is not None:
            key, fallback_key = found
            out[name] = (texts or {}).get(key) or t(locale, fallback_key)
            continue
        out[name] = value
    return out


def notification_text(key: str, **params: Any) -> dict[str, Any]:
    """The recipe for one notification's title and message.

    ``key`` is the catalog prefix — ``notif.assignment_graded`` resolves
    ``notif.assignment_graded.title`` and ``…​.body``.
    """
    return {"key": key, "params": params}


def _recipe(notification: Notification) -> tuple[str, dict[str, Any]] | None:
    recipe = (notification.meta or {}).get(I18N_KEY) if isinstance(notification.meta, dict) else None
    if not isinstance(recipe, dict) or not isinstance(recipe.get("key"), str):
        return None
    params = recipe.get("params") or {}
    return recipe["key"], params if isinstance(params, dict) else {}


def render_notifications(db: Session, notifications: Iterable[Notification], locale: str) -> list[tuple[str, str]]:
    """``render_notification`` for a page of rows, with the teachers' texts
    they name read in one pass."""
    rows = list(notifications)
    texts = released_texts(db, [r[1] for r in map(_recipe, rows) if r is not None], locale)
    return [render_notification(row, locale, texts) for row in rows]


def render_notification(
    notification: Notification, locale: str, texts: Mapping[ContentKey, str] | None = None
) -> tuple[str, str]:
    """Title and message for this reader, right now.

    ``texts`` carries the released teacher's texts the recipe names (see
    ``released_texts``); without it they are named by their fallback.

    Falls back to the stored text for rows written before notifications
    carried a recipe, and for any key that has since left the catalog.
    """
    recipe = _recipe(notification)
    if recipe is None:
        return notification.title, notification.message
    key, raw_params = recipe
    params = resolve_params(raw_params, locale, texts)
    try:
        title = t(locale, f"{key}.title", **params)
        message = t(locale, f"{key}.body", **params)
    except (KeyError, IndexError, ValueError):
        # The recipe and the catalog disagree about what this template
        # needs. That happens the moment somebody adds a placeholder to
        # an existing key — every row written before the change is now
        # short a value.
        #
        # ``t`` formats with ``str.format``, which raises on a missing
        # name, and this is the notification LIST: one bad row would
        # 500 the whole bell for that reader, and the row is in the
        # database, so it would 500 forever. The stored text is what it
        # is there for.
        logger.info("notification %s: recipe %s does not fit the catalog", notification.id, key)
        return notification.title, notification.message
    # ``t`` returns the key itself when it knows nothing about it.
    if title == f"{key}.title" or message == f"{key}.body":
        return notification.title, notification.message
    # A template that still has braces in it lost an argument quietly —
    # ``{title} — in „{course}“`` is not a sentence anybody should read.
    if "{" in title or "{" in message:
        return notification.title, notification.message
    return title, message


def create_notification(
    db: Session,
    user_id: str | uuid.UUID,
    type: str,
    title: str,
    message: str,
    link: str | None = None,
    metadata: dict[str, Any] | None = None,
    i18n: dict[str, Any] | None = None,
) -> Notification:
    """``title`` and ``message`` are what a reader sees if nothing else
    can be worked out; ``i18n`` (see ``notification_text``) is what lets
    the row be read in whatever language the reader picks later."""
    if i18n is not None:
        metadata = {**(metadata or {}), I18N_KEY: i18n}
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link,
        meta=metadata,
    )
    db.add(notification)
    db.flush()
    return notification


def create_notifications_bulk(
    db: Session,
    user_ids: Iterable[str | uuid.UUID],
    *,
    type: str,
    title: str,
    message: str,
    link: str | None = None,
    metadata: dict[str, Any] | None = None,
    i18n: dict[str, Any] | None = None,
) -> int:
    # Bulk-insert one identical notification row per recipient. Used for fan-out
    # cases like course announcements where a per-row ``create_notification`` +
    # ``flush`` would cost one round-trip per enrolled student.
    #
    # ``bulk_insert_mappings`` bypasses the ORM ``default=uuid.uuid4`` on the
    # ``id`` column and ``notifications.id`` has no server-side default in the
    # migration (``005_add_audit_notifications``). Generate the UUIDs in
    # Python so the insert does not fail with a NOT NULL violation.
    if i18n is not None:
        metadata = {**(metadata or {}), I18N_KEY: i18n}
    payloads = [
        {
            "id": uuid.uuid4(),
            "user_id": uid,
            "type": type,
            "title": title,
            "message": message,
            "link": link,
            "meta": metadata,
        }
        for uid in user_ids
    ]
    if not payloads:
        return 0
    db.bulk_insert_mappings(inspect(Notification), payloads)
    return len(payloads)
