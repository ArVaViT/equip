"""Changing how a course is graded — D8.

Until now there was no way to change a course's scheme at all: no field, no
route. That absence was also the only thing preventing the change from being
made silently, so the write path arrives with its rules already attached
rather than acquiring them later.

Three rules, each protecting something different:

* the scheme and its pass line are written together, because a five-point
  course whose pass line sits above 75 has an unreachable «3» band and no
  single-value write can notice that;
* hand-set grades block a scheme change, because «A» is not a five-point grade
  and reinterpreting it would move a student's official result without anyone
  deciding to;
* the change is audited, because it redefines what every grade in the course
  means — an academic decision, not a settings tweak.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.audit_log import AuditLog
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.student_grade import StudentGrade

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

SCHEME_URL = "/api/v1/grades/course/{course_id}/scheme"


def _course(db: Session, teacher, course_id: str = "c-scheme-change", scheme: str = "letter") -> Course:
    course = Course(id=course_id, status="published", created_by=teacher.id, grading_scheme=scheme)
    db.add(course)
    db.commit()
    return course


def test_reading_the_scheme_returns_the_bands_it_is_read_against(client, db: Session, teacher) -> None:
    """The client should render from the backend's answer, not its own copy."""
    course = _course(db, teacher)

    body = client.get(SCHEME_URL.format(course_id=course.id)).json()

    assert body["grading_scheme"] == "letter"
    assert [b[1] for b in body["bands"]] == ["A", "B", "C", "D", "F"]


def test_scheme_and_threshold_change_together(client, db: Session, teacher) -> None:
    course = _course(db, teacher)

    resp = client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "five_point", "pass_threshold": "70", "reason": "School switched to 5-point"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["grading_scheme"] == "five_point"
    assert [b[1] for b in resp.json()["bands"]] == ["5", "4", "3", "2"]


def test_five_point_above_the_ceiling_is_refused(client, db: Session, teacher) -> None:
    """A pass line above 75 leaves «3 (удовлетворительно)» unreachable.

    The course would look ordinary and be impossible to pass at the grade the
    scheme's own vocabulary calls passing.
    """
    course = _course(db, teacher)

    resp = client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "five_point", "pass_threshold": "80"},
    )

    assert resp.status_code == 422
    assert "75" in resp.text


def test_existing_hand_set_grades_block_a_scheme_change(client, db: Session, teacher, student) -> None:
    """«A» is not a grade in a five-point course.

    Converting it silently would change a student's official result with
    nobody having decided to. The refusal names who is affected so the teacher
    can act deliberately.
    """
    from .conftest import STUDENT_ID

    course = _course(db, teacher, course_id="c-scheme-blocked")
    db.add(Enrollment(id="enr-blocked", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.add(
        StudentGrade(
            id=uuid.uuid4(),
            student_id=STUDENT_ID,
            course_id=course.id,
            override_code="A",
        )
    )
    db.commit()

    resp = client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "five_point", "pass_threshold": "70"},
    )

    assert resp.status_code == 409
    assert str(STUDENT_ID) in resp.text
    db.refresh(course)
    assert course.grading_scheme == "letter", "the course must not change while overrides stand"


def test_threshold_alone_may_move_with_overrides_present(client, db: Session, teacher, student) -> None:
    """Only a *scheme* change reinterprets existing symbols.

    Nudging the pass line inside the same scheme does not make an «A» mean
    something else, so blocking it would be strictness without a reason.
    """
    from .conftest import STUDENT_ID

    course = _course(db, teacher, course_id="c-threshold-only")
    db.add(Enrollment(id="enr-thresh", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.add(StudentGrade(id=uuid.uuid4(), student_id=STUDENT_ID, course_id=course.id, override_code="B"))
    db.commit()

    resp = client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "letter", "pass_threshold": "75"},
    )

    assert resp.status_code == 200
    db.refresh(course)
    assert float(course.pass_threshold) == 75.0


def test_the_change_is_written_down(client, db: Session, teacher) -> None:
    course = _course(db, teacher, course_id="c-scheme-audit")

    client.put(
        SCHEME_URL.format(course_id=course.id),
        json={"grading_scheme": "percent", "pass_threshold": "60", "reason": "Director's decision"},
    )

    entry = db.query(AuditLog).filter(AuditLog.action == "grading_scheme_changed").first()
    assert entry is not None, "redefining what every grade means must leave a trail"
    assert entry.details["previous"]["grading_scheme"] == "letter"
    assert entry.details["new"]["grading_scheme"] == "percent"
    assert entry.details["reason"] == "Director's decision"


def test_another_teachers_course_is_not_reachable(client, db: Session, teacher) -> None:
    from app.models.user import User, UserRole

    other_teacher = User(
        id=uuid.uuid4(),
        email="other-teacher@test.local",
        full_name="Other Teacher",
        role=UserRole.TEACHER,
    )
    db.add(other_teacher)
    db.flush()
    foreign = Course(id="c-foreign-scheme", status="published", created_by=other_teacher.id)
    db.add(foreign)
    db.commit()

    resp = client.put(
        SCHEME_URL.format(course_id=foreign.id),
        json={"grading_scheme": "percent", "pass_threshold": "60"},
    )

    assert resp.status_code == 403
