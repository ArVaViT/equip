"""«Зачёт» means every required piece of work accepted (D2).

Not "average above a line". The draft this replaces defined pass as a weighted
average clearing a threshold while the interface de-emphasised percentages —
so a student could complete every chapter, pass every quiz, have every essay
accepted, and still be handed незачёт by a number the product had decided not
to show them.

A minister taking a course by correspondence has to be able to predict the
outcome without arithmetic: did the work, passed the tests, work accepted.
Every test here is a sentence in that form.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.services.grade_exemption_service import apply_exemption
from app.services.zachet import NEZACHET, NOT_ATTESTED, ZACHET, unaccepted_assignments, zachet_result

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID


def _course(db: Session, teacher, course_id: str, *, assignments: int = 1):
    course = Course(id=course_id, status="published", created_by=teacher.id, grading_scheme="pass_fail")
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    made = []
    for i in range(assignments):
        chapter = Chapter(
            id=f"{course_id}-a{i}",
            module_id=module.id,
            order_index=i,
            chapter_type="assignment",
            title=f"Работа {i}",
        )
        db.add(chapter)
        db.flush()
        assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
        db.add(assignment)
        made.append(assignment)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=100))
    db.commit()
    return course, made


def _submit(db: Session, assignment, *, status: str, grade: int | None, minutes_ago: int = 0):
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status=status,
            grade=grade,
            submitted_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )
    )
    db.commit()


def _result(db: Session, course, *, progress: int = 100, all_excused: bool = False):
    return zachet_result(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        progress=progress,
        all_items_excused=all_excused,
    )


def test_did_the_work_and_it_was_accepted(db: Session, teacher, student) -> None:
    course, (essay,) = _course(db, teacher, "c-z-pass")
    _submit(db, essay, status="graded", grade=80)

    assert _result(db, course) == (ZACHET, [])


def test_an_unfinished_course_is_not_zachet(db: Session, teacher, student) -> None:
    """Progress comes from the enrolment rather than being recomputed — зачёт
    disagreeing with the progress bar on the same screen is exactly the
    confusion this rule removes."""
    course, (essay,) = _course(db, teacher, "c-z-unfinished")
    _submit(db, essay, status="graded", grade=80)

    result, outstanding = _result(db, course, progress=60)

    assert result == NEZACHET
    assert outstanding == [], "the work is in; it is the course that is not finished"


def test_work_returned_for_revision_blocks_it(db: Session, teacher, student) -> None:
    """«Вернуть на доработку» is the teacher's "not yet", and it is the whole
    difference between this rule and counting marks: the essay has a grade on
    it and the course still is not зачтён."""
    course, (essay,) = _course(db, teacher, "c-z-returned")
    _submit(db, essay, status="returned", grade=45)

    result, outstanding = _result(db, course)

    assert result == NEZACHET
    assert outstanding == [str(essay.id)]


def test_grading_without_returning_is_acceptance(db: Session, teacher, student) -> None:
    """Even a low mark. The scheme is not about the number — a teacher who
    wanted more work back has a verb for that, and did not use it."""
    course, (essay,) = _course(db, teacher, "c-z-low-but-accepted")
    _submit(db, essay, status="graded", grade=1)

    assert _result(db, course) == (ZACHET, [])


def test_submitted_but_unmarked_is_still_owed(db: Session, teacher, student) -> None:
    """Nobody has read it yet, so nobody has accepted it."""
    course, (essay,) = _course(db, teacher, "c-z-pending")
    _submit(db, essay, status="submitted", grade=None)

    result, outstanding = _result(db, course)

    assert result == NEZACHET
    assert outstanding == [str(essay.id)]


def test_never_submitted_is_owed(db: Session, teacher, student) -> None:
    course, (essay,) = _course(db, teacher, "c-z-never")

    assert _result(db, course) == (NEZACHET, [str(essay.id)])


def test_a_later_return_overrides_an_earlier_acceptance(db: Session, teacher, student) -> None:
    """The latest submission decides. An earlier accepted draft does not
    survive the teacher returning a later one — «вернуть на доработку» is a
    decision about where the work stands now."""
    course, (essay,) = _course(db, teacher, "c-z-latest-wins")
    _submit(db, essay, status="graded", grade=90, minutes_ago=60)
    _submit(db, essay, status="returned", grade=40, minutes_ago=0)

    result, outstanding = _result(db, course)

    assert result == NEZACHET
    assert outstanding == [str(essay.id)]


def test_a_resubmission_after_a_return_clears_it(db: Session, teacher, student) -> None:
    course, (essay,) = _course(db, teacher, "c-z-fixed")
    _submit(db, essay, status="returned", grade=40, minutes_ago=60)
    _submit(db, essay, status="graded", grade=75, minutes_ago=0)

    assert _result(db, course) == (ZACHET, [])


def test_excused_work_is_not_owed(db: Session, teacher, student) -> None:
    """A student excused from an essay does not owe it (D6), so it cannot hold
    the зачёт — which is the whole reason exemptions exist."""
    course, (first, second) = _course(db, teacher, "c-z-excused", assignments=2)
    _submit(db, first, status="graded", grade=70)
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=second.id,
        teacher_id=teacher.id,
    )
    db.commit()

    assert _result(db, course) == (ZACHET, [])


def test_a_student_excused_from_everything_is_not_attested(db: Session, teacher, student) -> None:
    """Neither зачёт nor незачёт. Nobody assessed this person, and зачёт is an
    assessment — a human has to decide."""
    course, _essay = _course(db, teacher, "c-z-all-excused")

    assert _result(db, course, all_excused=True) == (NOT_ATTESTED, [])


def test_a_course_with_no_assignments_rests_on_completion_alone(db: Session, teacher, student) -> None:
    """Quiz chapters already require passing each quiz at its own passing_score
    (D2.1), so progress 100 carries "passed the tests" by itself."""
    course, _none = _course(db, teacher, "c-z-quizzes-only", assignments=0)

    assert _result(db, course) == (ZACHET, [])
    assert _result(db, course, progress=99)[0] == NEZACHET


def test_the_outstanding_list_names_every_kind_of_owed_work(db: Session, teacher, student) -> None:
    """A student asking "what is left" does not care which of the three shapes
    it is, so they arrive as one list."""
    course, (never, pending, returned) = _course(db, teacher, "c-z-three-shapes", assignments=3)
    _submit(db, pending, status="submitted", grade=None)
    _submit(db, returned, status="returned", grade=30)

    outstanding = unaccepted_assignments(db, student_id=STUDENT_ID, course_id=course.id)

    assert set(outstanding) == {str(never.id), str(pending.id), str(returned.id)}


def test_a_deleted_chapters_assignment_is_not_owed(db: Session, teacher, student) -> None:
    """Work in a removed chapter is not work anybody owes."""
    course, _essay = _course(db, teacher, "c-z-deleted")
    chapter = db.query(Chapter).filter(Chapter.id == "c-z-deleted-a0").first()
    chapter.deleted_at = datetime.now(UTC)
    db.commit()

    assert _result(db, course) == (ZACHET, [])


# --------------------------------------------------------------------------
# Found by an adversarial pass before any of this merged. Every one of them
# was reachable, and the suite above caught none.
# --------------------------------------------------------------------------


def test_failing_every_quiz_is_not_zachet_even_at_progress_100(db: Session, teacher, student) -> None:
    """The design assumes progress carries "passed the tests". It does not:
    `PUT /progress/chapter/…/complete` marks a chapter done without looking at
    the quiz inside it, so a teacher's tick could hand зачёт to a student who
    failed every test — by arithmetic nobody performed."""
    from app.models.chapter_progress import ChapterProgress
    from app.models.quiz import Quiz, QuizAttempt

    course = Course(id="c-z-failed-quiz", status="published", created_by=teacher.id, grading_scheme="pass_fail")
    db.add(course)
    module = Module(id="c-z-failed-quiz-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-z-failed-quiz-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Тест")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=70)
    db.add(quiz)
    db.flush()
    db.add(
        QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=STUDENT_ID,
            score=5,
            max_score=100,
            passed=False,
            completed_at=datetime.now(UTC),
        )
    )
    # The teacher ticks the chapter complete anyway.
    db.add(
        ChapterProgress(
            user_id=STUDENT_ID,
            chapter_id=chapter.id,
            completed=True,
            completion_type="teacher",
            completed_at=datetime.now(UTC),
        )
    )
    db.add(Enrollment(id="enr-c-z-failed-quiz", user_id=STUDENT_ID, course_id=course.id, progress=100))
    db.commit()

    result, _outstanding = _result(db, course)

    assert result == NEZACHET, (
        "a teacher who wants to pass this student still can — by setting the grade "
        "themselves, which is recorded and attributable"
    )


def test_a_passed_quiz_satisfies_the_rule(db: Session, teacher, student) -> None:
    from app.models.quiz import Quiz, QuizAttempt

    course = Course(id="c-z-passed-quiz", status="published", created_by=teacher.id, grading_scheme="pass_fail")
    db.add(course)
    module = Module(id="c-z-passed-quiz-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-z-passed-quiz-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Тест")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=70)
    db.add(quiz)
    db.flush()
    db.add(
        QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=STUDENT_ID,
            score=85,
            max_score=100,
            passed=True,
            completed_at=datetime.now(UTC),
        )
    )
    db.add(Enrollment(id="enr-c-z-passed-quiz", user_id=STUDENT_ID, course_id=course.id, progress=100))
    db.commit()

    assert _result(db, course) == (ZACHET, [])


def test_an_excused_quiz_is_not_owed_either(db: Session, teacher, student) -> None:
    from app.models.quiz import Quiz

    course = Course(id="c-z-excused-quiz", status="published", created_by=teacher.id, grading_scheme="pass_fail")
    db.add(course)
    module = Module(id="c-z-excused-quiz-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-z-excused-quiz-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Тест")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=70)
    db.add(quiz)
    db.add(Enrollment(id="enr-c-z-excused-quiz", user_id=STUDENT_ID, course_id=course.id, progress=100))
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

    assert _result(db, course) == (ZACHET, [])


def test_a_tie_on_submitted_at_still_honours_the_return(db: Session, teacher, student) -> None:
    """`submitted_at` defaults to NOW(), which on Postgres is the transaction
    timestamp — identical for rows written together. Untied, a graded row and a
    returned row both came back and whichever the reader folded in decided the
    verdict, so a returned essay could quietly count as accepted."""
    course, (essay,) = _course(db, teacher, "c-z-tie")
    same_moment = datetime.now(UTC)
    for status, grade in (("graded", 90), ("returned", 40)):
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=essay.id,
                student_id=STUDENT_ID,
                status=status,
                grade=grade,
                submitted_at=same_moment,
                graded_at=same_moment if status == "graded" else same_moment + timedelta(minutes=1),
            )
        )
    db.commit()

    result, outstanding = _result(db, course)

    assert result == NEZACHET
    assert outstanding == [str(essay.id)]
