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

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.i18n import t
from app.models.notification import Notification

#: Where the render recipe lives inside ``meta``.
I18N_KEY = "i18n"


def notification_text(key: str, **params: str) -> dict[str, Any]:
    """The recipe for one notification's title and message.

    ``key`` is the catalog prefix — ``notif.assignment_graded`` resolves
    ``notif.assignment_graded.title`` and ``…​.body``.
    """
    return {"key": key, "params": params}


def render_notification(notification: Notification, locale: str) -> tuple[str, str]:
    """Title and message for this reader, right now.

    Falls back to the stored text for rows written before notifications
    carried a recipe, and for any key that has since left the catalog.
    """
    recipe = (notification.meta or {}).get(I18N_KEY) if isinstance(notification.meta, dict) else None
    if not isinstance(recipe, dict) or not isinstance(recipe.get("key"), str):
        return notification.title, notification.message
    key = recipe["key"]
    params = recipe.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    title = t(locale, f"{key}.title", **params)
    message = t(locale, f"{key}.body", **params)
    # ``t`` returns the key itself when it knows nothing about it.
    if title == f"{key}.title" or message == f"{key}.body":
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
