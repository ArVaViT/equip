"""Coverage tests for the calendar event endpoints in ``app.api.v1.calendar``.

The existing ``test_cohorts_calendar_notifications.py`` covers the
notification-side flow; this file targets the assignment-loop inside
``GET /calendar/events`` and the source-language permission gate on
``GET /courses/{course_id}/events``.

Without these, the bulk fetch for assignment cv rows (lines 159-221)
and the 403 gate on ``?source=1`` for non-owner non-admin viewers
were uncovered.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.course import Chapter
from app.models.enrollment import Enrollment

from ._cv_helpers import (
    make_assignment_with_text,
    make_course_event_with_text,
    make_course_with_text,
    make_module_with_text,
)
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_published_course_with_assignment(
    db: Session,
    *,
    course_id: str,
    enroll_student: bool = True,
    assignment_due_in_days: int = 7,
) -> tuple[str, str, uuid.UUID]:
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="Calendar Test Course",
        status="published",
        created_by=TEACHER_ID,
    )
    module = make_module_with_text(
        db,
        module_id=f"{course_id}-mod",
        course_id=course.id,
        title="Module",
        due_date=datetime.now(UTC) + timedelta(days=3),
    )
    chapter = Chapter(
        id=f"{course_id}-ch",
        module_id=module.id,
        title="Chapter",
        order_index=0,
        chapter_type="assignment",
    )
    db.add(chapter)
    db.flush()
    assignment = make_assignment_with_text(
        db,
        chapter_id=chapter.id,
        title="Sample Assignment",
        description="Do the thing",
        due_date=datetime.now(UTC) + timedelta(days=assignment_due_in_days),
    )
    if enroll_student:
        db.add(
            Enrollment(
                id=f"enroll-{course_id}",
                user_id=STUDENT_ID,
                course_id=course_id,
                progress=0,
            )
        )
    db.commit()
    return course.id, chapter.id, assignment.id


class TestCalendarEvents:
    """``GET /calendar/events`` aggregates module deadlines, assignment
    deadlines, and course events from every enrolled course.

    Every title resolves at the reader's language and nowhere else. The
    loop used to walk display → the course's source → any locale at all
    — a spare language written out by hand in the one subsystem the
    shared resolver does not cover — so a German student's calendar
    listed Russian assignment names beside German course names."""

    def test_assignment_with_due_date_surfaces_as_deadline_event(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        _seed_published_course_with_assignment(db, course_id="cal-assign-1")

        r = student_client.get("/api/v1/calendar/events", headers={"Accept-Language": "en"})
        assert r.status_code == 200
        events = r.json()
        # At minimum the module deadline + the assignment deadline.
        assignment_events = [e for e in events if e["source"] == "assignment_deadline"]
        assert len(assignment_events) == 1
        assert assignment_events[0]["title"] == "Sample Assignment"
        assert assignment_events[0]["description"] == "Do the thing"
        assert assignment_events[0]["event_type"] == "deadline"

    def test_a_language_with_no_row_gets_no_title_rather_than_another_language(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        """The assignment has an English row and nothing else. A reader
        asking in Russian is owed silence, not English — the client
        renders an empty title as "not translated yet", and a calendar
        entry in a language nobody chose is worse than a dated one."""
        _seed_published_course_with_assignment(db, course_id="cal-assign-2")

        r = student_client.get(
            "/api/v1/calendar/events",
            headers={"Accept-Language": "ru"},
        )
        assert r.status_code == 200
        assignment_events = [e for e in r.json() if e["source"] == "assignment_deadline"]
        assert len(assignment_events) == 1
        assert assignment_events[0]["title"] == ""

    def test_no_enrolled_courses_returns_empty(
        self,
        student_client: TestClient,
    ) -> None:
        r = student_client.get("/api/v1/calendar/events")
        assert r.status_code == 200
        assert r.json() == []


class TestCourseEventsSourceGate:
    """``GET /courses/{course_id}/events?source=1`` is the editor view
    that returns human-authored source text. It MUST 403 for anyone
    who isn't the course owner or an admin — students with the right
    Accept-Language hit the localized read instead."""

    def test_source_param_403_for_enrolled_student(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        course_id, _, _ = _seed_published_course_with_assignment(db, course_id="cal-src-1")
        # Add a course event so the endpoint has rows to return.
        make_course_event_with_text(
            db,
            course_id=course_id,
            title="Event A",
            created_by=TEACHER_ID,
        )
        db.commit()
        r = student_client.get(f"/api/v1/courses/{course_id}/events?source=1")
        assert r.status_code == 403
        assert "source-language" in r.json()["detail"]["message"]

    def test_source_param_ok_for_owner(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """The teacher (owner) hitting their own course with ?source=1
        gets the editor view — no 403."""
        course_id, _, _ = _seed_published_course_with_assignment(db, course_id="cal-src-2", enroll_student=False)
        make_course_event_with_text(
            db,
            course_id=course_id,
            title="Owner Event",
            created_by=TEACHER_ID,
        )
        db.commit()
        r = client.get(f"/api/v1/courses/{course_id}/events?source=1")
        assert r.status_code == 200

    def test_owner_without_source_also_200(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        course_id, _, _ = _seed_published_course_with_assignment(db, course_id="cal-src-3", enroll_student=False)
        make_course_event_with_text(
            db,
            course_id=course_id,
            title="Owner Event",
            created_by=TEACHER_ID,
        )
        db.commit()
        r = client.get(f"/api/v1/courses/{course_id}/events")
        assert r.status_code == 200


class TestUpdateCourseEventTextPatch:
    """``PUT /courses/{course_id}/events/{event_id}`` routes
    ``title`` / ``description`` through ``sanitize_string`` and then
    ``dual_write_entity_content``. Pin both the text-patch path
    (lines 447-452) and the unknown-event 404."""

    def test_update_text_patch_sanitizes_and_writes_cv(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        course_id, _, _ = _seed_published_course_with_assignment(db, course_id="cal-up-1", enroll_student=False)
        event = make_course_event_with_text(
            db,
            course_id=course_id,
            title="Initial Title",
            description="Initial Desc",
            created_by=TEACHER_ID,
        )
        db.commit()

        r = client.put(
            f"/api/v1/courses/{course_id}/events/{event.id}",
            json={"title": "<p>Updated Title</p>", "description": "Updated Desc"},
        )
        assert r.status_code == 200
        body = r.json()
        # The sanitizer keeps <p> through (allowed tag) but the round-trip
        # is what we're pinning — the patch reaches the cv writer.
        assert "Updated Title" in body["title"]

    def test_update_unknown_event_returns_404(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        course_id, _, _ = _seed_published_course_with_assignment(db, course_id="cal-up-2", enroll_student=False)
        r = client.put(
            f"/api/v1/courses/{course_id}/events/{uuid.uuid4()}",
            json={"title": "X"},
        )
        assert r.status_code == 404
