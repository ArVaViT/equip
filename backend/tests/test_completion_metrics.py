"""Tests for ``equip.completion.course_avg_pct`` emission in
``sync_enrollment_progress``.

The Course Engagement dashboard's completion-rate tile is the
load-bearing consumer of this metric. The test seeds a tiny course
with one gradable chapter, completes it, calls
``sync_enrollment_progress``, and asserts the metric fired with
``course_id`` + ``value=100`` shape.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from app.services.course_service import sync_enrollment_progress

from ._cv_helpers import make_course_with_text, make_module_with_text
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.orm import Session


def _seed_student_and_teacher(db: Session) -> None:
    for user_id, role, email in [
        (TEACHER_ID, UserRole.TEACHER.value, "teacher@e.com"),
        (STUDENT_ID, UserRole.STUDENT.value, "student@e.com"),
    ]:
        if db.query(User).filter(User.id == user_id).first() is None:
            db.add(User(id=user_id, email=email, full_name="T", role=role))
    db.flush()


def _seed_course_with_one_quiz_chapter(db: Session, course_id: str) -> str:
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="Completion test",
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
        title="Chapter",
        order_index=0,
        chapter_type="quiz",  # gradable
    )
    db.add(chapter)
    db.flush()
    return chapter.id


class TestCompletionMetricEmission:
    def test_emits_course_avg_pct_on_progress_recompute(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _seed_student_and_teacher(db)
        chapter_id = _seed_course_with_one_quiz_chapter(db, "comp-1")
        course_id = "comp-1"
        db.add(
            Enrollment(
                id=f"enr-{course_id}",
                user_id=STUDENT_ID,
                course_id=course_id,
                progress=0,
            )
        )
        db.add(
            ChapterProgress(
                id=uuid.uuid4(),
                user_id=STUDENT_ID,
                chapter_id=chapter_id,
                completed=True,
                completion_type="self",
            )
        )
        db.commit()

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            enrollment = sync_enrollment_progress(db, STUDENT_ID, course_id)

        assert enrollment is not None
        assert enrollment.progress == 100

        metric_messages = [rec.getMessage() for rec in caplog.records if rec.name == "equip.metric"]
        completion = [m for m in metric_messages if "equip.completion.course_avg_pct" in m]
        assert completion, "expected at least one course_avg_pct event"
        # Should carry ``value=100.0`` (full completion) and the
        # course_id tag for the dashboard's per-course filter.
        assert any("value=100.0" in m for m in completion)
        assert any(f"course_id={course_id}" in m for m in completion)

    def test_emits_zero_when_no_gradable_chapters(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Course with zero gradable chapters → progress=0 → metric
        emits value=0.0. The dashboard reading this shouldn't see a
        skipped event; absence-of-data would look like a regression."""
        _seed_student_and_teacher(db)
        course = make_course_with_text(
            db,
            course_id="comp-empty",
            title="No gradable",
            status="published",
            created_by=TEACHER_ID,
        )
        db.add(
            Enrollment(
                id="enr-empty",
                user_id=STUDENT_ID,
                course_id=course.id,
                progress=0,
            )
        )
        db.commit()

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            enrollment = sync_enrollment_progress(db, STUDENT_ID, course.id)

        assert enrollment is not None
        assert enrollment.progress == 0
        messages = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        completion = [m for m in messages if "equip.completion.course_avg_pct" in m]
        assert completion
        assert any("value=0.0" in m for m in completion)
