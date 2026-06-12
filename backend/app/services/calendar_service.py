"""Calendar event aggregation.

Pure domain logic extracted from the ``GET /calendar/events`` route so
the iCal feed (``app.api.v1.calendar_ical``) can reuse it without
fabricating a ``Response`` to satisfy a route signature. Takes domain
arguments only — no FastAPI ``Request``/``Response``/``Depends``
objects; header parsing and cache/Vary headers stay in the routes.
"""

from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.course import Chapter, Course, Module
from app.models.course_event import CourseEvent
from app.models.enrollment import Enrollment
from app.models.user import User
from app.schemas.calendar import CalendarEvent
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.translation.resolve_for_display import (
    fetch_course_titles_by_id,
    populate_module_texts,
)


def build_calendar_events(
    db: Session,
    *,
    user: User,
    course_id: str | None = None,
    limit: int = 1000,
    display_locale: LocaleCode,
) -> list[CalendarEvent]:
    """Aggregate the user's module deadlines + assignment deadlines +
    course events, cv-localized to ``display_locale`` with per-course
    source-locale fallback, sorted by date and capped to ``limit``
    (soonest events kept).
    """
    enrolled_q = db.query(Enrollment.course_id).filter(Enrollment.user_id == user.id)
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
            from app.models.content_version import ContentVersion, ContentVersionStatus

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
                    ContentVersion.status == ContentVersionStatus.OK,
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
        from app.models.content_version import ContentVersion, ContentVersionStatus

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
                ContentVersion.status == ContentVersionStatus.OK,
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
    # Phase 5bn: apply defensive cap AFTER sorting so the oldest events
    # fall off the end first. Keeping the soonest ``limit`` events is the
    # right shape for a calendar UI (upcoming deadlines matter more than
    # ancient ones).
    return events[-limit:]
