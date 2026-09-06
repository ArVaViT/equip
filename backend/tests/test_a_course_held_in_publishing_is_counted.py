"""A course held in ``publishing`` is a number on a dashboard, not a
thing somebody notices.

Every metric the pipeline had described the queue: depth, in flight,
given up. A course held out of the catalogue by one parked row is the
case the queue cannot see — no job is queued for it, the sweep declines
to queue one, nothing is in flight — and so it looked, on every gauge,
exactly like a healthy idle system. Thirteen such parkings in thirty
days of production, each announced once by a ``Translation failed
validation`` warning, each found by hand.

``equip.translation.publishing_stuck`` counts courses that have been in
``publishing`` for longer than an hour. When a course entered
``publishing`` is read off the audit log — the ``publish`` action the
course PUT records — because ``courses.updated_at`` is bumped by the
sweep's own timestamp every cycle and would say every course was
touched a minute ago.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.api.v1.internal_translation_worker import _emit_queue_gauges
from app.models.audit_log import AuditLog
from app.models.course import Course, CourseStatus
from app.models.user import User
from app.services.translation.completeness import courses_stuck_in_publishing
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.orm import Session

_NOW = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)


def _course(db: Session, *, status: str = CourseStatus.PUBLISHING, published_ago: timedelta | None) -> Course:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="teacher@example.com", role="teacher"))
        db.commit()
    course = Course(id=str(uuid.uuid4()), created_by=TEACHER_ID, status=status, source_locale="ru")
    db.add(course)
    if published_ago is not None:
        db.add(
            AuditLog(
                user_id=TEACHER_ID,
                action="publish",
                resource_type="course",
                resource_id=course.id,
                details={"old_status": "draft", "new_status": "publishing"},
                created_at=_NOW - published_ago,
            )
        )
    db.commit()
    return course


class TestWhichCoursesCount:
    def test_an_hour_in_publishing_counts(self, db: Session) -> None:
        course = _course(db, published_ago=timedelta(hours=2))
        assert courses_stuck_in_publishing(db, now=_NOW) == [course.id]

    def test_a_course_the_worker_is_still_on_does_not(self, db: Session) -> None:
        """Five minutes in is a pipeline working, not a course stuck.
        Counting it would make the gauge fire on every publication."""
        _course(db, published_ago=timedelta(minutes=5))
        assert courses_stuck_in_publishing(db, now=_NOW) == []

    def test_a_published_course_does_not(self, db: Session) -> None:
        _course(db, status=CourseStatus.PUBLISHED, published_ago=timedelta(days=3))
        assert courses_stuck_in_publishing(db, now=_NOW) == []

    def test_the_latest_publication_is_the_one_that_counts(self, db: Session) -> None:
        """A course unpublished and sent out again starts its hour over.
        The first ``publish`` entry is history, not a clock."""
        course = _course(db, published_ago=timedelta(days=3))
        db.add(
            AuditLog(
                user_id=TEACHER_ID,
                action="publish",
                resource_type="course",
                resource_id=course.id,
                details={},
                created_at=_NOW - timedelta(minutes=10),
            )
        )
        db.commit()
        assert courses_stuck_in_publishing(db, now=_NOW) == []

    def test_a_course_with_no_publication_on_record_falls_back_to_its_dates(self, db: Session) -> None:
        """Moved into ``publishing`` by some path that wrote no audit
        entry. The course's own dates are a worse clock — the sweep
        bumps ``updated_at`` — but a worse clock beats not counting."""
        course = _course(db, published_ago=None)
        course.updated_at = _NOW - timedelta(hours=6)
        db.commit()
        assert courses_stuck_in_publishing(db, now=_NOW) == [course.id]


class TestTheWorkerReportsIt:
    def test_the_gauge_and_the_warning(self, db: Session, caplog: pytest.LogCaptureFixture) -> None:
        """The gauge plots the count; the WARNING names the course and
        is the line that reaches the log drain, INFO not being shipped
        on this deployment."""
        course = _course(db, published_ago=timedelta(hours=26))

        with caplog.at_level(logging.INFO):
            _emit_queue_gauges(db)

        metric_lines = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        assert any("equip.translation.publishing_stuck" in m and "value=1.0" in m for m in metric_lines)
        warnings = [
            r for r in caplog.records if r.levelno == logging.WARNING and "held in publishing" in r.getMessage()
        ]
        assert len(warnings) == 1
        assert course.id in warnings[0].getMessage()

    def test_zero_is_reported_as_zero(self, db: Session, caplog: pytest.LogCaptureFixture) -> None:
        """An explicit zero proves the worker looked. An absent series
        on the dashboard would read as a metric outage."""
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _emit_queue_gauges(db)
        metric_lines = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        assert any("equip.translation.publishing_stuck" in m and "value=0.0" in m for m in metric_lines)
