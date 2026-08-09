"""Typed, audited, removable hand-set grades — Phase 1 / M3 (D7).

Three defects are closed here, and each was a way for a grade to move without
anyone being able to say who moved it or why:

* **the value was free text.** ``VARCHAR(10)`` accepted "Aa+" and could not fit
  «удовлетворительно», so a Russian-language school could not write its own
  grade correctly while nonsense went in unchallenged;
* **it could not be taken back.** The write path read an omitted field as
  "leave it alone", so once an F was set, no request removed it;
* **it left no trail.** ``graded_by`` holds the *last* writer, so the person
  who first set a grade vanished the moment anyone edited it, and what the
  system had computed was never recorded at all.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from app.models.audit_log import AuditLog
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.student_grade import StudentGrade
from app.services.grade_override import (
    ACTION_CLEARED,
    ACTION_SET,
    resolve_official_row,
    validate_override,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _course(scheme: str = "letter") -> Course:
    return Course(id=f"c-{scheme}", status="published", grading_scheme=scheme)


# --------------------------------------------------------------------------
# what a code may be — the scheme decides
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["A", "B", "C", "D", "F"])
def test_letter_course_accepts_its_own_symbols(code: str) -> None:
    assert validate_override(_course("letter"), code=code, score=None) is None


@pytest.mark.parametrize("code", ["5", "4", "3", "2"])
def test_five_point_course_accepts_its_own_symbols(code: str) -> None:
    assert validate_override(_course("five_point"), code=code, score=None) is None


def test_a_letter_course_does_not_take_a_five_point_symbol() -> None:
    """«5» is a grade in one scheme and nonsense in another."""
    error = validate_override(_course("letter"), code="5", score=None)

    assert error is not None
    assert "letter" in error


def test_free_text_is_unrepresentable() -> None:
    """The exact value the old VARCHAR(10) accepted without complaint."""
    assert validate_override(_course("letter"), code="Aa+", score=None) is not None


def test_percent_course_takes_a_number_not_a_symbol() -> None:
    assert validate_override(_course("percent"), code=None, score=Decimal("82.5")) is None
    assert validate_override(_course("percent"), code="B", score=None) is not None


def test_a_number_is_refused_where_the_scheme_expects_a_symbol() -> None:
    error = validate_override(_course("letter"), code=None, score=Decimal("82"))

    assert error is not None
    assert "percent" in error


def test_exactly_one_form_is_required() -> None:
    assert validate_override(_course("letter"), code=None, score=None) is not None
    assert validate_override(_course("letter"), code="A", score=Decimal("90")) is not None


# --------------------------------------------------------------------------
# which row counts — the defect that could pass a failing student
# --------------------------------------------------------------------------


def _enrol(db: Session, student_id, course_id: str, cohort_id=None) -> None:
    from app.models.user import User, UserRole

    if db.get(User, student_id) is None:
        db.add(
            User(
                id=student_id,
                email=f"{student_id}@test.local",
                full_name="Test Student",
                role=UserRole.STUDENT,
            )
        )
        db.flush()
    db.add(
        Enrollment(
            id=f"enr-{student_id}-{cohort_id or 'solo'}",
            user_id=student_id,
            course_id=course_id,
            cohort_id=cohort_id,
            progress=0,
        )
    )


def _override(db: Session, student_id, course_id: str, *, code: str, cohort_id=None) -> StudentGrade:
    row = StudentGrade(
        id=uuid.uuid4(),
        student_id=student_id,
        course_id=course_id,
        cohort_id=cohort_id,
        override_code=code,
    )
    db.add(row)
    return row


def test_the_cohort_row_outranks_a_leftover_one(db: Session) -> None:
    """The whole point of resolving instead of iterating.

    `student_grades` is unique on (student, course, cohort) with NULLs not
    distinct, so a row from before the course had cohorts can sit beside this
    term's. The gradebook used to keep whichever came back last — meaning a
    stale "pass" could outrank a current "fail", or the reverse.
    """
    course = Course(id="c-cohorts", status="published")
    db.add(course)
    student_id = uuid.uuid4()
    cohort_id = uuid.uuid4()
    from datetime import UTC, datetime, timedelta

    from app.models.cohort import Cohort

    now = datetime.now(UTC)
    db.add(
        Cohort(
            id=cohort_id,
            start_date=now,
            end_date=now + timedelta(days=90),
            status="active",
        )
    )
    db.flush()
    _enrol(db, student_id, course.id, cohort_id)
    _override(db, student_id, course.id, code="F", cohort_id=None)  # leftover
    _override(db, student_id, course.id, code="A", cohort_id=cohort_id)  # this term
    db.flush()

    official = resolve_official_row(db, student_id=student_id, course_id=course.id)

    assert official is not None
    assert official.override_code == "A"


def test_a_cohortless_row_is_the_fallback_not_a_rival(db: Session) -> None:
    course = Course(id="c-solo", status="published")
    db.add(course)
    student_id = uuid.uuid4()
    db.flush()
    _enrol(db, student_id, course.id)
    _override(db, student_id, course.id, code="B", cohort_id=None)
    db.flush()

    official = resolve_official_row(db, student_id=student_id, course_id=course.id)

    assert official is not None
    assert official.override_code == "B"


def test_no_rows_means_no_override(db: Session) -> None:
    course = Course(id="c-none", status="published")
    db.add(course)
    student_id = uuid.uuid4()
    db.flush()
    _enrol(db, student_id, course.id)
    db.flush()

    assert resolve_official_row(db, student_id=student_id, course_id=course.id) is None


# --------------------------------------------------------------------------
# the route: audited, snapshotted, removable
# --------------------------------------------------------------------------


def test_setting_a_grade_records_who_what_and_against_which_computed_score(
    client, db: Session, teacher, student
) -> None:
    from .conftest import STUDENT_ID

    course = Course(id="c-audit", status="published", created_by=teacher.id)
    db.add(course)
    db.add(Enrollment(id="enr-audit", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()

    resp = client.put(
        f"/api/v1/grades/course/{course.id}/student/{STUDENT_ID}",
        json={"override_code": "A", "reason": "Miscounted quiz 3"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["override_code"] == "A"
    assert resp.json()["reason"] == "Miscounted quiz 3"

    entry = db.query(AuditLog).filter(AuditLog.action == ACTION_SET).first()
    assert entry is not None, "a hand-set grade must leave a trail"
    assert entry.details["override_code"] == "A"
    assert entry.details["reason"] == "Miscounted quiz 3"
    assert "computed_score" in entry.details


def test_a_grade_can_be_taken_back(client, db: Session, teacher, student) -> None:
    """There was no way to do this at all before.

    The old write path treated an omitted field as "leave it alone", so an F
    set by mistake was permanent — and the typed CHECK makes a row with neither
    value illegal, so clearing has to delete rather than empty.
    """
    from .conftest import STUDENT_ID

    course = Course(id="c-clear", status="published", created_by=teacher.id)
    db.add(course)
    db.add(Enrollment(id="enr-clear", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()
    client.put(
        f"/api/v1/grades/course/{course.id}/student/{STUDENT_ID}",
        json={"override_code": "F"},
    )

    resp = client.delete(f"/api/v1/grades/course/{course.id}/student/{STUDENT_ID}")

    assert resp.status_code == 204
    assert db.query(StudentGrade).filter(StudentGrade.course_id == course.id).first() is None, (
        "clearing removes the row, so the computed grade takes over again"
    )
    assert db.query(AuditLog).filter(AuditLog.action == ACTION_CLEARED).first() is not None


def test_clearing_a_grade_that_is_not_there_is_a_404(client, db: Session, teacher, student) -> None:
    from .conftest import STUDENT_ID

    course = Course(id="c-clear-404", status="published", created_by=teacher.id)
    db.add(course)
    db.add(Enrollment(id="enr-404", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()

    resp = client.delete(f"/api/v1/grades/course/{course.id}/student/{STUDENT_ID}")

    assert resp.status_code == 404


def test_a_symbol_from_the_wrong_scheme_is_refused_by_the_route(client, db: Session, teacher, student) -> None:
    from .conftest import STUDENT_ID

    course = Course(id="c-scheme", status="published", created_by=teacher.id, grading_scheme="letter")
    db.add(course)
    db.add(Enrollment(id="enr-scheme", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()

    resp = client.put(
        f"/api/v1/grades/course/{course.id}/student/{STUDENT_ID}",
        json={"override_code": "5"},
    )

    assert resp.status_code == 422
