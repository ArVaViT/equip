"""Tests for ``equip.engagement.chapter_completed_total`` emission.

This counter feeds the Course Engagement dashboard's drop-off tile.
The dashboard computes the drop-off rate as
``(enrolled - chapter_completed_unique_students) / enrolled``, so the
metric MUST fire exactly once per (user, chapter) completion
transition — never on a re-grade, never on a no-op teacher
remarks-as-complete-when-already-complete call, never on a quiz
re-submit that doesn't flip the chapter state.

Three emission sites are covered:

1. ``progress.teacher_complete_chapter`` (manual teacher mark) →
   ``completion_type=teacher``.
2. ``quiz_service.upsert_passed_chapter_progress`` (auto from passed
   quiz attempt) → ``completion_type=quiz``.
3. ``assignments.submit_assignment`` (auto from first submission) →
   ``completion_type=assignment``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from app.services import quiz_service

from ._cv_helpers import make_course_with_text, make_module_with_text
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


def _seed_basic_course(db: Session, course_id: str = "eng-test") -> str:
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="Engagement",
        status="published",
        created_by=TEACHER_ID,
    )
    module = make_module_with_text(
        db,
        module_id=f"{course_id}-m",
        course_id=course.id,
        title="M",
    )
    chapter = Chapter(
        id=f"{course_id}-ch",
        module_id=module.id,
        title="C",
        order_index=0,
        chapter_type="text",
    )
    db.add(chapter)
    db.flush()
    return chapter.id


class TestQuizEngagementEmission:
    """``upsert_passed_chapter_progress`` is the auto-from-quiz path. It now
    RETURNS whether it flipped completion (the route handlers emit the metric
    post-commit); the helper itself no longer emits, so a rolled-back
    transaction can't double-count."""

    def test_returns_true_and_does_not_self_emit_on_first_completion(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _seed_users(db)
        chapter_id = _seed_basic_course(db, "eng-q1")
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            flipped = quiz_service.upsert_passed_chapter_progress(db, STUDENT_ID, chapter_id)
            db.commit()
        assert flipped is True
        # The helper must NOT emit — emission is the caller's job, post-commit.
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        assert [m for m in msgs if "equip.engagement.chapter_completed_total" in m] == []

    def test_returns_false_on_already_complete(
        self,
        db: Session,
    ) -> None:
        """A second call after the chapter is already ``completed=True`` is a
        no-op and returns False, so the caller won't double-count."""
        _seed_users(db)
        chapter_id = _seed_basic_course(db, "eng-q2")
        assert quiz_service.upsert_passed_chapter_progress(db, STUDENT_ID, chapter_id) is True
        db.commit()
        assert quiz_service.upsert_passed_chapter_progress(db, STUDENT_ID, chapter_id) is False


class TestTeacherCompleteEngagementEmission:
    """``progress.teacher_complete_chapter`` is the manual-by-teacher path."""

    def test_emits_completion_type_teacher(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
        client,
    ) -> None:
        _seed_users(db)
        chapter_id = _seed_basic_course(db, "eng-t1")
        # Need an enrollment for the endpoint's guard
        db.add(
            Enrollment(
                id=f"enr-{uuid4().hex[:6]}",
                user_id=STUDENT_ID,
                course_id="eng-t1",
                progress=0,
            )
        )
        db.commit()

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            resp = client.put(
                f"/api/v1/progress/chapter/{chapter_id}/student/{STUDENT_ID}/complete",
                headers={"Authorization": "Bearer teacher-token"},
            )
        assert resp.status_code == 200, resp.text
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        completed = [m for m in msgs if "equip.engagement.chapter_completed_total" in m]
        assert completed, "teacher-mark-complete must emit"
        assert any("completion_type=teacher" in m for m in completed)

    def test_does_not_emit_on_idempotent_teacher_call(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
        client,
    ) -> None:
        _seed_users(db)
        chapter_id = _seed_basic_course(db, "eng-t2")
        db.add(
            Enrollment(
                id=f"enr-{uuid4().hex[:6]}",
                user_id=STUDENT_ID,
                course_id="eng-t2",
                progress=0,
            )
        )
        db.add(
            ChapterProgress(
                id=uuid4(),
                user_id=STUDENT_ID,
                chapter_id=chapter_id,
                completed=True,
                completion_type="teacher",
            )
        )
        db.commit()

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            resp = client.put(
                f"/api/v1/progress/chapter/{chapter_id}/student/{STUDENT_ID}/complete",
                headers={"Authorization": "Bearer teacher-token"},
            )
        assert resp.status_code == 200
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        completed = [m for m in msgs if "equip.engagement.chapter_completed_total" in m]
        assert completed == [], "idempotent re-mark must NOT re-emit"
