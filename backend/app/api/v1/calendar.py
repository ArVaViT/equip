import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_course_owner
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.i18n import t
from app.core.meeting_url import find_meeting_url
from app.core.sanitize import sanitize_multiline_text, sanitize_plain_text
from app.models.course import Course, CourseStatus
from app.models.course_event import CourseEvent
from app.models.enrollment import Enrollment
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.schemas.calendar import (
    CalendarEvent,
    CourseEventCreate,
    CourseEventResponse,
    CourseEventUpdate,
    SeriesScope,
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
from app.services.event_series import SeriesRejected, WeeklySeries, shift_on_wall_clock, zone_or_utc
from app.services.notification_service import (
    create_notifications_bulk,
    notification_text,
    resolve_params,
    translatable,
)
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


def _follow_recording_in_notices(db: Session, *, course_id: str, event: CourseEvent) -> None:
    """Keep the "recording is ready" notices pointing at the recording.

    A link is usually corrected because the first one was wrong: the notice
    must not keep the broken one. A recording taken off takes its notices
    with it, so adding one again later is one notice, not a second.
    """
    if not event.recording_url:
        delete_notifications_about(
            db,
            types=("recording_ready",),
            link=_event_link(course_id),
            meta_key="event_id",
            target_id=event.id,
        )
    else:
        for notice in db.query(Notification).filter(
            Notification.type == "recording_ready", Notification.link == _event_link(course_id)
        ):
            if isinstance(notice.meta, dict) and notice.meta.get("event_id") == str(event.id):
                notice.meta = {**notice.meta, "recording_url": event.recording_url}
    db.commit()


def notify_students_about_event(
    db: Session,
    *,
    course: Course,
    event: CourseEvent,
    author: User | None,
    rescheduled: bool,
    recording: bool = False,
    reminder: bool = False,
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
    recipients_by_locale = enrolled_recipients_by_locale(
        db, course_id=course.id, exclude_user_id=author.id if author else None
    )
    key = (
        "notif.event_reminder"
        if reminder
        else "notif.recording_ready"
        if recording
        else "notif.event_rescheduled"
        if rescheduled
        else "notif.new_event"
    )
    for locale, recipients in recipients_by_locale.items():
        params: dict[str, Any] = {
            # A catalog key, translated whenever the bell is opened.
            "kind": translatable(f"event_type.{event.event_type}"),
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
        message = t(locale, f"{key}.body", **resolve_params(params, locale))
        link = _event_link(course.id)
        metadata: dict[str, str] = {"course_id": course.id, "event_id": str(event.id)}
        # The bell is where a student is standing when the session is
        # about to start, so the way in travels with the notification
        # rather than only living on the course page. It goes in the
        # metadata and not into ``message``: the row is rendered
        # line-clamped to two lines, and a 90-character Zoom URL pasted
        # into the sentence pushes out the title of the thing it is
        # about. The client draws a "Join" button from this key.
        if event.meeting_url and not recording:
            metadata["meeting_url"] = event.meeting_url
        # A recording is watched from where the news is read, like a meeting
        # is joined: the bell draws a "Recording" button from this key.
        if event.recording_url:
            metadata["recording_url"] = event.recording_url
        i18n = notification_text(key, **params)
        # Two literal call sites rather than one with a computed kind:
        # the notification-kinds test reads the kind off the source.
        if reminder:
            create_notifications_bulk(
                db,
                recipients,
                type="event_reminder",
                title=title,
                message=message,
                link=link,
                metadata=metadata,
                i18n=i18n,
            )
        elif recording:
            create_notifications_bulk(
                db,
                recipients,
                type="recording_ready",
                title=title,
                message=message,
                link=link,
                metadata=metadata,
                i18n=i18n,
            )
        elif rescheduled:
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
            "meeting_url": event.meeting_url,
            "recording_url": event.recording_url,
            "duration_minutes": event.duration_minutes,
            "series_id": event.series_id,
            "created_by": event.created_by,
            "created_at": event.created_at,
        }
    )


def _as_aware(value: datetime) -> datetime:
    """SQLite hands a ``timestamptz`` back naive, Postgres aware; both are UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _has_ended(event: CourseEvent, now: datetime | None = None) -> bool:
    """Whether the event is already behind us — its end, or its start when
    it has no length. "A new event in your course" about last Saturday's
    class is news about nothing; its recording is the news."""
    end = _as_aware(event.event_date)
    if event.duration_minutes:
        end += timedelta(minutes=event.duration_minutes)
    return end <= (now or datetime.now(UTC))


def _mark_announced_within_the_hour(db: Session, event: CourseEvent) -> None:
    """A class posted or moved to within the next hour is announced by that
    notice, Join link and all; the hour-before reminder five minutes later
    would be the same news twice. Committed by the notifier."""
    from app.services.event_reminders import REMIND_WITHIN

    now = datetime.now(UTC)
    if _as_aware(event.event_date) - now <= REMIND_WITHIN:
        event.reminded_at = now


def _series_rejected(reason: str) -> Exception:
    return equip_error(
        ErrorCode.VALIDATION_FAILED,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message=f"Event series rejected: {reason}",
        context={"resource_type": "course_event", "reason": f"series_{reason}"},
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
    # Falls back to a link found in the description, because the
    # description is a free text box and a link is what people put
    # in free text boxes. The teacher who scheduled this product's
    # first live lesson typed his Zoom address there — the dedicated
    # field did not exist yet that day — and the event went out with
    # no meeting on it, so no student ever saw a Join button. He had
    # entered the link; the product had swallowed it.
    #
    # Not sanitised beside the title and the description: those are
    # prose that gets tags stripped out of it, and a URL is not prose
    # (the schema validator already refused anything but http(s)).
    meeting_url = data.meeting_url or find_meeting_url(description)
    if data.repeat is not None and data.event_type == "deadline":
        # A deadline is a moment in a course, not a weekly meeting; twelve
        # copies of one is a slip in the form, not a plan.
        raise _series_rejected("not_for_deadline")
    if data.repeat is None:
        starts = [data.event_date]
        series_id = None
    else:
        zone = zone_or_utc(data.repeat.time_zone or teacher.time_zone)
        try:
            starts = WeeklySeries(
                first=data.event_date, every_weeks=data.repeat.every_weeks, until=data.repeat.until, zone=zone
            ).occurrences()
        except SeriesRejected as exc:
            raise _series_rejected(exc.reason) from exc
        # A "series" of one is an event; do not mark it as a series the
        # editor would then offer "this and following" for.
        series_id = uuid.uuid4() if len(starts) > 1 else None
    events: list[CourseEvent] = []
    for start in starts:
        event = CourseEvent(
            course_id=course_id,
            event_type=data.event_type,
            event_date=start,
            meeting_url=meeting_url,
            # A recording belongs to one class; a series being created
            # has had none of them yet except, at most, the first.
            recording_url=data.recording_url if not events else None,
            duration_minutes=data.duration_minutes,
            series_id=series_id,
            created_by=teacher.id,
        )
        db.add(event)
        db.flush()
        dual_write_entity_content(
            db,
            entity_type="course_event",
            entity_id=str(event.id),
            fallback_locale=course.source_locale,
            authored_by=teacher.id,
            texts={"title": title, "description": description},
        )
        events.append(event)
    db.commit()
    source_locale = course.source_locale
    for event in events:
        db.refresh(event)
        # Translate first so a recipient's language has the title by the
        # time their notification is written.
        reconcile_entity_if_course_published(db, "course_event", event)
    # One notice for a whole series — about the first class still ahead —
    # not one per Saturday. A class already over is not "new": if it
    # came with its recording, the recording is the news; otherwise the
    # teacher is filling in the past and the class hears nothing.
    upcoming = next((e for e in events if not _has_ended(e)), None)
    if upcoming is not None:
        _mark_announced_within_the_hour(db, upcoming)
        notify_students_about_event(db, course=course, event=upcoming, author=teacher, rescheduled=False)
    elif events[0].recording_url:
        notify_students_about_event(
            db, course=course, event=events[0], author=teacher, rescheduled=False, recording=True
        )
    event = events[0]
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
    scope: SeriesScope = Query("this"),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> CourseEventResponse:
    course = verify_course_owner(db, course_id, teacher)
    event = _event_or_404(db, course_id, event_id)
    # Title + description live in cv. Pop them off the patch
    # before the setattr loop and route through dual_write.
    updates = data.model_dump(exclude_unset=True)
    zone = zone_or_utc(updates.pop("time_zone", None) or teacher.time_zone)
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
    old_instant = _as_aware(event.event_date)
    new_date = updates.get("event_date")
    rescheduled = new_date is not None and new_date != old_instant
    # Whether this patch has an opinion about the link, recorded before
    # the loop writes it. "Remove the meeting" arrives as an explicit
    # ``meeting_url: null``.
    meeting_url_given = "meeting_url" in updates
    # A recording added where there was none is news for the class; editing
    # or removing one is not.
    recording_added = bool(updates.get("recording_url")) and not event.recording_url
    # The other occurrences this edit reaches. A recording is one class's
    # own and never travels; a move travels as the same shift on the wall
    # clock — 20:00 → 19:00 is 19:00 on every lesson's own day.
    siblings = _series_siblings(db, event, scope)
    shared = {k: v for k, v in updates.items() if k not in ("recording_url", "event_date")}
    for sibling in siblings:
        for field, value in shared.items():
            setattr(sibling, field, value)
        if rescheduled:
            assert new_date is not None
            sibling.event_date = shift_on_wall_clock(
                _as_aware(sibling.event_date), old_anchor=old_instant, new_anchor=new_date, zone=zone
            )
            sibling.reminded_at = None
    for field, value in updates.items():
        setattr(event, field, value)
    if rescheduled:
        # The reminder is about a time; a new time is announced again.
        event.reminded_at = None
    # The same rescue as on create, and deliberately no wider than the
    # edit in front of it: a teacher rewriting the description is
    # telling us about the meeting, and a link that appears there with
    # the column empty is one they think they have entered.
    #
    # It does not run on edits that leave the description alone, and the
    # reason is a test: clearing the field is an explicit null, the link
    # is still down in the prose, and a rescue on the *next* unrelated
    # edit would put it back — the product arguing with someone who
    # removed a meeting on purpose. Events written before this column
    # existed are repaired by a one-off data migration instead, which is
    # the honest shape for a one-off.
    if "description" in text_patch and not meeting_url_given:
        found = find_meeting_url(text_patch["description"])
        for target in [event, *siblings]:
            if not target.meeting_url:
                target.meeting_url = found
    db.flush()
    source_locale = course.source_locale
    if text_patch:
        for target in [event, *siblings]:
            dual_write_entity_content(
                db,
                entity_type="course_event",
                entity_id=str(target.id),
                fallback_locale=source_locale,
                authored_by=teacher.id,
                only_fields=set(text_patch.keys()),
                texts=text_patch,
            )
    db.commit()
    for target in [event, *siblings]:
        db.refresh(target)
        reconcile_entity_if_course_published(db, "course_event", target)
    # One notice per edit, about the class the teacher opened — moving a
    # term's worth of Saturdays is one piece of news, not twelve. Moving
    # a class that is over (correcting the record) is no news at all.
    if rescheduled and not _has_ended(event):
        _mark_announced_within_the_hour(db, event)
        notify_students_about_event(db, course=course, event=event, author=teacher, rescheduled=True)
    if recording_added:
        notify_students_about_event(db, course=course, event=event, author=teacher, rescheduled=False, recording=True)
    elif "recording_url" in updates:
        _follow_recording_in_notices(db, course_id=course.id, event=event)
    return _course_event_to_response(db, event, source_locale=source_locale or "en")


def _event_or_404(db: Session, course_id: str, event_id: UUID) -> CourseEvent:
    event = db.query(CourseEvent).filter(CourseEvent.id == event_id, CourseEvent.course_id == course_id).first()
    if not event:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Event not found",
            context={"resource_type": "course_event", "resource_id": str(event_id), "course_id": course_id},
        )
    return event


def _series_siblings(db: Session, event: CourseEvent, scope: SeriesScope) -> list[CourseEvent]:
    """The other occurrences an edit or a delete with ``scope`` reaches.

    "following" means later than this one by start time, not by creation
    order: a lesson moved to an earlier week still counts from where it
    now stands. An event outside a series has no siblings whatever the
    scope.
    """
    if scope == "this" or event.series_id is None:
        return []
    q = db.query(CourseEvent).filter(
        CourseEvent.series_id == event.series_id,
        CourseEvent.course_id == event.course_id,
        CourseEvent.id != event.id,
    )
    if scope == "following":
        # ``>=``: a lesson moved onto this one's exact time is still not
        # before it. The anchor itself is excluded by id above.
        q = q.filter(CourseEvent.event_date >= event.event_date)
    return q.order_by(CourseEvent.event_date).all()


@event_router.delete(
    "/{course_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_course_event(
    course_id: str,
    event_id: UUID,
    scope: SeriesScope = Query("this"),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    verify_course_owner(db, course_id, teacher)
    event = _event_or_404(db, course_id, event_id)
    targets = [event, *_series_siblings(db, event, scope)]
    # The bell must not keep advertising an event that no longer exists.
    delete_notifications_about(
        db,
        types=("new_event", "event_rescheduled", "recording_ready", "event_reminder"),
        link=_event_link(course_id),
        meta_key="event_id",
        target_ids=[target.id for target in targets],
    )
    for target in targets:
        # cv polymorphic — drop rows explicitly.
        delete_entity_cv_rows(db, entity_type="course_event", entity_id=target.id)
        db.delete(target)
    db.commit()
