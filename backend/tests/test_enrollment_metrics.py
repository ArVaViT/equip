"""Tests for ``equip.enrollments.created_total`` emission.

The Course Engagement dashboard's enrollment-rate tile reads from
this counter; the dropoff_count derived metric uses it as a
denominator. The metric MUST fire exactly once per *new* enrollment
and MUST NOT fire when the existing-row early return path is taken
(idempotent re-enroll).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
