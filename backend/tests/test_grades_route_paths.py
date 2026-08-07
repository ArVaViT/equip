"""Targeted error-path tests for ``app.api.v1.grades``.

The existing ``test_certificates_and_grades.py`` covers happy-path
grade flows. This file fills the visible-uncovered paths:

* GET grading config — non-owner non-enrolled student → 403.
* GET grade summary — ``calculate_all_student_grades`` raising
  ``SQLAlchemyError`` → 500 with a clean error envelope.

The route's UUID-string handling on the student_id path param
(``filter(StudentGrade.student_id == student_id)`` with a str)
relies on Postgres native UUID coercion; SQLite's bind processor
rejects raw strings, which is why several other student-id-driven
paths (cohort filter, upsert IntegrityError recovery) are not
exercised here — they're covered by the Postgres schema-smoke job in
CI rather than the in-memory suite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from app.models.enrollment import Enrollment

from ._cv_helpers import make_course_with_text
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    import uuid

    import pytest
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User


def _seed_published_course(db: Session, course_id: str = "g-route") -> str:
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="Test",
        status="published",
        created_by=TEACHER_ID,
        quiz_weight=50,
        assignment_weight=50,
    )
    db.commit()
    return course.id


def _enroll(db: Session, course_id: str, user_id: uuid.UUID = STUDENT_ID) -> None:
    db.add(
        Enrollment(
            id=f"enr-{course_id}-{user_id}",
            user_id=user_id,
            course_id=course_id,
            progress=0,
        )
    )
    db.commit()


class TestGradingConfigVisibility:
    """``GET /grades/course/{course_id}/config`` is readable by the
    course owner, any admin, or an enrolled student. Everyone else
    sees 403 with a generic "Access denied" envelope."""

    def test_non_owner_non_enrolled_student_403(
        self,
        student_client: TestClient,
        db: Session,
        teacher: User,
    ) -> None:
        course_id = _seed_published_course(db)
        r = student_client.get(f"/api/v1/grades/course/{course_id}/config")
        assert r.status_code == 403
        assert "Access denied" in r.json()["detail"]["message"]

    def test_enrolled_student_sees_config(
        self,
        student_client: TestClient,
        db: Session,
        teacher: User,
    ) -> None:
        course_id = _seed_published_course(db)
        _enroll(db, course_id)
        r = student_client.get(f"/api/v1/grades/course/{course_id}/config")
        assert r.status_code == 200

    def test_owner_sees_config(
        self,
        client: TestClient,
        db: Session,
        teacher: User,
    ) -> None:
        course_id = _seed_published_course(db)
        r = client.get(f"/api/v1/grades/course/{course_id}/config")
        assert r.status_code == 200

    def test_admin_sees_config_even_when_not_enrolled(
        self,
        admin_client: TestClient,
        db: Session,
        teacher: User,
    ) -> None:
        course_id = _seed_published_course(db)
        r = admin_client.get(f"/api/v1/grades/course/{course_id}/config")
        assert r.status_code == 200


class TestGradeSummaryErrorPath:
    def test_sqlalchemy_error_maps_to_500(
        self,
        client: TestClient,
        db: Session,
        teacher: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When ``calculate_all_student_grades`` raises a
        ``SQLAlchemyError`` (DB hiccup, lock timeout) the route
        catches it and surfaces a clean 500 envelope rather than a
        bare Internal Server Error trace. Pin both the status code
        and the error message so the frontend's banner mapping
        doesn't silently regress."""
        from app.api.v1 import grades as route_mod

        course_id = _seed_published_course(db)

        def fake_calc(*_a: object, **_k: object) -> None:
            raise SQLAlchemyError("lock timeout")

        monkeypatch.setattr(route_mod, "calculate_all_student_grades", fake_calc)
        r = client.get(f"/api/v1/grades/course/{course_id}/summary")
        assert r.status_code == 500
        assert "Grade calculation failed" in r.json()["detail"]["message"]
