"""How this grade came to be what it is (D7).

A hand-set grade is the one number on a teacher's page that nobody can
reconstruct from the work. Six months later, at the point where a director
signs a ведомость, "why is this a B when the system computed 64" has to have
an answer that is not somebody's memory.

The audit rows have been written since Phase 1. Nothing has ever read them
back, which means in practice the answer did not exist.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.audit_log import AuditLog
from app.models.course import Course, Module
from app.models.enrollment import Enrollment
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

URL = "/api/v1/grades/course/{}/student/{}/history"
OVERRIDE_URL = "/api/v1/grades/course/{}/student/{}"


def _course(db: Session, course_id: str):
    course = Course(id=course_id, status="published", created_by=TEACHER_ID, grading_scheme="letter")
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=100))
    db.commit()
    return course


def _history(client, course_id: str) -> list[dict]:
    response = client.get(URL.format(course_id, STUDENT_ID))
    assert response.status_code == 200, response.text
    return response.json()


def test_a_hand_set_grade_says_who_set_it_and_what_it_replaced(client, db: Session, teacher, student) -> None:
    course = _course(db, "hist-set")

    client.put(
        OVERRIDE_URL.format(course.id, STUDENT_ID),
        json={"override_code": "B", "reason": "Сдавал устно, письменная работа утеряна"},
    )

    entries = _history(client, course.id)

    assert len(entries) == 1
    assert entries[0]["action"] == "grade_override_set"
    assert entries[0]["override_code"] == "B"
    assert entries[0]["actor_name"] == teacher.full_name
    # The note written for the institution. Teacher-facing only (D7) — this is
    # the screen it exists for.
    assert entries[0]["reason"] == "Сдавал устно, письменная работа утеряна"


def test_changing_a_grade_twice_leaves_two_lines_not_one(client, db: Session, teacher, student) -> None:
    """A history that only keeps the current state is the state, not a history —
    and the question it is asked is about the change, not the value."""
    course = _course(db, "hist-twice")

    client.put(OVERRIDE_URL.format(course.id, STUDENT_ID), json={"override_code": "C", "reason": "первая"})
    client.put(OVERRIDE_URL.format(course.id, STUDENT_ID), json={"override_code": "B", "reason": "вторая"})

    entries = _history(client, course.id)

    # Both writes land as their own line. Their relative order is not asserted
    # here: `created_at` is a server default with second resolution, so two
    # writes in one test are genuinely simultaneous. Ordering has its own test
    # below, with the timestamps set apart.
    assert {e["action"] for e in entries} == {"grade_override_changed", "grade_override_set"}
    changed = next(e for e in entries if e["action"] == "grade_override_changed")
    assert changed["override_code"] == "B"
    assert changed["reason"] == "вторая"


def test_clearing_a_grade_is_itself_an_event(client, db: Session, teacher, student) -> None:
    course = _course(db, "hist-cleared")
    client.put(OVERRIDE_URL.format(course.id, STUDENT_ID), json={"override_code": "B", "reason": "почему-то"})

    client.delete(OVERRIDE_URL.format(course.id, STUDENT_ID))

    # Membership, not position: both rows carry the same second-resolution
    # timestamp, and what matters here is that removing a grade is recorded at
    # all — "there is no override" and "the override was taken away" look
    # identical on the page and are not the same event.
    assert "grade_override_cleared" in [e["action"] for e in _history(client, course.id)]


def test_the_newest_change_is_first(client, db: Session, teacher, student) -> None:
    """The question a drawer is opened with is almost always about the most
    recent change, and a list that has to be read bottom-up gets misread."""
    course = _course(db, "hist-order")
    client.put(OVERRIDE_URL.format(course.id, STUDENT_ID), json={"override_code": "C", "reason": "старая"})
    client.put(OVERRIDE_URL.format(course.id, STUDENT_ID), json={"override_code": "B", "reason": "новая"})
    old = db.query(AuditLog).filter(AuditLog.action == "grade_override_set").one()
    old.created_at = datetime.now(UTC) - timedelta(days=3)
    db.commit()

    assert [e["reason"] for e in _history(client, course.id)] == ["новая", "старая"]


def test_one_students_history_is_not_anothers(client, db: Session, teacher, student) -> None:
    other = User(id=uuid.uuid4(), email="other-student@example.com", full_name="Другой", role="student")
    db.add(other)
    db.commit()
    course = _course(db, "hist-other")
    db.add(Enrollment(id="enr-hist-other-2", user_id=other.id, course_id=course.id, progress=100))
    db.commit()
    client.put(OVERRIDE_URL.format(course.id, other.id), json={"override_code": "B", "reason": "не про них"})

    assert _history(client, course.id) == []


def test_one_courses_history_is_not_anothers(client, db: Session, teacher, student) -> None:
    """The same student in two courses is the ordinary case for a school running
    more than one subject, and a history that mixes them makes every entry
    ambiguous."""
    romans = _course(db, "hist-romans")
    _course(db, "hist-acts")
    client.put(OVERRIDE_URL.format(romans.id, STUDENT_ID), json={"override_code": "B", "reason": "римлянам"})

    assert _history(client, "hist-acts") == []
    assert len(_history(client, romans.id)) == 1


def test_a_teacher_cannot_read_a_course_they_do_not_own(client, db: Session, teacher, student) -> None:
    other = User(id=uuid.uuid4(), email="other-teacher@example.com", full_name="Чужой", role="teacher")
    db.add(other)
    db.flush()
    course = Course(id="hist-foreign", status="published", created_by=other.id)
    db.add(course)
    db.commit()

    assert client.get(URL.format(course.id, STUDENT_ID)).status_code in {403, 404}


def test_a_student_cannot_read_it_at_all(student_client, db: Session, teacher, student) -> None:
    """It carries the note written about them for the institution (D7)."""
    course = _course(db, "hist-private")

    assert student_client.get(URL.format(course.id, STUDENT_ID)).status_code == 403


def test_an_empty_history_is_an_empty_list_not_an_error(client, db: Session, teacher, student) -> None:
    """Most students never have one. The drawer opens and says nothing happened,
    which is a true and useful answer."""
    course = _course(db, "hist-empty")

    assert _history(client, course.id) == []
