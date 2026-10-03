"""The unsubscribe link at the foot of every course mail.

* ``GET  /email/unsubscribe?token=…`` — what the link would turn off, and
  whether it already is. Reads only: mail scanners open every link in a
  message, and a GET that unsubscribed would turn people's mail off for them.
* ``POST /email/unsubscribe?token=…`` — turns that kind off. Called by the
  page the link opens (after the person presses the button) and by the mail
  client's own "unsubscribe" (RFC 8058 one-click: a form body
  ``List-Unsubscribe=One-Click``, which is accepted and otherwise ignored).

No login: the token is the authority, and it can do exactly one thing — turn
one kind of mail off for one person (``services/email/course_mail.py``).
Turning it back on is in the profile, where the person is signed in.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session  # noqa: TC002 — FastAPI Depends runtime use

from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.user import User
from app.services.email.course_mail import MailKind, read_unsubscribe_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email", tags=["email"])


class UnsubscribeState(BaseModel):
    kind: MailKind
    #: True once this kind is off for the person the link belongs to.
    off: bool


def _person_for(db: Session, token: str) -> tuple[User, MailKind]:
    read = read_unsubscribe_token(token)
    person = None
    if read is not None:
        try:
            person = db.get(User, uuid.UUID(read[0]))
        except ValueError:
            person = None
    if read is None or person is None:
        # One answer for a forged token, a mangled one, and an account that is
        # gone: none of them is something the reader can fix by trying again.
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=400,
            message="This unsubscribe link is not valid.",
            context={"resource_type": "unsubscribe"},
        )
    return person, read[1]


@router.get("/unsubscribe", response_model=UnsubscribeState)
def read_unsubscribe(token: str = Query(..., min_length=1), db: Session = Depends(get_db)) -> UnsubscribeState:
    person, kind = _person_for(db, token)
    return UnsubscribeState(kind=kind, off=kind in (person.email_off or []))


@router.post("/unsubscribe", response_model=UnsubscribeState)
def unsubscribe(token: str = Query(..., min_length=1), db: Session = Depends(get_db)) -> UnsubscribeState:
    person, kind = _person_for(db, token)
    current = list(person.email_off or [])
    if kind not in current:
        # A new list, not an in-place append: the JSON column is not tracked
        # for mutation, and an append would never reach the database.
        person.email_off = [*current, kind]
        db.commit()
        logger.info("unsubscribed: kind=%s", kind)
    return UnsubscribeState(kind=kind, off=True)
