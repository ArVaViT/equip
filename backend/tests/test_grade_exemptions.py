"""«Освобождение» — excusing a student from work (D6).

The design flags the same mistake twice, and it is the easy one to make:
removing the item from the *grade* while leaving it in the *progress*. The
excused student then sits at 90-something percent complete forever, and the
certificate gate — which needs progress 100 — becomes permanently
unsatisfiable for exactly the sick teenager the exemption exists to help.

So every test here checks both denominators, not one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.assignment import Assignment
from app.models.audit_log import AuditLog
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.grade_exemption import GradeExemption
from app.models.quiz import Quiz
from app.services.grade_calculator import (
    calculate_all_student_grades,
    calculate_student_grade_for_course,
)
from app.services.grade_exemption_service import apply_exemption, remove_exemption

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID


def _course_with_two_assignments(db: Session, teacher, course_id: str = "c-excuse") -> tuple[Course, list]:
    """A course whose grade rests entirely on two assignments."""
    course = Course(
        id=course_id,
        status="published",
        created_by=teacher.id,
        quiz_weight=0,
        assignment_weight=100,
    )
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()

    assignments = []
    for i in range(2):
        chapter = Chapter(
            id=f"{course_id}-ch{i}",
            module_id=module.id,
            order_index=i,
            chapter_type="assignment",
            title=f"Ch{i}",
        )
        db.add(chapter)
        db.flush()
        assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
        db.add(assignment)
        assignments.append(assignment)

    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.commit()
    return course, assignments


def test_an_excused_item_leaves_both_denominators(db: Session, teacher, student) -> None:
    """One of two assignments done, the other excused, means 100% — not 50%.

    Leaving the excused item in the denominator is mercy that costs exactly as
    much as no mercy.
    """
    from app.models.assignment import AssignmentSubmission

    course, (done, waived) = _course_with_two_assignments(db, teacher)
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=done.id,
            student_id=STUDENT_ID,
            status="graded",
            grade=100,
            graded_by=teacher.id,
        )
    )
    db.commit()

    before = calculate_student_grade_for_course(db, course, STUDENT_ID)
    assert before.final_score == 50.0, "one of two done, nothing excused yet"

    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
        teacher_id=teacher.id,
        reason="Hospitalised",
    )
    db.commit()

    after = calculate_student_grade_for_course(db, course, STUDENT_ID)
    assert after.final_score == 100.0


def test_an_exemption_completes_the_chapter_so_progress_can_reach_100(db: Session, teacher, student) -> None:
    """The half the design calls a blocker.

    Without this the excused student never reaches progress 100, so the
    certificate gate can never be satisfied — the feature would block the very
    person it exists for.
    """
    course, (_done, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-progress")

    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
        teacher_id=teacher.id,
    )
    db.commit()

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.user_id == STUDENT_ID, ChapterProgress.chapter_id == "c-excuse-progress-ch1")
        .first()
    )
    assert progress is not None
    assert progress.completed is True
    assert progress.completion_type == "excused", "and marked as waived, not as done"


def test_removing_an_exemption_reverts_only_what_it_created(db: Session, teacher, student) -> None:
    course, (_done, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-revert")

    # The student genuinely finished the first chapter themselves.
    db.add(
        ChapterProgress(
            user_id=STUDENT_ID,
            chapter_id="c-excuse-revert-ch0",
            completed=True,
            completion_type="self",
            completed_at=datetime.now(UTC),
        )
    )
    db.commit()

    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
        teacher_id=teacher.id,
    )
    db.commit()
    remove_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
    )
    db.commit()

    waived_progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.chapter_id == "c-excuse-revert-ch1", ChapterProgress.user_id == STUDENT_ID)
        .first()
    )
    own_progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.chapter_id == "c-excuse-revert-ch0", ChapterProgress.user_id == STUDENT_ID)
        .first()
    )

    assert waived_progress.completed is False, "the waived chapter is open again"
    assert own_progress.completed is True, "the student's own work is untouched"
    assert own_progress.completion_type == "self"


def test_a_chapter_the_student_already_finished_is_not_relabelled(db: Session, teacher, student) -> None:
    """Excusing work someone already did must not erase that they did it."""
    course, (done, _waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-done")
    db.add(
        ChapterProgress(
            user_id=STUDENT_ID,
            chapter_id="c-excuse-done-ch0",
            completed=True,
            completion_type="self",
            completed_at=datetime.now(UTC),
        )
    )
    db.commit()

    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=done.id,
        teacher_id=teacher.id,
    )
    db.commit()

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.chapter_id == "c-excuse-done-ch0", ChapterProgress.user_id == STUDENT_ID)
        .first()
    )
    assert progress.completion_type == "self"


def test_excusing_twice_is_a_no_op(db: Session, teacher, student) -> None:
    """A second waiver must not create a row the inverse would half revert."""
    course, (_done, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-twice")

    for _ in range(2):
        apply_exemption(
            db,
            student_id=STUDENT_ID,
            course_id=course.id,
            item_type="assignment",
            item_id=waived.id,
            teacher_id=teacher.id,
        )
    db.commit()

    assert db.query(GradeExemption).filter(GradeExemption.course_id == course.id).count() == 1


# --------------------------------------------------------------------------
# the whole-class path, which computes the same numbers a different way
# --------------------------------------------------------------------------


def test_the_class_view_drops_the_excused_score_with_its_slot(db: Session, teacher, student) -> None:
    """Excusing work already submitted must not inflate the average.

    The trap: the denominator drops the excused item while its score stays in
    the numerator. Two assignments at 100 and 40, excused from the 40, then
    140/1 = 140%. The single-student path can't hit this because it filters the
    ids before it reads any scores; the class view reads first and filters
    after, so it has to be checked separately.
    """
    from app.models.assignment import AssignmentSubmission

    course, (kept, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-batch")
    for assignment, grade in ((kept, 100), (waived, 40)):
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment.id,
                student_id=STUDENT_ID,
                status="graded",
                grade=grade,
                graded_by=teacher.id,
            )
        )
    db.commit()

    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
        teacher_id=teacher.id,
    )
    db.commit()

    (row,) = calculate_all_student_grades(db, course)
    assert row["breakdown"].final_score == 100.0

    solo = calculate_student_grade_for_course(db, course, STUDENT_ID)
    assert row["breakdown"].final_score == solo.final_score, "the two surfaces must agree"


def test_one_students_exemption_does_not_touch_another(db: Session, teacher, student) -> None:
    """The class view resolves exemptions per student, not per course."""
    from app.models.assignment import AssignmentSubmission
    from app.models.user import User

    other_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    db.add(User(id=other_id, email="other@example.com", full_name="Other", role="student"))
    course, (kept, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-two-students")
    db.add(Enrollment(id="enr-other", user_id=other_id, course_id=course.id, progress=0))
    for sid in (STUDENT_ID, other_id):
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=kept.id,
                student_id=sid,
                status="graded",
                grade=100,
                graded_by=teacher.id,
            )
        )
    db.commit()

    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
        teacher_id=teacher.id,
    )
    db.commit()

    by_student = {r["student_id"]: r["breakdown"].final_score for r in calculate_all_student_grades(db, course)}
    assert by_student[str(STUDENT_ID)] == 100.0, "excused from the second assignment"
    assert by_student[str(other_id)] == 50.0, "not excused, still owes it"


# --------------------------------------------------------------------------
# the route
# --------------------------------------------------------------------------


def test_the_route_excuses_and_writes_it_down(client, db: Session, teacher, student) -> None:
    course, (_done, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-route")

    resp = client.post(
        f"/api/v1/grades/course/{course.id}/student/{STUDENT_ID}/exemptions",
        json={"item_type": "assignment", "item_id": str(waived.id), "reason": "Bereavement"},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["reason"] == "Bereavement"

    entry = db.query(AuditLog).filter(AuditLog.action == "grade_exemption_created").first()
    assert entry is not None, "waiving work is a decision someone will be asked about"
    assert entry.details["reason"] == "Bereavement"


def test_work_from_another_course_cannot_be_excused(client, db: Session, teacher, student) -> None:
    """A teacher's authority stops at their own course.

    Both ids are real; only the pairing is wrong. Without the course scope the
    lookup happily finds the item and writes an exemption against someone
    else's course.
    """
    mine, _items = _course_with_two_assignments(db, teacher, course_id="c-excuse-mine")
    _theirs, (_kept, elsewhere) = _course_with_two_assignments(db, teacher, course_id="c-excuse-theirs")

    resp = client.post(
        f"/api/v1/grades/course/{mine.id}/student/{STUDENT_ID}/exemptions",
        json={"item_type": "assignment", "item_id": str(elsewhere.id)},
    )

    assert resp.status_code == 404
    assert db.query(GradeExemption).filter(GradeExemption.course_id == mine.id).count() == 0


def test_an_exemption_cannot_be_removed_through_another_course(client, db: Session, teacher, student) -> None:
    """Deleting is scoped the same way creating is, or the scope means nothing."""
    mine, _items = _course_with_two_assignments(db, teacher, course_id="c-excuse-del-mine")
    theirs, (_kept, elsewhere) = _course_with_two_assignments(db, teacher, course_id="c-excuse-del-theirs")
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=theirs.id,
        item_type="assignment",
        item_id=elsewhere.id,
        teacher_id=teacher.id,
    )
    db.commit()

    resp = client.delete(f"/api/v1/grades/course/{mine.id}/student/{STUDENT_ID}/exemptions/assignment/{elsewhere.id}")

    assert resp.status_code == 404
    assert db.query(GradeExemption).filter(GradeExemption.course_id == theirs.id).count() == 1


def test_excusing_work_that_does_not_exist_is_a_404(client, db: Session, teacher, student) -> None:
    course, _items = _course_with_two_assignments(db, teacher, course_id="c-excuse-404")

    resp = client.post(
        f"/api/v1/grades/course/{course.id}/student/{STUDENT_ID}/exemptions",
        json={"item_type": "quiz", "item_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 404


def test_an_excused_chapter_cannot_be_un_completed_by_hand(client, db: Session, teacher, student) -> None:
    """The two halves of an exemption stay together.

    Un-completing the chapter directly would leave the work out of the grade
    while the student's progress fell below 100 — certificate blocked, and no
    sign anywhere of why. The exemption is the thing to remove; it undoes both.
    """
    course, (_done, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-uncomplete")
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
        teacher_id=teacher.id,
    )
    db.commit()

    resp = client.put(f"/api/v1/progress/chapter/c-excuse-uncomplete-ch1/student/{STUDENT_ID}/incomplete")

    assert resp.status_code == 409, resp.text
    progress = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.chapter_id == "c-excuse-uncomplete-ch1",
            ChapterProgress.user_id == STUDENT_ID,
        )
        .first()
    )
    assert progress.completed is True


def test_quiz_exemptions_work_the_same_way(db: Session, teacher, student) -> None:
    course = Course(id="c-excuse-quiz", status="published", created_by=teacher.id)
    db.add(course)
    module = Module(id="c-excuse-quiz-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-excuse-quiz-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Ch")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=70)
    db.add(quiz)
    db.add(Enrollment(id="enr-excuse-quiz", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()

    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="quiz",
        item_id=quiz.id,
        teacher_id=teacher.id,
    )
    db.commit()

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.chapter_id == chapter.id, ChapterProgress.user_id == STUDENT_ID)
        .first()
    )
    assert progress is not None
    assert progress.completion_type == "excused"
