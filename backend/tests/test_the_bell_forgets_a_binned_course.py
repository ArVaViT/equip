"""A course in the bin takes its notifications with it — and brings them back.

Announcements and events notify every student with a link into the course.
Binning or purging the course left those rows in the bell: an unread count for
something nobody could open, each link a 404 (2026-10-03). They are filtered
when the bell is read rather than deleted, so a course restored from the bin
comes back with its notifications.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.notification import Notification
from tests._cv_helpers import make_course_with_text
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _notify(db: Session, course_id: str | None) -> None:
    db.add(
        Notification(
            user_id=STUDENT_ID,
            type="new_announcement",
            title="Exam moved",
            message="Acts of the Apostles",
            link=f"/courses/{course_id}" if course_id else "/",
            meta={"course_id": course_id} if course_id else None,
        )
    )
    db.commit()


def test_a_binned_course_leaves_the_bell_and_comes_back_on_restore(student_client: TestClient, db: Session) -> None:
    course = make_course_with_text(db, title="Acts", status="published", created_by=TEACHER_ID)
    _notify(db, course.id)
    _notify(db, None)
    assert student_client.get("/api/v1/notifications/unread-count").json()["count"] == 2

    course.deleted_at = datetime.now(UTC)
    db.commit()

    assert student_client.get("/api/v1/notifications/unread-count").json()["count"] == 1
    listed = student_client.get("/api/v1/notifications").json()
    assert (listed["total"], len(listed["items"])) == (1, 1)

    course.deleted_at = None
    db.commit()

    assert student_client.get("/api/v1/notifications/unread-count").json()["count"] == 2
