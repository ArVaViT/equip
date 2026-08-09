"""Resolving, validating and auditing a hand-set grade.

Design: ``grading-system-redesign.md`` (Accepted 2026-08-06), decision D7.

Three things live here, and each replaces something that used to be decided
implicitly:

* **which row counts.** ``student_grades`` is unique on (student, course,
  cohort) with NULLs not distinct, so a cohort-scoped row and a legacy
  NULL-cohort row can coexist for the same student. Today's gradebook iterates
  every matching row and the last one read wins — meaning a stale override
  from before the course had cohorts can silently outrank this term's. The
  rule is now explicit and ordered.
* **what a code may be.** The scheme decides. A ``letter`` course cannot hold
  «5», a ``pass_fail`` course cannot hold «B», and no course can hold "Aa+".
* **that it is written down.** Setting, changing and clearing an override each
  append to the audit log with the old value, the new one, and what the
  calculator had said — so a grade moved by hand can always be traced to a
  person and a moment.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.enrollment import Enrollment
from app.models.student_grade import StudentGrade
from app.services.audit_service import log_action

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from fastapi import Request
    from sqlalchemy.orm import Session

    from app.models.course import Course

#: Symbols each scheme accepts as a hand-set grade. `percent` is absent on
#: purpose: there the result is a number, and it goes to ``override_score``.
CODES_BY_SCHEME: dict[str, tuple[str, ...]] = {
    "pass_fail": ("pass", "fail"),
    "five_point": ("5", "4", "3", "2"),
    "letter": ("A", "B", "C", "D", "F"),
}

AUDIT_RESOURCE = "student_grade"
ACTION_SET = "grade_override_set"
ACTION_CHANGED = "grade_override_changed"
ACTION_CLEARED = "grade_override_cleared"


def resolve_official_row(db: Session, *, student_id: UUID | str, course_id: str) -> StudentGrade | None:
    """The one override row that counts for this student, or ``None``.

    Order, and nothing else is consulted:

    1. the row matching the student's enrolment cohort;
    2. failing that, the row with no cohort;
    3. failing that, there is no override.

    Reading every row and letting the last win — what the gradebook does today
    — means a leftover NULL-cohort override can outrank the current term's and
    quietly pass a failing student. Which row is official must not depend on
    the order rows come back from the database.
    """
    rows = (
        db.query(StudentGrade).filter(StudentGrade.student_id == student_id, StudentGrade.course_id == course_id).all()
    )
    if not rows:
        return None

    # A student can hold several enrolments in one course — a retake in a later
    # cohort writes a new row (see Enrollment.__table_args__). Taking whichever
    # came back first made the official grade depend on row order, which is
    # exactly what this function exists to prevent. The most recent enrolment
    # is the one being graded now.
    enrolment_cohort = (
        db.query(Enrollment.cohort_id)
        .filter(Enrollment.user_id == student_id, Enrollment.course_id == course_id)
        .order_by(Enrollment.enrolled_at.desc().nullslast(), Enrollment.id.desc())
        .limit(1)
        .scalar()
    )

    if enrolment_cohort is not None:
        for row in rows:
            if row.cohort_id == enrolment_cohort:
                return row

    for row in rows:
        if row.cohort_id is None:
            return row

    return None


def validate_override(course: Course, *, code: str | None, score: Decimal | None) -> str | None:
    """Check a proposed override against the course scheme.

    Returns an error message, or ``None`` when the pair is acceptable.
    """
    if code is not None and score is not None:
        return "Provide either override_code or override_score, not both"
    if code is None and score is None:
        # A row with no override is a comment the teacher left without touching
        # the grade — ordinary, and previously impossible.
        return None

    scheme = course.grading_scheme or "letter"

    if score is not None:
        if scheme != "percent":
            return f"A numeric override needs the percent scheme; this course uses {scheme}"
        if not (Decimal("0") <= score <= Decimal("100")):
            return "override_score must be between 0 and 100"
        return None

    allowed = CODES_BY_SCHEME.get(scheme)
    if allowed is None:
        return f"The {scheme} scheme takes a numeric override, not a symbol"
    if code not in allowed:
        return f"{code!r} is not a grade in the {scheme} scheme (expected one of {', '.join(allowed)})"
    return None


def audit_override(
    db: Session,
    *,
    actor_id: UUID | str,
    action: str,
    row: StudentGrade,
    previous: Mapping[str, object] | None = None,
    request: Request | None = None,
) -> None:
    """Record a hand-set grade in the audit log.

    Deliberately records the computed score alongside the override: "teacher
    set B" says little, "teacher set B where the system had computed 64%" is
    the sentence a director actually needs.
    """
    log_action(
        db,
        user_id=actor_id,
        action=action,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(row.id),
        details={
            "student_id": str(row.student_id),
            "course_id": row.course_id,
            "cohort_id": str(row.cohort_id) if row.cohort_id else None,
            "override_code": row.override_code,
            "override_score": float(row.override_score) if row.override_score is not None else None,
            "computed_score": float(row.computed_score) if row.computed_score is not None else None,
            "reason": row.reason,
            "previous": dict(previous) if previous is not None else None,
        },
        request=request,
    )
