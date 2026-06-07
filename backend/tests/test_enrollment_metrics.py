"""Tests for ``equip.enrollments.created_total`` emission.

The Course Engagement dashboard's enrollment-rate tile reads from
this counter; the dropoff_count derived metric uses it as a
denominator. The metric MUST fire exactly once per *new* enrollment
and MUST NOT fire when the existing-row early return path is taken
(idempotent re-enroll).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from app.models.cohort import Cohort, CohortCourse
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from app.services.course_service import enroll_user_in_course

from ._cv_helpers import make_course_with_text
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.orm import Session


def _seed_users(db: Session) -> None:
    for user_id, role, email in [
        (TEACHER_ID, UserRole.TEACHER.value, "t@e.com"),
        (STUDENT_ID, UserRole.STUDENT.value, "s@e.com"),
    ]:
        if db.query(User).filter(User.id == user_id).first() is None:
            db.add(User(id=user_id, email=email, full_name="X", role=role))
    db.flush()


class TestEnrollmentMetricEmission:
    def test_emits_created_total_on_new_enrollment(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _seed_users(db)
        course = make_course_with_text(
            db,
            course_id="enr-new",
            title="Enr New",
            status="published",
            created_by=TEACHER_ID,
        )
        db.commit()

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            enrollment = enroll_user_in_course(db, STUDENT_ID, course.id)

        assert enrollment.course_id == course.id
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.enrollments.created_total" in m]
        assert events, "expected one created_total event"
        assert any("value=1.0" in m for m in events)
        assert any(f"course_id={course.id}" in m for m in events)

    def test_does_not_re_emit_on_idempotent_reenroll(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The existing-row early-return path MUST be silent — counting
        a re-enroll would inflate the enrollment denominator and skew
        the drop-off computation."""
        _seed_users(db)
        course = make_course_with_text(
            db,
            course_id="enr-idem",
            title="Enr Idem",
            status="published",
            created_by=TEACHER_ID,
        )
        db.commit()

        # First enrollment writes the row + fires the counter.
        enroll_user_in_course(db, STUDENT_ID, course.id)
        # Clear what setup emitted; the assertion is about the SECOND call.
        caplog.clear()

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            again = enroll_user_in_course(db, STUDENT_ID, course.id)

        # Same row returned, no new emission.
        assert again is not None
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.enrollments.created_total" in m]
        assert events == [], "re-enroll must NOT re-fire the counter"

    def test_omits_cohort_id_tag_when_not_provided(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Missing cohort_id must NOT produce a ``cohort_id=`` attribute —
        Datadog treats empty tag values as malformed. ``emit`` drops
        empty-string tags, so the wire line should not contain the key
        at all."""
        _seed_users(db)
        course = make_course_with_text(
            db,
            course_id="enr-no-cohort",
            title="Enr",
            status="published",
            created_by=TEACHER_ID,
        )
        db.commit()

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            enroll_user_in_course(db, STUDENT_ID, course.id)

        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.enrollments.created_total" in m]
        assert events
        for m in events:
            assert "cohort_id=" not in m, f"unexpected cohort_id attribute in: {m}"


class TestMultiCohortRetake:
    """Existence is scoped to (user, course, cohort) — a student may retake a
    course in a different cohort and get a NEW enrollment row, matching the DB
    unique index `(user_id, course_id, COALESCE(cohort_id, sentinel))`. The
    previous (user, course)-only check wrongly returned the old row and blocked
    the retake the index was designed to allow.
    """

    def test_retake_in_different_cohort_creates_new_row(self, db: Session) -> None:
        _seed_users(db)
        course = make_course_with_text(
            db,
            course_id="enr-retake",
            title="Retake",
            status="published",
            created_by=TEACHER_ID,
        )
        db.commit()

        # Solo enrollment (no cohort).
        solo = enroll_user_in_course(db, STUDENT_ID, course.id)

        # A cohort that includes this course.
        cohort = Cohort(
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2030, 1, 1),
            status="active",
        )
        db.add(cohort)
        db.commit()
        db.refresh(cohort)
        db.add(CohortCourse(cohort_id=cohort.id, course_id=course.id))
        db.commit()

        # Retake via the cohort → a NEW row, not the solo one.
        via_cohort = enroll_user_in_course(db, STUDENT_ID, course.id, cohort_id=cohort.id)
        assert via_cohort.id != solo.id
        assert via_cohort.cohort_id == cohort.id

        # Same cohort again → idempotent: returns the existing cohort row.
        again = enroll_user_in_course(db, STUDENT_ID, course.id, cohort_id=cohort.id)
        assert again.id == via_cohort.id

        # Net: exactly two rows for (user, course) — solo + cohort.
        rows = (
            db.query(Enrollment)
            .filter(Enrollment.user_id == STUDENT_ID, Enrollment.course_id == course.id)
            .count()
        )
        assert rows == 2

    def test_solo_reenroll_still_idempotent(self, db: Session) -> None:
        """The None-cohort path must still early-return the existing solo row
        (cohort_id IS NULL match), not create a duplicate."""
        _seed_users(db)
        course = make_course_with_text(
            db,
            course_id="enr-solo-idem",
            title="Solo",
            status="published",
            created_by=TEACHER_ID,
        )
        db.commit()
        first = enroll_user_in_course(db, STUDENT_ID, course.id)
        again = enroll_user_in_course(db, STUDENT_ID, course.id)
        assert again.id == first.id
        rows = (
            db.query(Enrollment)
            .filter(Enrollment.user_id == STUDENT_ID, Enrollment.course_id == course.id)
            .count()
        )
        assert rows == 1
