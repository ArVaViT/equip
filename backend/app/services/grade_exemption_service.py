"""Excusing a student from a piece of work, and taking it back (D6).

The whole point is that an exemption lands in two places at once. Removing the
item from the grade alone leaves the student short of progress 100, so the
certificate gate becomes permanently unsatisfiable — for exactly the sick
teenager or the late-joining adult the feature exists to serve. The design
names that as a blocker twice, and it is the easy mistake to make: the grade is
where you think of an exemption, the progress is where it actually bites.

So creating an exemption:

1. writes the row;
2. marks the item's chapter complete with ``completion_type='excused'``;
3. resyncs the enrolment's progress.

Removing one reverts exactly and only what it created — hence the distinct
completion type, so a teacher's own manual completion of the same chapter is
left alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.assignment import Assignment
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Module
from app.models.grade_exemption import GradeExemption
from app.models.quiz import Quiz
from app.services.course_service._enrollment import sync_enrollment_progress

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

EXCUSED = "excused"


def chapter_for_item(db: Session, *, item_type: str, item_id: UUID, course_id: str | None = None) -> str | None:
    """The chapter an excusable item belongs to, or ``None`` if it is gone.

    Pass ``course_id`` and the lookup also refuses items that live in a
    different course. A teacher's authority is over their own course, and an
    unscoped id is a way around that: excusing a student from work set by
    someone else is not this endpoint's business.
    """
    model = Quiz if item_type == "quiz" else Assignment
    query = db.query(model.chapter_id).filter(model.id == item_id)
    if course_id is not None:
        query = query.join(Chapter, Chapter.id == model.chapter_id).join(Module, Module.id == Chapter.module_id)
        query = query.filter(Module.course_id == course_id)
    return query.scalar()


def excused_item_ids(db: Session, *, student_id: UUID | str, course_id: str) -> tuple[set, set]:
    """``(quiz_ids, assignment_ids)`` this student is excused from."""
    rows = (
        db.query(GradeExemption.item_type, GradeExemption.item_id)
        .filter(GradeExemption.student_id == student_id, GradeExemption.course_id == course_id)
        .all()
    )
    quizzes = {r.item_id for r in rows if r.item_type == "quiz"}
    assignments = {r.item_id for r in rows if r.item_type == "assignment"}
    return quizzes, assignments


def apply_exemption(
    db: Session,
    *,
    student_id: UUID,
    course_id: str,
    item_type: str,
    item_id: UUID,
    teacher_id: UUID,
    reason: str | None = None,
) -> GradeExemption:
    """Excuse a student, in the grade and in the progress, atomically.

    Idempotent: excusing the same work twice returns the existing row rather
    than creating a second one the inverse would only half revert.
    """
    existing = (
        db.query(GradeExemption)
        .filter(
            GradeExemption.student_id == student_id,
            GradeExemption.course_id == course_id,
            GradeExemption.item_type == item_type,
            GradeExemption.item_id == item_id,
        )
        .first()
    )
    if existing is not None:
        return existing

    exemption = GradeExemption(
        student_id=student_id,
        course_id=course_id,
        item_type=item_type,
        item_id=item_id,
        reason=reason,
        created_by=teacher_id,
    )
    db.add(exemption)

    chapter_id = chapter_for_item(db, item_type=item_type, item_id=item_id)
    if chapter_id is not None:
        progress = (
            db.query(ChapterProgress)
            .filter(ChapterProgress.user_id == student_id, ChapterProgress.chapter_id == chapter_id)
            .first()
        )
        if progress is None:
            progress = ChapterProgress(
                user_id=student_id,
                chapter_id=chapter_id,
                completed=True,
                completion_type=EXCUSED,
                completed_by=teacher_id,
            )
            db.add(progress)
        elif not progress.completed:
            # An unfinished chapter becomes complete *as excused*. A chapter the
            # student had already finished is left exactly as it is — recording
            # it as waived would erase the fact that they did the work.
            progress.completed = True
            progress.completion_type = EXCUSED
            progress.completed_by = teacher_id

    db.flush()
    sync_enrollment_progress(db, student_id, course_id)
    return exemption


def remove_exemption(
    db: Session, *, student_id: UUID, course_id: str, item_type: str, item_id: UUID
) -> GradeExemption | None:
    """Take an exemption back, reverting only what it created.

    Progress rows marked ``'excused'`` are undone; a chapter the teacher had
    completed manually, or the student had genuinely finished, is untouched.

    Scoped to the course: the caller's authority is over one course, so an
    exemption belonging to another one must stay out of reach even when the
    item id is guessed correctly.
    """
    exemption = (
        db.query(GradeExemption)
        .filter(
            GradeExemption.student_id == student_id,
            GradeExemption.course_id == course_id,
            GradeExemption.item_type == item_type,
            GradeExemption.item_id == item_id,
        )
        .first()
    )
    if exemption is None:
        return None

    chapter_id = chapter_for_item(db, item_type=item_type, item_id=item_id)
    if chapter_id is not None:
        progress = (
            db.query(ChapterProgress)
            .filter(
                ChapterProgress.user_id == student_id,
                ChapterProgress.chapter_id == chapter_id,
                ChapterProgress.completion_type == EXCUSED,
            )
            .first()
        )
        if progress is not None:
            progress.completed = False
            progress.completion_type = "self"
            progress.completed_by = None

    db.delete(exemption)
    db.flush()
    sync_enrollment_progress(db, student_id, course_id)
    return exemption
