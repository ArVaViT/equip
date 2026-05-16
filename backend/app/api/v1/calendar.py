from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_course_owner
from app.core.database import get_db
from app.models.assignment import Assignment
from app.models.course import Chapter, Course, Module
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
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import (
    fetch_overlay_triples_bulk,
    localize_course_event_rows,
    pick_overlay_value,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/events", response_model=list[CalendarEvent])
def get_calendar_events(
    response: Response,
    course_id: str | None = Query(None),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CalendarEvent]:
    response.headers["Vary"] = "Accept-Language"
    display_locale: LocaleCode = normalize_locale(accept_language)
    enrolled_q = db.query(Enrollment.course_id).filter(Enrollment.user_id == current_user.id)
    if course_id:
        enrolled_q = enrolled_q.filter(Enrollment.course_id == course_id)
    enrolled_course_ids = [row[0] for row in enrolled_q.all()]

    if not enrolled_course_ids:
        return []

    # Drop trashed courses — users may still have enrollments pointing to
    # deleted courses, but their calendar should not advertise deadlines
    # from content that has been removed from the catalog. We fetch title
    # AND source_locale in the same query (previously two separate fetches);
    # source_locale is needed below for the translation overlay.
    course_titles: dict[str, str] = {}
    course_source_locales: dict[str, LocaleCode] = {}
    course_rows = (
        db.query(Course.id, Course.title, Course.source_locale)
        .filter(Course.id.in_(enrolled_course_ids), Course.deleted_at.is_(None))
        .all()
    )
    for cid, ctitle, csrc in course_rows:
        course_titles[cid] = ctitle
        course_source_locales[cid] = normalize_locale(csrc)
    enrolled_course_ids = list(course_titles.keys())
    if not enrolled_course_ids:
        return []

    events: list[CalendarEvent] = []

    modules = (
        db.query(Module)
        .filter(
            Module.course_id.in_(enrolled_course_ids),
            Module.due_date.isnot(None),
            Module.deleted_at.is_(None),
        )
        .all()
    )
    for m in modules:
        assert m.due_date is not None
        events.append(
            CalendarEvent(
                id=f"module-{m.id}",
                title=f"{m.title} — Due",
                description=m.description,
                event_type="deadline",
                event_date=m.due_date,
                course_id=m.course_id,
                course_title=course_titles.get(m.course_id),
                source="module_deadline",
            )
        )

    chapter_ids_by_course: dict[str, list[str]] = {}
    chapters = (
        db.query(Chapter.id, Module.course_id)
        .join(Module, Chapter.module_id == Module.id)
        .filter(
            Module.course_id.in_(enrolled_course_ids),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .all()
    )
    for ch_id, crs_id in chapters:
        chapter_ids_by_course.setdefault(crs_id, []).append(ch_id)

    all_chapter_ids = [ch_id for ids in chapter_ids_by_course.values() for ch_id in ids]
    if all_chapter_ids:
        ch_to_course = {}
        for crs_id, ch_ids in chapter_ids_by_course.items():
            for ch_id in ch_ids:
                ch_to_course[ch_id] = crs_id

        assignments = (
            db.query(Assignment)
            .filter(
                Assignment.chapter_id.in_(all_chapter_ids),
                Assignment.due_date.isnot(None),
            )
            .all()
        )
        for a in assignments:
            assert a.due_date is not None
            crs_id = ch_to_course.get(a.chapter_id, "")
            events.append(
                CalendarEvent(
                    id=f"assignment-{a.id}",
                    title=a.title,
                    description=a.description,
                    event_type="deadline",
                    event_date=a.due_date,
                    course_id=crs_id,
                    course_title=course_titles.get(crs_id),
                    source="assignment_deadline",
                )
            )

    course_events = db.query(CourseEvent).filter(CourseEvent.course_id.in_(enrolled_course_ids)).all()

    # Bulk-fetch overlay rows for every course_event title + non-empty
    # description. Locale wins for every reader, including admins — moderators
    # who need raw source content use admin-only audit/edit surfaces.
    overlay_event: dict[tuple[str, str, str], str] = {}
    if course_events:
        specs: list[tuple[str, str, str]] = []
        for ce in course_events:
            specs.append(("course_event", str(ce.id), "title"))
            if ce.description and str(ce.description).strip():
                specs.append(("course_event", str(ce.id), "description"))
        overlay_event = fetch_overlay_triples_bulk(db, specs, display_locale)

    for ce in course_events:
        course_src = course_source_locales.get(ce.course_id, normalize_locale(None))
        title = (
            pick_overlay_value(
                overlay_event,
                "course_event",
                str(ce.id),
                "title",
                ce.title,
                source_locale=course_src,
                display_locale=display_locale,
            )
            or ce.title
        )
        description = pick_overlay_value(
            overlay_event,
            "course_event",
            str(ce.id),
            "description",
            ce.description,
            source_locale=course_src,
            display_locale=display_locale,
        )
        events.append(
            CalendarEvent(
                id=str(ce.id),
                title=title,
                description=description,
                event_type=ce.event_type,
                event_date=ce.event_date,
                course_id=ce.course_id,
                course_title=course_titles.get(ce.course_id),
                source="course_event",
            )
        )

    events.sort(key=lambda e: e.event_date)
    return events


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
) -> CourseEvent:
    verify_course_owner(db, course_id, teacher)
    event = CourseEvent(
        course_id=course_id,
        title=data.title,
        description=data.description,
        event_type=data.event_type,
        event_date=data.event_date,
        created_by=teacher.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    reconcile_entity_if_course_published(db, "course_event", event)
    return event


@event_router.get(
    "/{course_id}/events",
    response_model=list[CourseEventResponse],
)
def list_course_events(
    response: Response,
    course_id: str,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CourseEventResponse]:
    response.headers["Vary"] = "Accept-Language"
    # Narrow probe: only the columns needed for ownership + soft-delete checks.
    course_row = (
        db.query(Course.created_by, Course.source_locale)
        .filter(Course.id == course_id, Course.deleted_at.is_(None))
        .first()
    )
    if not course_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    is_owner = str(course_row.created_by) == str(current_user.id)
    is_admin = current_user.role == UserRole.ADMIN.value
    if not is_owner and not is_admin:
        enrolled = (
            db.query(Enrollment.id)
            .filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id)
            .first()
        )
        if not enrolled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be enrolled in this course to view events",
            )
    rows = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
    # Locale wins. Every reader — students, owners, admins — gets the locale
    # overlay when one exists. Editors that need raw source must use dedicated
    # authoring endpoints (the PUT/POST routes below operate on raw columns).
    display_locale: LocaleCode = normalize_locale(accept_language)
    source_locale: LocaleCode = normalize_locale(course_row.source_locale)
    return localize_course_event_rows(db, rows, display_locale=display_locale, source_locale=source_locale)


@event_router.put(
    "/{course_id}/events/{event_id}",
    response_model=CourseEventResponse,
)
def update_course_event(
    course_id: str,
    event_id: str,
    data: CourseEventUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> CourseEvent:
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    reconcile_entity_if_course_published(db, "course_event", event)
    return event


@event_router.delete(
    "/{course_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_course_event(
    course_id: str,
    event_id: str,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    db.delete(event)
    db.commit()
