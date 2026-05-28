from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_course_owner
from app.core.database import get_db
from app.core.sanitize import sanitize_string
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
from app.services.content_versions import dual_write_entity_content, fetch_cv_entity_texts_with_fallback
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import (
    fetch_course_titles_by_id,
    localize_course_event_rows,
    populate_module_texts,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


_TRANSLATABLE_COURSE_EVENT_FIELDS = ("title", "description")


def _course_event_to_response(db: Session, event: CourseEvent, *, source_locale: str = "en") -> CourseEventResponse:
    """Phase 5e4: title + description columns dropped — pull both from
    cv. Used by the single-entity create / update routes; the list /
    calendar routes use ``localize_course_event_rows`` which is
    locale-aware.
    """
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="course_event",
        entity_ids=[str(event.id)],
        fields=list(_TRANSLATABLE_COURSE_EVENT_FIELDS),
        display_locale=source_locale,
        source_locale=source_locale,
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
    # from content that has been removed from the catalog. Live courses are
    # title-resolved against cv (display→source→any) for the labels below;
    # source_locale is also captured for per-course event-title fallback.
    course_source_locales: dict[str, LocaleCode] = {
        cid: normalize_locale(src)
        for cid, src in db.query(Course.id, Course.source_locale)
        .filter(Course.id.in_(enrolled_course_ids), Course.deleted_at.is_(None))
        .all()
    }
    enrolled_course_ids = list(course_source_locales)
    if not enrolled_course_ids:
        return []
    course_titles = fetch_course_titles_by_id(db, enrolled_course_ids, display_locale=display_locale)

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
    # Modules straddle multiple courses with potentially different
    # source_locales; group + bulk-hydrate so each module's title /
    # description land via cv.
    modules_by_src: dict[LocaleCode, list[Module]] = {}
    for m in modules:
        modules_by_src.setdefault(course_source_locales.get(m.course_id, display_locale), []).append(m)
    for src_locale, mods in modules_by_src.items():
        populate_module_texts(db, mods, source_locale=src_locale)
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
        # Phase 5e3: assignments.title + description columns dropped —
        # one cv read covers every assignment, with the picker applying
        # the per-assignment course-declared source_locale fallback.
        asg_rows_by_pair_locale: dict[tuple[str, str, str], str] = {}
        any_for_pair: dict[tuple[str, str], str] = {}
        if assignments:
            from app.models.content_version import ContentVersion

            asg_ids = [str(a.id) for a in assignments]
            cv_rows = (
                db.query(
                    ContentVersion.entity_id,
                    ContentVersion.field,
                    ContentVersion.locale,
                    ContentVersion.text,
                )
                .filter(
                    ContentVersion.entity_type == "assignment",
                    ContentVersion.entity_id.in_(asg_ids),
                    ContentVersion.field.in_(["title", "description"]),
                    ContentVersion.superseded_by.is_(None),
                    ContentVersion.status == "ok",
                )
                .order_by(ContentVersion.entity_id, ContentVersion.field, ContentVersion.created_at)
                .all()
            )
            for eid, fld, loc, txt in cv_rows:
                asg_rows_by_pair_locale.setdefault((eid, fld, loc), txt)
                any_for_pair.setdefault((eid, fld), txt)
        for a in assignments:
            assert a.due_date is not None
            crs_id = ch_to_course.get(a.chapter_id, "")
            aid = str(a.id)
            asg_source = course_source_locales.get(crs_id, display_locale)
            asg_title = (
                asg_rows_by_pair_locale.get((aid, "title", display_locale))
                or asg_rows_by_pair_locale.get((aid, "title", asg_source))
                or any_for_pair.get((aid, "title"))
                or ""
            )
            asg_description = (
                asg_rows_by_pair_locale.get((aid, "description", display_locale))
                or asg_rows_by_pair_locale.get((aid, "description", asg_source))
                or any_for_pair.get((aid, "description"))
            )
            events.append(
                CalendarEvent(
                    id=f"assignment-{a.id}",
                    title=asg_title,
                    description=asg_description,
                    event_type="deadline",
                    event_date=a.due_date,
                    course_id=crs_id,
                    course_title=course_titles.get(crs_id),
                    source="assignment_deadline",
                )
            )

    course_events = db.query(CourseEvent).filter(CourseEvent.course_id.in_(enrolled_course_ids)).all()

    # Phase 5e4: course_events.title + description columns dropped — one
    # cv read covers every event, with the picker applying the
    # per-event course-declared source_locale fallback in Python.
    # Mirrors the assignment-deadline pattern above.
    ce_rows_by_pair_locale: dict[tuple[str, str, str], str] = {}
    ce_any_for_pair: dict[tuple[str, str], str] = {}
    if course_events:
        from app.models.content_version import ContentVersion

        ce_ids = [str(ce.id) for ce in course_events]
        cv_rows = (
            db.query(
                ContentVersion.entity_id,
                ContentVersion.field,
                ContentVersion.locale,
                ContentVersion.text,
            )
            .filter(
                ContentVersion.entity_type == "course_event",
                ContentVersion.entity_id.in_(ce_ids),
                ContentVersion.field.in_(["title", "description"]),
                ContentVersion.superseded_by.is_(None),
                ContentVersion.status == "ok",
            )
            .order_by(ContentVersion.entity_id, ContentVersion.field, ContentVersion.created_at)
            .all()
        )
        for eid, fld, loc, txt in cv_rows:
            ce_rows_by_pair_locale.setdefault((eid, fld, loc), txt)
            ce_any_for_pair.setdefault((eid, fld), txt)

    for ce in course_events:
        course_src = course_source_locales.get(ce.course_id, normalize_locale(None))
        ce_id = str(ce.id)
        title = (
            ce_rows_by_pair_locale.get((ce_id, "title", display_locale))
            or ce_rows_by_pair_locale.get((ce_id, "title", course_src))
            or ce_any_for_pair.get((ce_id, "title"))
            or ""
        )
        description = (
            ce_rows_by_pair_locale.get((ce_id, "description", display_locale))
            or ce_rows_by_pair_locale.get((ce_id, "description", course_src))
            or ce_any_for_pair.get((ce_id, "description"))
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
) -> CourseEventResponse:
    verify_course_owner(db, course_id, teacher)
    # Phase 5e4: title + description live in cv. Sanitisation runs
    # before the cv write so stored text is safe to render.
    title = sanitize_string(data.title)
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
    if source and not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the course owner or an admin can request source-language content",
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    # Phase 5e4: title + description live in cv. Pop them off the patch
    # before the setattr loop and route through dual_write.
    updates = data.model_dump(exclude_unset=True)
    text_patch: dict[str, str | None] = {}
    if "title" in updates:
        v = updates.pop("title")
        text_patch["title"] = sanitize_string(v) if v is not None else None
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    db.delete(event)
    db.commit()
