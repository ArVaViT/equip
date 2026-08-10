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

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

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
        # Soft-deleted chapters are already out of every grade calculation, so
        # an exemption there can never move a number. Accepting one answers 201
        # and writes an audit entry for a decision with no effect — and one that
        # would quietly start applying if the chapter were ever restored.
        query = query.filter(
            Module.course_id == course_id,
            Chapter.deleted_at.is_(None),
            Module.deleted_at.is_(None),
        )
    return query.scalar()


def _every_item_excused(db: Session, *, student_id: UUID, chapter_id: str) -> bool:
    """Is there nothing left in this chapter for this student to do?

    A chapter is not one piece of work. It can hold two quizzes, or a quiz and
    an assignment, and completing it because *one* of them was waived hands the
    student a finished chapter while the rest sits unsubmitted — progress 100,
    certificate gate open, work still owed. So the chapter closes only when
    every gradable item in it is excused, and reopens the moment one isn't.

    Deliberately about exemptions alone, not "excused or already done": a
    chapter the student partly finished is closed by the machinery that
    finished it, and it is not this function's business to close it for them.
    """
    quiz_ids = [r[0] for r in db.query(Quiz.id).filter(Quiz.chapter_id == chapter_id).all()]
    assignment_ids = [r[0] for r in db.query(Assignment.id).filter(Assignment.chapter_id == chapter_id).all()]
    if not quiz_ids and not assignment_ids:
        return False

    excused_quizzes, excused_assignments = _excused_ids_for_items(
        db, student_id=student_id, quiz_ids=quiz_ids, assignment_ids=assignment_ids
    )
    return all(q in excused_quizzes for q in quiz_ids) and all(a in excused_assignments for a in assignment_ids)


def _excused_ids_for_items(db: Session, *, student_id: UUID, quiz_ids: list, assignment_ids: list) -> tuple[set, set]:
    rows = (
        db.query(GradeExemption.item_type, GradeExemption.item_id)
        .filter(
            GradeExemption.student_id == student_id,
            GradeExemption.item_id.in_(list(quiz_ids) + list(assignment_ids)),
        )
        .all()
    )
    return (
        {r.item_id for r in rows if r.item_type == "quiz"},
        {r.item_id for r in rows if r.item_type == "assignment"},
    )


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

    chapter_id = chapter_for_item(db, item_type=item_type, item_id=item_id)
    if chapter_id is None:
        raise LookupError("no such quiz or assignment")

    exemption = GradeExemption(
        student_id=student_id,
        course_id=course_id,
        item_type=item_type,
        item_id=item_id,
        chapter_id=chapter_id,
        reason=reason,
        created_by=teacher_id,
    )
    # Two teachers clicking at once used to make one of them a 500: the SELECT
    # above misses for both, and the loser lands on the unique key. The
    # SAVEPOINT keeps that collision from poisoning the caller's transaction so
    # the row the winner wrote can simply be returned — which is what
    # "idempotent" was supposed to mean.
    try:
        with db.begin_nested():
            db.add(exemption)
            db.flush()
    except IntegrityError:
        # Matched against the unique key exactly — (student, item_type, item_id),
        # without the course — or a row that collided would be invisible here and
        # the 500 we just caught would come straight back.
        existing = (
            db.query(GradeExemption)
            .filter(
                GradeExemption.student_id == student_id,
                GradeExemption.item_type == item_type,
                GradeExemption.item_id == item_id,
            )
            .first()
        )
        if existing is None:
            raise
        return existing

    if _every_item_excused(db, student_id=student_id, chapter_id=chapter_id):
        progress = (
            db.query(ChapterProgress)
            .filter(ChapterProgress.user_id == student_id, ChapterProgress.chapter_id == chapter_id)
            .first()
        )
        if progress is None:
            # Same race, other table: the student's own autocomplete or a
            # co-teacher's mark-complete may be inserting this very row.
            # ``upsert_passed_chapter_progress`` handles it the same way.
            try:
                with db.begin_nested():
                    progress = ChapterProgress(
                        user_id=student_id,
                        chapter_id=chapter_id,
                        completed=True,
                        completed_at=datetime.now(UTC),
                        completion_type=EXCUSED,
                        completed_by=teacher_id,
                    )
                    db.add(progress)
                    db.flush()
            except IntegrityError:
                progress = (
                    db.query(ChapterProgress)
                    .filter(ChapterProgress.user_id == student_id, ChapterProgress.chapter_id == chapter_id)
                    .first()
                )
                if progress is None:
                    raise
        if not progress.completed:
            # An unfinished chapter becomes complete *as excused*. A chapter the
            # student had already finished is left exactly as it is — recording
            # it as waived would erase the fact that they did the work.
            progress.completed = True
            progress.completed_at = datetime.now(UTC)
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

    # From the row, not from the item: the item may have been deleted since,
    # and the completion this exemption created still has to be revertible.
    chapter_id = exemption.chapter_id
    db.delete(exemption)
    db.flush()

    # Reopen the chapter only if the student now owes something in it again. A
    # chapter whose other item is still excused has nothing left for them to
    # do, and slamming it shut would close the certificate gate over work that
    # was waived.
    if not _every_item_excused(db, student_id=student_id, chapter_id=chapter_id):
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
            # ``completion_type`` is left as ``'excused'`` deliberately. The row
            # records how the chapter was last completed, and rewriting it to
            # ``'self'`` would claim the student ticked it themselves — a thing
            # that never happened, and indistinguishable afterwards from a
            # chapter they simply started. ``teacher_uncomplete_chapter``
            # refuses the same rewrite for the same reason.
            progress.completed_by = None

    db.flush()
    sync_enrollment_progress(db, student_id, course_id)
    return exemption
