from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_course_owner
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.sanitize import sanitize_plain_text, sanitize_string
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
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import localize_course_event_rows

router = APIRouter(prefix="/calendar", tags=["calendar"])


_TRANSLATABLE_COURSE_EVENT_FIELDS = ("title", "description")


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
    verify_course_owner(db, course_id, teacher)
    # Title + description live in cv. Sanitisation runs
    # before the cv write so stored text is safe to render.
    title = sanitize_plain_text(data.title)
    description = sanitize_string(data.description) if data.description else data.description
    event = CourseEvent(
        course_id=course_id,
        event_type=data.event_type,
        event_date=data.event_date,
        created_by=teacher.id,
    )
    db.add(event)
    db.flush()
    source_locale = db.query(Course.source_locale).filter(Course.id == course_id).scalar()
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
    reconcile_entity_if_course_published(db, "course_event", event)
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
    # Title + description live in cv. Pop them off the patch
    # before the setattr loop and route through dual_write.
    updates = data.model_dump(exclude_unset=True)
    text_patch: dict[str, str | None] = {}
    if "title" in updates:
        v = updates.pop("title")
        text_patch["title"] = sanitize_plain_text(v) if v is not None else None
    if "description" in updates:
        v = updates.pop("description")
        text_patch["description"] = sanitize_string(v) if v is not None else None
    for field, value in updates.items():
        setattr(event, field, value)
    db.flush()
    source_locale = db.query(Course.source_locale).filter(Course.id == course_id).scalar()
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
    db.delete(event)
    db.commit()
