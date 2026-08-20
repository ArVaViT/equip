"""Which language does this person read?

Three services had grown their own copy of this query — the certificate
service, the invitation service, and (not at all) the two notification
sites that simply wrote English. The answer is the same everywhere and
so is the fallback, and a notification is exactly the surface where
getting it wrong is most visible: it arrives unbidden, in a list of
other notifications that *are* in the reader's language.

``preferred_locale`` is nullable — an account can predate the column or
belong to somebody who never chose. ``normalize_locale`` turns that,
and any value the platform no longer serves, into ``DEFAULT_LOCALE``:
English, because a row that says nothing about the reader is not
evidence that they read Russian.
"""

from __future__ import annotations

import uuid  # noqa: TC003 — used at runtime by the annotation below
from typing import TYPE_CHECKING

from app.models.user import User
from app.schemas.locale import LocaleCode, normalize_locale

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def preferred_locale_of(db: Session, user_id: uuid.UUID | str | None) -> LocaleCode:
    """The language ``user_id`` chose, or the platform default.

    A missing user id is not an error: system-issued mail and
    notifications have no author behind them and still have to go out.
    """
    if user_id is None:
        return normalize_locale(None)
    raw = db.query(User.preferred_locale).filter(User.id == user_id).scalar()
    return normalize_locale(raw)


__all__ = ["preferred_locale_of"]
