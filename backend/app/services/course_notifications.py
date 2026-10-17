"""What a teacher's course-level post needs before it can reach the class.

An announcement and a calendar event fan out the same way: every
enrolled student except the author, grouped by the language they read
in, each group told in its own words about a thing whose title also has
a version in that language — or does not yet.

The pieces live here so ``announcements.py`` and ``calendar.py`` share
one answer to each question. The ``create_notifications_bulk`` call
itself stays in the route, with the kind written as a literal: the
notification-kinds test walks call sites statically and refuses a kind
it cannot read off the source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from app.models.enrollment import Enrollment
from app.models.notification import Notification
from app.models.user import User
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.notification_service import content_text, released_texts, resolve_params

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from app.models.course import Course


def enrolled_recipients_by_locale(
    db: Session,
    *,
    course_id: str,
    exclude_user_id: uuid.UUID | str | None,
) -> dict[LocaleCode, list[uuid.UUID]]:
    """Enrolled students who should hear about a course post, grouped by
    the language they read in.

    The author is left out — they wrote it. Deactivated accounts keep
    their enrollment rows but receive nothing (#786 rule).
    """
    rows = (
        db.query(Enrollment.user_id, User.preferred_locale)
        .join(User, User.id == Enrollment.user_id)
        .filter(
            Enrollment.course_id == course_id,
            User.deactivated_at.is_(None),
        )
        .all()
    )
    out: dict[LocaleCode, list[uuid.UUID]] = {}
    for uid, raw_locale in rows:
        if exclude_user_id is not None and str(uid) == str(exclude_user_id):
            continue
        out.setdefault(normalize_locale(raw_locale), []).append(uid)
    return out


def course_title(course: Course) -> dict[str, Any]:
    """The course's title, as a notification parameter read at render —
    in the language the reader is in when they open the bell, and the
    name the course has then (see ``entity_title``)."""
    return content_text("course", course.id, "title", fallback_key="fallback.course")


def entity_title(
    entity_type: Literal["announcement", "course_event"],
    entity_id: uuid.UUID | str,
    *,
    fallback_key: str,
) -> dict[str, Any]:
    """The post's title, as a notification parameter read at render.

    Not text: a reference the bell resolves each time it is opened, from
    released rows in the reader's language (``notification_service.
    content_text``). A text appears to readers only once every language
    has it — in the author's own language too, so the reader who shares
    it waits like everyone else. Until then the row names the post by
    ``fallback_key`` («an announcement», «an event»); from then on, by its
    title. A held edit to a released title keeps the released wording
    until the edit is out in every language.

    It used to be resolved here, once, with the author's held text for a
    reader of the author's language: an early copy in one language, which
    the calendar had too until it was reverted (b38d7556).
    """
    return content_text(entity_type, entity_id, "title", fallback_key=fallback_key)


def stored_params(db: Session, params: dict[str, Any], locale: LocaleCode) -> dict[str, Any]:
    """``params`` filled in as a reader in ``locale`` may read them now —
    for the row's stored text, which is shown only when its recipe cannot
    be rendered. Released rows only, like the render itself."""
    return resolve_params(params, locale, released_texts(db, [params], locale))


def delete_notifications_about(
    db: Session,
    *,
    types: tuple[str, ...],
    link: str,
    meta_key: str,
    target_id: uuid.UUID | str | None = None,
    target_ids: list[uuid.UUID] | list[str] | None = None,
) -> int:
    """Drop the notification rows a deleted post left in every recipient's
    bell.

    The rows point at the post only through ``meta[meta_key]``, which
    Postgres has no way to follow on its own. ``link`` was fixed at
    fan-out time, so the candidate set narrows in SQL by type + link and
    the ``meta`` match happens in Python — sidesteps the ``->>`` /
    ``json_extract`` dialect split while keeping the candidate count
    bounded by one course's enrollment.

    ``target_ids`` takes several at once — a deleted series is one scan of
    the course's notices, not one per lesson.
    """
    targets = {str(t) for t in (target_ids or [])}
    if target_id is not None:
        targets.add(str(target_id))
    if not targets:
        return 0
    candidates = db.query(Notification).filter(Notification.type.in_(types), Notification.link == link).all()
    stale_ids = [n.id for n in candidates if isinstance(n.meta, dict) and str(n.meta.get(meta_key)) in targets]
    if not stale_ids:
        return 0
    db.query(Notification).filter(Notification.id.in_(stale_ids)).delete(synchronize_session=False)
    return len(stale_ids)
