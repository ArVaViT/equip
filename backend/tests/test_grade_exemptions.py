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


def test_the_progress_detail_names_the_work_behind_each_chapter(client, db: Session, teacher, student) -> None:
    """The teacher's screen needs the item id for work nobody has touched.

    That is the whole case for an exemption — the student never submitted —
    and it is precisely when ``assignment_result`` is null, so the screen has
    nothing else to point at.
    """
    course, (first, _second) = _course_with_two_assignments(db, teacher, course_id="c-excuse-detail")

    resp = client.get(f"/api/v1/progress/course/{course.id}/students/{STUDENT_ID}/detail")

    assert resp.status_code == 200, resp.text
    chapters = {c["id"]: c for c in resp.json()["chapters"]}
    row = chapters["c-excuse-detail-ch0"]
    assert row["assignment_result"] is None, "nothing submitted — the case that matters"
    assert row["gradable_item"] == {"type": "assignment", "id": str(first.id)}


def test_an_excused_chapter_says_so_on_the_teachers_screen(client, db: Session, teacher, student) -> None:
    """An excused chapter must not read as work the student did.

    It is a green tick either way; only the label carries the difference, and
    the label is what a teacher signs a certificate on.
    """
    course, (_first, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-label")
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
        teacher_id=teacher.id,
    )
    db.commit()

    resp = client.get(f"/api/v1/progress/course/{course.id}/students/{STUDENT_ID}/detail")

    chapters = {c["id"]: c for c in resp.json()["chapters"]}
    assert chapters["c-excuse-label-ch1"]["completed"] is True
    assert chapters["c-excuse-label-ch1"]["completed_by"] == "excused"


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


# --------------------------------------------------------------------------
# A chapter is not one piece of work, and a category is not one student
#
# Every case below was found by an adversarial pass over the first version of
# this feature, which assumed one item per chapter and one answer per course.
# --------------------------------------------------------------------------


def _one_chapter_two_items(db: Session, teacher, course_id: str):
    """A single gradable chapter carrying BOTH a quiz and an assignment."""
    course = Course(id=course_id, status="published", created_by=teacher.id, quiz_weight=50, assignment_weight=50)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"{course_id}-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="C")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add_all([quiz, assignment])
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.commit()
    return course, chapter, quiz, assignment


def _mixed_course(db: Session, teacher, course_id: str):
    """One quiz chapter and one assignment chapter, weighted 70/30."""
    course = Course(id=course_id, status="published", created_by=teacher.id, quiz_weight=70, assignment_weight=30)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    qch = Chapter(id=f"{course_id}-chq", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
    ach = Chapter(id=f"{course_id}-cha", module_id=module.id, order_index=1, chapter_type="assignment", title="A")
    db.add_all([qch, ach])
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=qch.id)
    assignment = Assignment(id=uuid.uuid4(), chapter_id=ach.id, max_score=100)
    db.add_all([quiz, assignment])
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.commit()
    return course, quiz, assignment


def test_excusing_one_item_leaves_a_chapter_that_still_owes_work_open(db: Session, teacher, student) -> None:
    """One quiz waived does not finish a chapter that also holds an assignment.

    Otherwise progress reaches 100 and the certificate gate opens while the
    assignment sits unsubmitted — a finished course with work still owed.
    """
    course, _chapter, quiz, _assignment = _one_chapter_two_items(db, teacher, "c-excuse-partial")

    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="quiz",
        item_id=quiz.id,
        teacher_id=teacher.id,
    )
    db.commit()

    enrolment = db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID, Enrollment.course_id == course.id).first()
    assert enrolment.progress != 100


def test_a_chapter_closes_only_when_every_item_in_it_is_excused(db: Session, teacher, student) -> None:
    course, chapter, quiz, assignment = _one_chapter_two_items(db, teacher, "c-excuse-both")

    for item_type, item_id in (("quiz", quiz.id), ("assignment", assignment.id)):
        apply_exemption(
            db,
            student_id=STUDENT_ID,
            course_id=course.id,
            item_type=item_type,
            item_id=item_id,
            teacher_id=teacher.id,
        )
    db.commit()

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.user_id == STUDENT_ID, ChapterProgress.chapter_id == chapter.id)
        .first()
    )
    assert progress.completed is True
    assert progress.completion_type == "excused"


def test_returning_one_item_reopens_the_chapter_it_belongs_to(db: Session, teacher, student) -> None:
    """The inverse of the rule above, and it has to be the same rule.

    The assignment stays waived, but the quiz is owed again — so there IS
    something left to do in that chapter and it must not stay closed.
    """
    course, chapter, quiz, assignment = _one_chapter_two_items(db, teacher, "c-excuse-reopen")
    for item_type, item_id in (("quiz", quiz.id), ("assignment", assignment.id)):
        apply_exemption(
            db,
            student_id=STUDENT_ID,
            course_id=course.id,
            item_type=item_type,
            item_id=item_id,
            teacher_id=teacher.id,
        )
    db.commit()

    remove_exemption(db, student_id=STUDENT_ID, course_id=course.id, item_type="quiz", item_id=quiz.id)
    db.commit()

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.user_id == STUDENT_ID, ChapterProgress.chapter_id == chapter.id)
        .first()
    )
    assert progress.completed is False


def test_two_quizzes_in_one_chapter_need_both_waived(db: Session, teacher, student) -> None:
    course = Course(id="c-excuse-2q", status="published", created_by=teacher.id, quiz_weight=100, assignment_weight=0)
    db.add(course)
    module = Module(id="c-excuse-2q-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-excuse-2q-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="C")
    db.add(chapter)
    db.flush()
    first, second = Quiz(id=uuid.uuid4(), chapter_id=chapter.id), Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add_all([first, second])
    db.add(Enrollment(id="enr-c-excuse-2q", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()

    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="quiz",
        item_id=first.id,
        teacher_id=teacher.id,
    )
    db.commit()

    enrolment = db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID, Enrollment.course_id == course.id).first()
    assert enrolment.progress != 100, "the second quiz is still owed"


def test_work_done_after_being_excused_survives_the_exemption_being_lifted(db: Session, teacher, student) -> None:
    """Excused, recovered, passed the quiz anyway, teacher lifts the waiver.

    The completion has to change hands from the exemption to the student the
    moment they pass, or lifting the waiver reopens a chapter they earned.
    """
    from app.models.quiz import QuizAttempt
    from app.services.quiz_service import upsert_passed_chapter_progress

    course = Course(
        id="c-excuse-did-it", status="published", created_by=teacher.id, quiz_weight=100, assignment_weight=0
    )
    db.add(course)
    module = Module(id="c-excuse-did-it-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-excuse-did-it-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="C")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.add(Enrollment(id="enr-c-excuse-did-it", user_id=STUDENT_ID, course_id=course.id, progress=0))
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

    db.add(
        QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=STUDENT_ID,
            score=100,
            max_score=100,
            passed=True,
            completed_at=datetime.now(UTC),
        )
    )
    upsert_passed_chapter_progress(db, STUDENT_ID, chapter.id)
    db.commit()

    remove_exemption(db, student_id=STUDENT_ID, course_id=course.id, item_type="quiz", item_id=quiz.id)
    db.commit()

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.user_id == STUDENT_ID, ChapterProgress.chapter_id == chapter.id)
        .first()
    )
    assert progress.completed is True, "they passed it"
    assert progress.completion_type == "quiz", "and the record says who did the work"


def test_the_two_surfaces_agree_when_a_whole_category_is_excused(db: Session, teacher, student) -> None:
    """Excusing the only quiz redistributes the weights — on both paths or neither.

    The single-student path asked whether the category was live using the
    student's remaining items; the class list asked course-wide. Same student,
    80% on one screen and 24% on the other.
    """
    from app.models.assignment import AssignmentSubmission
    from app.models.quiz import QuizAttempt

    course, quiz, assignment = _mixed_course(db, teacher, "c-excuse-agree")
    db.add(
        QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=STUDENT_ID,
            score=20,
            max_score=100,
            completed_at=datetime.now(UTC),
        )
    )
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="graded",
            grade=80,
            graded_by=teacher.id,
        )
    )
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

    solo = calculate_student_grade_for_course(db, course, STUDENT_ID)
    (row,) = calculate_all_student_grades(db, course)

    assert solo.final_score == row["breakdown"].final_score
    assert solo.final_score == 80.0, "the quiz is no longer theirs to sit; the assignment carries the grade"


def test_a_student_excused_from_everything_is_not_assessed(client, db: Session, teacher, student) -> None:
    """Not assessed — and the certificate gate holds.

    Excusing an item also completes its chapter, so a student excused from
    every piece of work reaches progress 100 without a single thing having been
    assessed. Reading that as "passed by completion" would print a certificate
    for a course nobody graded.
    """
    course, quiz, assignment = _mixed_course(db, teacher, "c-excuse-everything")
    for item_type, item_id in (("quiz", quiz.id), ("assignment", assignment.id)):
        apply_exemption(
            db,
            student_id=STUDENT_ID,
            course_id=course.id,
            item_type=item_type,
            item_id=item_id,
            teacher_id=teacher.id,
        )
    db.commit()

    solo = calculate_student_grade_for_course(db, course, STUDENT_ID)
    (row,) = calculate_all_student_grades(db, course)

    assert solo.result_state == "not_assessed"
    assert row["breakdown"].result_state == "not_assessed", "and the class list says the same"
    assert solo.has_quiz_items is True, "the course still contains a quiz — that is a fact about the syllabus"

    enrolment = db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID, Enrollment.course_id == course.id).first()
    assert enrolment.progress == 100, "every chapter is waived, so the progress gate alone would let them through"


def test_the_certificate_gate_refuses_a_student_with_nothing_assessed(
    student_client, db: Session, teacher, student
) -> None:
    course, quiz, assignment = _mixed_course(db, teacher, "c-excuse-cert")
    for item_type, item_id in (("quiz", quiz.id), ("assignment", assignment.id)):
        apply_exemption(
            db,
            student_id=STUDENT_ID,
            course_id=course.id,
            item_type=item_type,
            item_id=item_id,
            teacher_id=teacher.id,
        )
    db.commit()

    resp = student_client.post(f"/api/v1/certificates/course/{course.id}")

    assert resp.status_code == 400, resp.text
    # The refusal now travels as codes rather than a sentence, so the card that
    # already explains this on the student's course page renders it in whatever
    # language they read (D9). The rule is unchanged: excusing every item takes
    # progress to 100 without a single thing having been assessed, and a
    # certificate would be certifying nothing.
    assert [b["code"] for b in resp.json()["detail"]["context"]["blockers"]] == ["not_assessed"]


def test_an_exemption_survives_its_item_being_deleted(db: Session, teacher, student) -> None:
    """Deleting the work must not strand a completion nobody can undo.

    `item_id` is polymorphic, so it carries no foreign key, and assignments are
    hard-deleted. Reaching the chapter *through* the item meant that removing
    the exemption afterwards silently skipped the revert — leaving the chapter
    complete as 'excused', progress counting it toward the certificate, and the
    guard on the incomplete route pointing at a row that no longer existed.
    """
    course, (_kept, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-deleted")
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
        teacher_id=teacher.id,
    )
    db.commit()

    db.delete(waived)
    db.commit()

    remove_exemption(db, student_id=STUDENT_ID, course_id=course.id, item_type="assignment", item_id=waived.id)
    db.commit()

    progress = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.chapter_id == "c-excuse-deleted-ch1",
            ChapterProgress.user_id == STUDENT_ID,
        )
        .first()
    )
    assert progress.completed is False, "the chapter reopened even though the item was gone"


def test_returning_work_keeps_the_record_of_how_it_was_completed(db: Session, teacher, student) -> None:
    """`completion_type` must not be rewritten to 'self' on the way out.

    'self' means the student ticked the chapter themselves. That never
    happened, and afterwards the row is indistinguishable from one they
    started and abandoned — the same rewrite `teacher_uncomplete_chapter`
    refuses for the same reason.
    """
    course, (_kept, waived) = _course_with_two_assignments(db, teacher, course_id="c-excuse-provenance")
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=waived.id,
        teacher_id=teacher.id,
    )
    db.commit()
    remove_exemption(db, student_id=STUDENT_ID, course_id=course.id, item_type="assignment", item_id=waived.id)
    db.commit()

    progress = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.chapter_id == "c-excuse-provenance-ch1",
            ChapterProgress.user_id == STUDENT_ID,
        )
        .first()
    )
    assert progress.completed is False
    assert progress.completion_type == "excused", "how it was last completed is still true"


def test_a_soft_deleted_chapter_cannot_be_excused_from(client, db: Session, teacher, student) -> None:
    """An exemption there could never move a number, so it must not be offered.

    Deleted chapters are already out of every grade calculation. Accepting one
    writes an audit entry for a decision with no effect — and one that would
    quietly start applying if the chapter were ever restored.
    """
    course, (first, _second) = _course_with_two_assignments(db, teacher, course_id="c-excuse-deleted-ch")
    chapter = db.query(Chapter).filter(Chapter.id == "c-excuse-deleted-ch-ch0").first()
    chapter.deleted_at = datetime.now(UTC)
    db.commit()

    resp = client.post(
        f"/api/v1/grades/course/{course.id}/student/{STUDENT_ID}/exemptions",
        json={"item_type": "assignment", "item_id": str(first.id)},
    )

    assert resp.status_code == 404, resp.text


def test_marking_a_chapter_complete_by_hand_is_written_down(client, db: Session, teacher, student) -> None:
    """`enrollment.progress` is the whole certificate gate.

    Doing this on every gradable chapter takes a student from nothing to
    eligible — a bigger decision than editing a displayed grade, which has been
    audited all along.
    """
    _course, _items = _course_with_two_assignments(db, teacher, course_id="c-audit-complete")

    resp = client.put(f"/api/v1/progress/chapter/c-audit-complete-ch0/student/{STUDENT_ID}/complete")
    assert resp.status_code == 200, resp.text

    entry = db.query(AuditLog).filter(AuditLog.action == "chapter_completed_by_teacher").first()
    assert entry is not None
    assert entry.details["student_id"] == str(STUDENT_ID)

    client.put(f"/api/v1/progress/chapter/c-audit-complete-ch0/student/{STUDENT_ID}/incomplete")
    removed = db.query(AuditLog).filter(AuditLog.action == "chapter_completion_removed_by_teacher").first()
    assert removed is not None, "and taking it back clears completed_by, so it needs its own entry"
