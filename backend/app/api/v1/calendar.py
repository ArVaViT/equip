from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_course_owner
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.i18n import t
from app.core.sanitize import sanitize_multiline_text, sanitize_plain_text
from app.models.course import Course, CourseStatus
from app.models.course_event import CourseEvent
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from app.schemas.calendar import (
    CalendarEvent,
    CourseEventCreate,
    CourseEventResponse,
    CourseEventUpdate,
)
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.calendar_service import build_calendar_events
from app.services.content_versions import (
    delete_entity_cv_rows,
    dual_write_entity_content,
    fetch_cv_entity_texts_with_fallback,
)
from app.services.course_notifications import (
    course_title_for_locale,
    delete_notifications_about,
    enrolled_recipients_by_locale,
    entity_title_for_locale,
)
from app.services.notification_service import create_notifications_bulk, notification_text
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import localize_course_event_rows

router = APIRouter(prefix="/calendar", tags=["calendar"])


_TRANSLATABLE_COURSE_EVENT_FIELDS = ("title", "description")


def _event_link(course_id: str) -> str:
    """Where a notification about an event sends the reader: the calendar,
    filtered to the course. The date and time are shown there in the
    reader's own zone — which is why the notification text itself names
    neither: the server does not know where the reader is."""
    return f"/calendar?course={course_id}"


def _notify_students_about_event(
    db: Session,
    *,
    course: Course,
    event: CourseEvent,
    author: User,
    rescheduled: bool,
) -> None:
    """Tell every enrolled student the event exists (or moved).

    Announcements had this fan-out from the start; events did not, so a
    teacher could put an exam on the calendar and nobody would know
    until they happened to open it. Each recipient is written to in the
    language they read in, with the event's title in that language when
    it has one (see ``entity_title_for_locale`` for when it does not).
    The kind — deadline, exam — comes from the catalog so the sentence
    is whole in every language.
    """
    source_locale = normalize_locale(course.source_locale)
    recipients_by_locale = enrolled_recipients_by_locale(db, course_id=course.id, exclude_user_id=author.id)
    key = "notif.event_rescheduled" if rescheduled else "notif.new_event"
    for locale, recipients in recipients_by_locale.items():
        params = {
            "kind": t(locale, f"event_type.{event.event_type}"),
            "title": entity_title_for_locale(
                db,
                entity_type="course_event",
                entity_id=event.id,
                locale=locale,
                source_locale=source_locale,
                fallback_key="fallback.event",
            ),
            "course": course_title_for_locale(db, course, locale),
        }
        title = t(locale, f"{key}.title")
        message = t(locale, f"{key}.body", **params)
        link = _event_link(course.id)
        metadata = {"course_id": course.id, "event_id": str(event.id)}
        i18n = notification_text(key, **params)
        # Two literal call sites rather than one with a computed kind:
        # the notification-kinds test reads the kind off the source.
        if rescheduled:
            create_notifications_bulk(
                db,
                recipients,
                type="event_rescheduled",
                title=title,
                message=message,
                link=link,
                metadata=metadata,
                i18n=i18n,
            )
        else:
            create_notifications_bulk(
                db,
                recipients,
                type="new_event",
                title=title,
                message=message,
                link=link,
                metadata=metadata,
                i18n=i18n,
            )
    db.commit()


def _course_event_to_response(db: Session, event: CourseEvent, *, source_locale: str = "en") -> CourseEventResponse:
    """Title + description columns dropped — pull both from
    cv. Used by the single-entity create / update routes; the list /
    calendar routes use ``localize_course_event_rows`` which is
    locale-aware.

    ``include_author_edits`` because this answers the teacher about the
    text they just saved: on a published course that text waits for its
    translations before readers see it, but its author sees it now.
    """
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="course_event",
        entity_ids=[str(event.id)],
        fields=list(_TRANSLATABLE_COURSE_EVENT_FIELDS),
        display_locale=source_locale,
        source_locale=source_locale,
        include_author_edits=True,
    )
    title = texts.get((str(event.id), "title")) or ""
    description = texts.get((str(event.id), "description"))
    return CourseEventResponse.model_validate(
        {
            "id": event.id,
            "course_id": event.course_id,
            "title": title,
            "description": description,
            "event_type": event.event_type,
            "event_date": event.event_date,
            "created_by": event.created_by,
            "created_at": event.created_at,
        }
    )


@router.get("/events", response_model=list[CalendarEvent])
def get_calendar_events(
    response: Response,
    # 36 = UUID length; matches the bound on every Create schema id.
    course_id: str | None = Query(None, max_length=36),
    # Defensive cap. A student enrolled in 10+ courses with
    # years of module deadlines + assignment deadlines + course events
    # could otherwise fan out into the thousands; on Vercel serverless
    # the 10s function budget is the floor. 1000 covers any realistic
    # workload (calendar UI typically shows < 100 events at a time);
    # 2000 is the absolute ceiling. Applied AFTER the in-Python
    # event_date sort so the cap drops the oldest items first.
    limit: int = Query(1000, ge=1, le=2000),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CalendarEvent]:
    response.headers["Vary"] = "Accept-Language"
    return build_calendar_events(
        db,
        user=current_user,
        course_id=course_id,
        limit=limit,
        display_locale=normalize_locale(accept_language),
    )


event_router = APIRouter(prefix="/courses", tags=["calendar"])


@event_router.post(
    "/{course_id}/events",
    response_model=CourseEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_course_event(
    course_id: str,
    data: CourseEventCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> CourseEventResponse:
    course = verify_course_owner(db, course_id, teacher)
    # Title + description live in cv. Sanitisation runs
    # before the cv write so stored text is safe to render. Both are
    # typed as plain text and shown as plain text, so neither is
    # HTML-escaped on the way in (``sanitize_multiline_text``).
    title = sanitize_plain_text(data.title)
    description = sanitize_multiline_text(data.description) if data.description else data.description
    event = CourseEvent(
        course_id=course_id,
        event_type=data.event_type,
        event_date=data.event_date,
        created_by=teacher.id,
    )
    db.add(event)
    db.flush()
    source_locale = course.source_locale
    dual_write_entity_content(
        db,
        entity_type="course_event",
        entity_id=str(event.id),
        fallback_locale=source_locale,
        authored_by=teacher.id,
        texts={"title": title, "description": description},
    )
    db.commit()
    db.refresh(event)
    # Translate first so a recipient's language has the title by the
    # time their notification is written.
    reconcile_entity_if_course_published(db, "course_event", event)
    _notify_students_about_event(db, course=course, event=event, author=teacher, rescheduled=False)
    return _course_event_to_response(db, event, source_locale=source_locale or "en")


@event_router.get(
    "/{course_id}/events",
    response_model=list[CourseEventResponse],
)
def list_course_events(
    response: Response,
    course_id: str,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    source: bool = Query(
        False,
        description=(
            "Bypass the translation overlay and return source-language ``title`` "
            "+ ``description``. Owner / admin only — used by the calendar event "
            "editor. ``prefer_human=True`` keeps MT rows out of the any-locale "
            "fallback tier."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CourseEventResponse]:
    response.headers["Vary"] = "Accept-Language"
    # Narrow probe: only the columns needed for ownership + soft-delete checks.
    course_row = (
        db.query(Course.created_by, Course.source_locale, Course.status)
        .filter(Course.id == course_id, Course.deleted_at.is_(None))
        .first()
    )
    if not course_row:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Course not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    is_owner = str(course_row.created_by) == str(current_user.id)
    is_admin = current_user.role == UserRole.ADMIN.value
    if not is_owner and not is_admin:
        enrolled = (
            db.query(Enrollment.id)
            .filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id)
            .first()
        )
        if not enrolled:
            # Mirror the catalog / PDF-export leak guard: an unpublished
            # course 404s to non-member probes so its existence doesn't
            # leak; published courses keep the plain 403.
            if course_row.status != CourseStatus.PUBLISHED:
                raise equip_error(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    status_code=status.HTTP_404_NOT_FOUND,
                    message="Course not found",
                    context={"resource_type": "course", "resource_id": course_id},
                )
            raise equip_error(
                ErrorCode.AUTH_FORBIDDEN,
                status_code=status.HTTP_403_FORBIDDEN,
                message="You must be enrolled in this course to view events",
                context={"resource_type": "course_event", "course_id": course_id},
            )
    if source and not (is_owner or is_admin):
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only the course owner or an admin can request source-language content",
            context={"resource_type": "course_event", "course_id": course_id},
        )
    rows = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
    # Locale wins. Every reader — students, owners, admins — gets the locale
    # overlay when one exists. ``?source=1`` collapses display_locale to
    # source_locale and prefers human rows in the any-locale fallback tier
    # so the editor never sees machine output as authoritative source.
    display_locale: LocaleCode = normalize_locale(accept_language)
    source_locale: LocaleCode = normalize_locale(course_row.source_locale)
    return localize_course_event_rows(
        db,
        rows,
        display_locale=source_locale if source else display_locale,
        source_locale=source_locale,
        prefer_human=source,
    )


@event_router.put(
    "/{course_id}/events/{event_id}",
    response_model=CourseEventResponse,
)
def update_course_event(
    course_id: str,
    event_id: UUID,
    data: CourseEventUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> CourseEventResponse:
    course = verify_course_owner(db, course_id, teacher)
    event = (
        db.query(CourseEvent)
        .filter(
            CourseEvent.id == event_id,
            CourseEvent.course_id == course_id,
        )
        .first()
    )
    if not event:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Event not found",
            context={"resource_type": "course_event", "resource_id": str(event_id), "course_id": course_id},
        )
    # Title + description live in cv. Pop them off the patch
    # before the setattr loop and route through dual_write.
    updates = data.model_dump(exclude_unset=True)
    text_patch: dict[str, str | None] = {}
    if "title" in updates:
        v = updates.pop("title")
        text_patch["title"] = sanitize_plain_text(v) if v is not None else None
    if "description" in updates:
        v = updates.pop("description")
        text_patch["description"] = sanitize_multiline_text(v) if v is not None else None
    # A moved event is the one edit students must hear about — a
    # retitled one is not. Compare as instants: SQLite hands the old
    # value back naive, Postgres aware, and the patch is always aware.
    old_instant = event.event_date.replace(tzinfo=UTC) if event.event_date.tzinfo is None else event.event_date
    new_date = updates.get("event_date")
    rescheduled = new_date is not None and new_date != old_instant
    for field, value in updates.items():
        setattr(event, field, value)
    db.flush()
    source_locale = course.source_locale
    if text_patch:
        dual_write_entity_content(
            db,
            entity_type="course_event",
            entity_id=str(event.id),
            fallback_locale=source_locale,
            authored_by=teacher.id,
            only_fields=set(text_patch.keys()),
            texts=text_patch,
        )
    db.commit()
    db.refresh(event)
    reconcile_entity_if_course_published(db, "course_event", event)
    if rescheduled:
        _notify_students_about_event(db, course=course, event=event, author=teacher, rescheduled=True)
    return _course_event_to_response(db, event, source_locale=source_locale or "en")


@event_router.delete(
    "/{course_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_course_event(
    course_id: str,
    event_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    verify_course_owner(db, course_id, teacher)
    event = (
        db.query(CourseEvent)
        .filter(
            CourseEvent.id == event_id,
            CourseEvent.course_id == course_id,
        )
        .first()
    )
    if not event:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Event not found",
            context={"resource_type": "course_event", "resource_id": str(event_id), "course_id": course_id},
        )
    # cv polymorphic — drop rows explicitly.
    delete_entity_cv_rows(db, entity_type="course_event", entity_id=event.id)
    # The bell must not keep advertising an event that no longer exists.
    delete_notifications_about(
        db,
        types=("new_event", "event_rescheduled"),
        link=_event_link(course_id),
        meta_key="event_id",
        target_id=event.id,
    )
    db.delete(event)
    db.commit()
