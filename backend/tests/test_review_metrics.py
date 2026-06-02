"""Tests for ``equip.reviews.rating_latest`` emission from the
review create/update path.

The Course Engagement dashboard's rating tile is driven by this
gauge — Datadog averages the most-recent rating per (user, course)
over a chosen window. Emission must fire on:

  1. First-time review POST (new row).
  2. Update of an existing review (PUT semantics — same endpoint
     handles both per the API contract).

Emission must NOT fire on the 403 (no-certificate) path, since the
review never persists.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.models.certificate import Certificate
from app.models.review import CourseReview
from app.models.user import User, UserRole

from ._cv_helpers import make_course_with_text
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.orm import Session


def _seed_user_and_course(db: Session, course_id: str) -> None:
    for user_id, role, email in [
        (TEACHER_ID, UserRole.TEACHER.value, "t@e.com"),
        (STUDENT_ID, UserRole.STUDENT.value, "s@e.com"),
    ]:
        if db.query(User).filter(User.id == user_id).first() is None:
            db.add(User(id=user_id, email=email, full_name="X", role=role))
    db.flush()
    make_course_with_text(
        db,
        course_id=course_id,
        title="R",
        status="published",
        created_by=TEACHER_ID,
    )


def _grant_certificate(db: Session, course_id: str) -> None:
    db.add(
        Certificate(
            id=uuid.uuid4(),
            user_id=STUDENT_ID,
            course_id=course_id,
            status="approved",
        )
    )
    db.commit()


class TestReviewMetricEmission:
    def test_emits_rating_latest_on_first_review(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
        student_client,
    ) -> None:
        _seed_user_and_course(db, "rev-1")
        _grant_certificate(db, "rev-1")

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            resp = student_client.post(
                "/api/v1/reviews/course/rev-1",
                json={"rating": 5, "comment": "Great course"},
                headers={"Authorization": "Bearer student-token"},
            )
        assert resp.status_code == 201, resp.text
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.reviews.rating_latest" in m]
        assert events, "expected rating_latest gauge to fire on new review"
        assert any("value=5.0" in m for m in events)
        assert any("course_id=rev-1" in m for m in events)

    def test_emits_rating_latest_on_review_update(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
        student_client,
    ) -> None:
        _seed_user_and_course(db, "rev-2")
        _grant_certificate(db, "rev-2")
        # First post — setup
        student_client.post(
            "/api/v1/reviews/course/rev-2",
            json={"rating": 3, "comment": "ok"},
            headers={"Authorization": "Bearer student-token"},
        )
        caplog.clear()

        # The same endpoint also serves PUT semantics — second POST
        # with a different rating overwrites the row.
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            resp = student_client.post(
                "/api/v1/reviews/course/rev-2",
                json={"rating": 4, "comment": "better"},
                headers={"Authorization": "Bearer student-token"},
            )
        assert resp.status_code == 200
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.reviews.rating_latest" in m]
        assert events, "expected gauge to fire on review update"
        assert any("value=4.0" in m for m in events)

    def test_does_not_emit_without_certificate(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
        student_client,
    ) -> None:
        """403 path — student doesn't have a completion certificate so
        the review is rejected. The gauge MUST NOT fire."""
        _seed_user_and_course(db, "rev-3")
        # No certificate granted.

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            resp = student_client.post(
                "/api/v1/reviews/course/rev-3",
                json={"rating": 5, "comment": "spam"},
                headers={"Authorization": "Bearer student-token"},
            )
        assert resp.status_code == 403
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.reviews.rating_latest" in m]
        assert events == [], "gauge must NOT fire when review is rejected"

        # And no review row was persisted.
        assert db.query(CourseReview).filter(CourseReview.course_id == "rev-3").count() == 0
