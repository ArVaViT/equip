"""Single source of truth for the cohort seat-capacity gate.

Both enrollment paths must enforce ``max_students`` identically:

* student self-enroll — ``api/v1/courses/enrollment.py::_enforce_cohort_gates``
* admin add-student   — ``api/v1/cohorts.py::add_student``

The rule: a user who ALREADY holds a seat in the cohort is exempt (a second
course in the SAME cohort never consumes a new seat — that's the whole point
of the multi-cohort design), everyone else counts toward the cap.

Before this helper the two paths inlined the check differently and DIVERGED:
the admin path exempted already-seated users, the self-enroll path did not —
so a student already in a full cohort was wrongly 403'd when self-enrolling
into a SECOND course of that same cohort. They also raised different
``ErrorCode``s for the identical "cohort full" condition. One helper, one
behaviour, one code.

Note: the *status* gate (cohort must be "active" for self-enroll, but an admin
may add to an "upcoming" cohort) is deliberately NOT unified — that divergence
is intentional and stays at each call site.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import status
from sqlalchemy import func

from app.core.errors import ErrorCode, equip_error
from app.models.enrollment import Enrollment

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.models.cohort import Cohort


def assert_cohort_has_capacity(db: Session, cohort: Cohort, user_id: str | UUID) -> None:
    """Raise ``COURSE_ENROLMENT_CLOSED`` (403) if seating ``user_id`` would push
    the cohort past ``max_students``. No-op when ``max_students`` is unset or the
    user already holds a seat in this cohort.

    Call under the same ``with_for_update()`` lock on the cohort row that the
    write path uses, so the count + insert are atomic against concurrent adds.
    """
    if not cohort.max_students:
        return
    already_seated = (
        db.query(Enrollment.id).filter(Enrollment.cohort_id == cohort.id, Enrollment.user_id == user_id).first()
        is not None
    )
    if already_seated:
        return
    current_count = (
        db.query(func.count(func.distinct(Enrollment.user_id))).filter(Enrollment.cohort_id == cohort.id).scalar() or 0
    )
    if current_count >= cohort.max_students:
        raise equip_error(
            ErrorCode.COURSE_ENROLMENT_CLOSED,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Cohort has reached maximum capacity",
            context={
                "resource_type": "cohort",
                "cohort_id": str(cohort.id),
                "max_students": cohort.max_students,
                "current_count": current_count,
            },
        )
