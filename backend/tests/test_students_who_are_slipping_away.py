"""The teacher's list of students to call this week.

Quiet for seven days — no lesson read, no test, no work handed in — or two
deadlines missed with nothing handed in. Reading counts as activity: the
progress board's "last seen" counted only tests and submissions, and a student
reading every lesson looked gone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.cohort import Cohort
from app.models.course import Chapter, Module
from app.models.enrollment import Enrollment
from app.models.grade_exemption import GradeExemption
from app.models.user import User
from app.services.students_at_risk import students_at_risk
from tests._cv_helpers import make_course_with_text
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _days(n: float) -> datetime:
    return NOW - timedelta(days=n)


def _person(db: Session, name: str) -> User:
    user = User(id=uuid.uuid4(), email=f"{name}@example.com", full_name=name, role="student")
    db.add(user)
    db.flush()
    return user


def _setup(db: Session) -> dict[str, User]:
    course = make_course_with_text(db, title="Деяния", status="published", created_by=TEACHER_ID)
    module = Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0)
    reading = Chapter(id=f"r-{course.id}", course_id=course.id, module_id=module.id, title="R", order_index=0)
    essays = Chapter(
        id=f"a-{course.id}",
        course_id=course.id,
        module_id=module.id,
        title="A",
        order_index=1,
        chapter_type="assignment",
    )
    db.add_all([module, reading, essays])
    db.flush()
    late1 = Assignment(id=uuid.uuid4(), chapter_id=essays.id, max_score=10, due_date=_days(10))
    late2 = Assignment(id=uuid.uuid4(), chapter_id=essays.id, max_score=10, due_date=_days(3))
    future = Assignment(id=uuid.uuid4(), chapter_id=essays.id, max_score=10, due_date=NOW + timedelta(days=5))
    db.add_all([late1, late2, future])
    db.flush()

    people = {
        n: _person(db, n) for n in ("active", "quiet", "new", "missed", "excused", "reader", "done", "gone", "again")
    }
    for name, enrolled, progress in (
        ("active", 30, 10),
        ("quiet", 30, 10),
        ("new", 2, 0),
        ("missed", 30, 10),
        ("excused", 30, 10),
        ("reader", 30, 10),
        ("done", 30, 100),
        ("gone", 150, 10),
        ("again", 200, 10),
    ):
        db.add(
            Enrollment(
                id=str(uuid.uuid4()),
                user_id=people[name].id,
                course_id=course.id,
                progress=progress,
                enrolled_at=_days(enrolled),
            )
        )

    # Second time through, in a new cohort (ADR-010: a second enrolment row).
    cohort = Cohort(start_date=_days(20), end_date=NOW + timedelta(days=60), status="active")
    db.add(cohort)
    db.flush()
    db.add(
        Enrollment(
            id=str(uuid.uuid4()),
            user_id=people["again"].id,
            course_id=course.id,
            cohort_id=cohort.id,
            progress=10,
            enrolled_at=_days(20),
        )
    )

    def read(name: str, ago: float) -> None:
        db.add(ChapterProgress(user_id=people[name].id, chapter_id=reading.id, completed=True, completed_at=_days(ago)))

    def hand_in(name: str, assignment: Assignment, ago: float) -> None:
        db.add(
            AssignmentSubmission(
                assignment_id=assignment.id, student_id=people[name].id, content="x", submitted_at=_days(ago)
            )
        )

    hand_in("active", late1, 9)
    hand_in("active", late2, 1)
    read("quiet", 10)
    hand_in("quiet", late1, 12)
    hand_in("quiet", late2, 11)
    read("missed", 1)
    read("excused", 1)
    db.add(
        GradeExemption(
            student_id=people["excused"].id,
            course_id=course.id,
            item_type="assignment",
            item_id=late1.id,
            chapter_id=essays.id,
        )
    )
    read("reader", 2)
    # Stopped in May: past the call that helps.
    read("gone", 140)
    read("again", 12)
    # Dropped the first run, finished the second: done, not slipping.
    finisher = _person(db, "finisher")
    db.add(
        Enrollment(id=str(uuid.uuid4()), user_id=finisher.id, course_id=course.id, progress=40, enrolled_at=_days(200))
    )
    db.add(
        Enrollment(
            id=str(uuid.uuid4()),
            user_id=finisher.id,
            course_id=course.id,
            cohort_id=cohort.id,
            progress=100,
            enrolled_at=_days(20),
        )
    )
    db.add(ChapterProgress(user_id=finisher.id, chapter_id=reading.id, completed=True, completed_at=_days(10)))
    hand_in("reader", late1, 9)
    hand_in("reader", late2, 2)

    # Somebody else's course: none of its students are this teacher's to call.
    other_teacher = User(id=uuid.uuid4(), email="other-teacher@example.com", full_name="Other", role="teacher")
    db.add(other_teacher)
    db.flush()
    other = make_course_with_text(db, title="Other", status="published", created_by=other_teacher.id)
    stranger = _person(db, "stranger")
    db.add(Enrollment(id=str(uuid.uuid4()), user_id=stranger.id, course_id=other.id, progress=0, enrolled_at=_days(60)))
    db.commit()
    return people


def test_who_is_on_the_list_and_why(db: Session, teacher: User) -> None:
    people = _setup(db)
    rows = students_at_risk(db, TEACHER_ID, now=NOW)
    found = {r.full_name: r for r in rows}

    assert set(found) == {"quiet", "missed", "again"}
    assert len(rows) == len(found)  # two enrolments, one line
    assert found["again"].quiet_days == 12
    assert found["quiet"].quiet_days == 10
    assert found["missed"].missed_deadlines == 2
    assert found["again"].missed_deadlines == 2
    # Most deadlines missed first, then the quietest.
    assert [r.full_name for r in rows] == ["again", "missed", "quiet"]
    assert people["reader"]  # reading two days ago kept them off it


def test_the_teacher_sees_it_in_their_language(client: TestClient, db: Session, teacher: User) -> None:
    _setup(db)
    r = client.get("/api/v1/analytics/at-risk", headers={"Accept-Language": "ru"})
    assert r.status_code == 200, r.text
    names = {row["full_name"] for row in r.json()}
    # Real "now" here: the fixtures are days old relative to 2026-10-01, so at
    # least those two are on it whatever today is.
    assert {"quiet", "missed"} <= names
    assert "stranger" not in names and "done" not in names
    assert all(row["course_title"] == "Деяния" for row in r.json())
