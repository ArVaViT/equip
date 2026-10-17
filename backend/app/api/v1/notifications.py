from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import exists, or_, true
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.course import Course
from app.models.notification import Notification
from app.models.user import User
from app.schemas.locale import normalize_locale
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification_service import render_notifications
from app.services.staged_edits import awaiting_first_release

router = APIRouter(prefix="/notifications", tags=["notifications"])

#: The course a notification is about, when it is about one.
_ABOUT_COURSE = Notification.meta["course_id"].as_string()

#: Not about a course, or about one that is still there. A course in the
#: bin (or purged) kept its announcements and events in the bell, each a
#: link to a 404 (2026-10-03). Filtered when read rather than deleted, so
#: restoring the course from the bin brings them back with it.
_ABOUT_A_LIVE_COURSE = or_(
    _ABOUT_COURSE.is_(None),
    exists().where(Course.id == _ABOUT_COURSE, Course.deleted_at.is_(None)),
)

#: The announcement a notification is about, when it is about one.
_ABOUT_ANNOUNCEMENT = Notification.meta["announcement_id"].as_string()


def _not_about_an_unreleased_post(db: Session) -> ColumnElement[bool]:
    """Leave out the notices about a post readers cannot see yet.

    A new announcement on a live course is held until every language has
    it, and ``list_announcements`` hides it from readers until then. Its
    notice is written at once, so it is hidden here the same way and turns
    up once the post is out — in its place by date, with the title it was
    released with. For the reader of the author's language too: there is
    no early copy in one language. Filtered when read, like a binned
    course, so nothing has to be fanned out a second time on release.

    Events are not held back: the calendar lists a held event under its
    kind, and so does its notice (see ``course_notifications.entity_title``)
    — a reminder that a session starts within the hour must not wait.
    """
    held = awaiting_first_release(db, entity_type="announcement", fields=["title", "content"])
    if not held:
        return true()
    return or_(_ABOUT_ANNOUNCEMENT.is_(None), _ABOUT_ANNOUNCEMENT.notin_(sorted(held)))


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    released = _not_about_an_unreleased_post(db)
    total = (
        db.query(sa_func.count(Notification.id))
        .filter(Notification.user_id == current_user.id, _ABOUT_A_LIVE_COURSE, released)
        .scalar()
    ) or 0

    items = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, _ABOUT_A_LIVE_COURSE, released)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Rendered per request, not per write. A notification used to be
    # stored as finished text in whatever language the writer resolved
    # at the time, which froze the reader's language at the moment of
    # the event: switch to German and the bell stays Russian. Rows
    # written before this carry no recipe and fall back to their stored
    # text.
    response.headers["Vary"] = "Accept-Language"
    locale = normalize_locale(accept_language or current_user.preferred_locale)
    rendered = [
        NotificationResponse.model_validate(item, from_attributes=True).model_copy(
            update={"title": title, "message": message}
        )
        for item, (title, message) in zip(items, render_notifications(db, items, locale), strict=True)
    ]

    return {
        "items": rendered,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = (
        db.query(sa_func.count(Notification.id))
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
            _ABOUT_A_LIVE_COURSE,
            _not_about_an_unreleased_post(db),
        )
        .scalar()
    ) or 0
    return UnreadCountResponse(count=count)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_as_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not notification:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Notification not found",
            context={"resource_type": "notification", "resource_id": str(notification_id)},
        )

    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/read-all", status_code=status.HTTP_200_OK)
def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Only what the reader can see: a notice still held back for its post
    # is new when it turns up.
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
        _not_about_an_unreleased_post(db),
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"message": "All notifications marked as read"}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not notification:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Notification not found",
            context={"resource_type": "notification", "resource_id": str(notification_id)},
        )

    db.delete(notification)
    db.commit()
