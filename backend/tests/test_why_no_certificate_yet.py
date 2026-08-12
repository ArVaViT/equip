"""A refused certificate has to say what would change the answer (D9).

The gate ships at the end of this phase and will refuse far more often than
today's progress check. A refusal a student cannot act on becomes a message to
the teacher, and a teacher who gets that message five times a week starts
approving certificates to make it stop — which is the gate defeating itself.
So the explanation ships first, and every test here is one sentence a student
should be able to read off their own screen.

Three obstacles read identically as "not done" and are three different
conversations: nobody has marked it (the teacher's move), it came back for
revision (the student's move), it was never handed in (the student's move, and
a different one). They are counted separately on purpose.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.models.student_grade import StudentGrade
from app.services.certificate_readiness import (
    BELOW_THRESHOLD,
    COURSE_NOT_COMPLETE,
    NOT_ASSESSED,
    QUIZZES_NOT_PASSED,
    WORK_NOT_GRADED,
    WORK_NOT_SUBMITTED,
    WORK_RETURNED,
    certificate_blockers,
)
from app.services.grade_exemption_service import apply_exemption

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

URL = "/api/v1/grades/my/{}/breakdown"


def _course(db: Session, course_id: str, *, scheme: str = "letter", progress: int = 100, threshold: int = 70):
    course = Course(
        id=course_id,
        status="published",
        created_by=TEACHER_ID,
        grading_scheme=scheme,
        pass_threshold=threshold,
    )
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=progress))
    db.flush()
    return course, module


def _assignment(db: Session, module, course_id: str, index: int = 0, *, max_score: int = 100):
    chapter = Chapter(
        id=f"{course_id}-a{index}",
        module_id=module.id,
        order_index=index,
        chapter_type="assignment",
        title=f"Эссе {index}",
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=max_score)
    db.add(assignment)
    db.flush()
    return assignment, chapter


def _submit(db: Session, assignment, *, status: str, grade: int | None) -> None:
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status=status,
            grade=grade,
        )
    )


def _quiz(db: Session, module, course_id: str, index: int = 0, *, passing_score: int = 70):
    chapter = Chapter(
        id=f"{course_id}-q{index}",
        module_id=module.id,
        order_index=100 + index,
        chapter_type="quiz",
        title=f"Тест {index}",
    )
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=passing_score)
    db.add(quiz)
    db.flush()
    return quiz, chapter


def _attempt(db: Session, quiz, *, score: int, passed: bool, unread_essay: bool = False) -> None:
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=score,
        max_score=100,
        passed=passed,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    if unread_essay:
        question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=10, order_index=0)
        db.add(question)
        db.flush()
        db.add(
            QuizAnswer(
                id=uuid.uuid4(),
                attempt_id=attempt.id,
                question_id=question.id,
                text_answer="Ответ",
                points_earned=0,
                graded_at=None,
            )
        )


def _blockers(db: Session, course):
    enrollment = db.query(Enrollment).filter(Enrollment.course_id == course.id).one()
    return certificate_blockers(db, course, enrollment, STUDENT_ID)


def _codes(blockers) -> list[str]:
    return [b.code for b in blockers]


# ---------------------------------------------------------------------------
# Whose move is it
# ---------------------------------------------------------------------------


def test_unmarked_work_is_named_as_unmarked_not_as_a_bad_grade(db: Session, teacher, student) -> None:
    """The student handed it in. Everything after that is the teacher's move,
    and a refusal that does not say so reads as the student's failure."""
    course, module = _course(db, "cert-unmarked")
    assignment, chapter = _assignment(db, module, "cert-unmarked")
    _submit(db, assignment, status="submitted", grade=None)
    db.commit()

    blockers = _blockers(db, course)

    assert WORK_NOT_GRADED in _codes(blockers)
    unmarked = next(b for b in blockers if b.code == WORK_NOT_GRADED)
    assert unmarked.params["count"] == 1
    # Naming the problem without saying where it is sends the student to the
    # teacher instead of to the work.
    assert unmarked.chapter_ids == [chapter.id]


def test_work_sent_back_is_a_different_sentence_from_work_never_sent(db: Session, teacher, student) -> None:
    course, module = _course(db, "cert-returned")
    returned_assignment, returned_chapter = _assignment(db, module, "cert-returned", 0)
    _assignment(db, module, "cert-returned", 1)
    _submit(db, returned_assignment, status="returned", grade=40)
    db.commit()

    blockers = _blockers(db, course)
    codes = _codes(blockers)

    assert WORK_RETURNED in codes
    assert WORK_NOT_SUBMITTED in codes
    assert next(b for b in blockers if b.code == WORK_RETURNED).chapter_ids == [returned_chapter.id]
    assert next(b for b in blockers if b.code == WORK_NOT_SUBMITTED).params["count"] == 1


def test_an_unread_essay_inside_a_quiz_counts_as_unmarked(db: Session, teacher, student) -> None:
    """A quiz can be scored and still be unmarked: the multiple-choice half is
    automatic and the essay half is not. Telling a student the test is done
    while a teacher still has to read it is the same lie in the other
    direction."""
    course, module = _course(db, "cert-quiz-essay")
    quiz, chapter = _quiz(db, module, "cert-quiz-essay")
    _attempt(db, quiz, score=90, passed=True, unread_essay=True)
    db.commit()

    blockers = _blockers(db, course)

    assert WORK_NOT_GRADED in _codes(blockers)
    assert next(b for b in blockers if b.code == WORK_NOT_GRADED).chapter_ids == [chapter.id]


def test_a_quiz_never_sat_is_named_rather_than_absorbed_into_the_percentage(db: Session, teacher, student) -> None:
    course, module = _course(db, "cert-quiz-missing")
    _quiz(db, module, "cert-quiz-missing")
    db.commit()

    assert WORK_NOT_SUBMITTED in _codes(_blockers(db, course))


# ---------------------------------------------------------------------------
# The number
# ---------------------------------------------------------------------------


def test_a_failing_score_is_stated_with_the_line_it_missed(db: Session, teacher, student) -> None:
    course, module = _course(db, "cert-low", threshold=70)
    assignment, _chapter = _assignment(db, module, "cert-low")
    _submit(db, assignment, status="graded", grade=64)
    db.commit()

    blockers = _blockers(db, course)
    low = next(b for b in blockers if b.code == BELOW_THRESHOLD)

    assert low.params["final_score"] == 64.0
    assert low.params["pass_threshold"] == 70.0
    assert low.params["provisional"] is False
    # Last in the list: it is the summary of the others, not a separate problem.
    assert _codes(blockers)[-1] == BELOW_THRESHOLD


def test_the_score_says_it_is_provisional_while_work_is_unread(db: Session, teacher, student) -> None:
    """Итоговая counts unmarked work as zero, so while anything is unread the
    figure is a floor that can only rise. Stated flatly next to an unread essay
    it tells the student their standing is worse than anybody yet knows."""
    course, module = _course(db, "cert-provisional")
    graded_assignment, _c1 = _assignment(db, module, "cert-provisional", 0)
    unread_assignment, _c2 = _assignment(db, module, "cert-provisional", 1)
    _submit(db, graded_assignment, status="graded", grade=100)
    _submit(db, unread_assignment, status="submitted", grade=None)
    db.commit()

    blockers = _blockers(db, course)
    low = next(b for b in blockers if b.code == BELOW_THRESHOLD)

    assert low.params["provisional"] is True


def test_a_passing_student_is_told_nothing_because_nothing_is_wrong(db: Session, teacher, student) -> None:
    course, module = _course(db, "cert-passing")
    assignment, _chapter = _assignment(db, module, "cert-passing")
    _submit(db, assignment, status="graded", grade=88)
    db.commit()

    assert _blockers(db, course) == []


def test_an_unfinished_course_leads_with_that(db: Session, teacher, student) -> None:
    course, module = _course(db, "cert-progress", progress=40)
    assignment, _chapter = _assignment(db, module, "cert-progress")
    _submit(db, assignment, status="graded", grade=95)
    db.commit()

    blockers = _blockers(db, course)

    assert _codes(blockers)[0] == COURSE_NOT_COMPLETE
    assert blockers[0].params["progress"] == 40


# ---------------------------------------------------------------------------
# Exemptions and overrides — decisions somebody already made
# ---------------------------------------------------------------------------


def test_an_excused_item_is_not_owed(db: Session, teacher, student) -> None:
    """Excusing work is a teacher's decision (D6). Listing it as an obstacle
    would send the student back to ask for something they already have."""
    course, module = _course(db, "cert-excused")
    graded_assignment, _c1 = _assignment(db, module, "cert-excused", 0)
    excused_assignment, _c2 = _assignment(db, module, "cert-excused", 1)
    _submit(db, graded_assignment, status="graded", grade=90)
    db.commit()
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=excused_assignment.id,
        teacher_id=TEACHER_ID,
    )
    # Progress is computed from chapter completion, which this fixture does not
    # simulate; the subject here is which items are owed, not the progress bar.
    db.query(Enrollment).filter(Enrollment.course_id == course.id).update({"progress": 100})
    db.commit()

    assert _blockers(db, course) == []


def test_a_hand_set_passing_grade_ends_the_conversation(db: Session, teacher, student) -> None:
    """The teacher decided, with the whole picture in front of them (D7).
    Listing unmarked work under that decision invites somebody to undo it."""
    course, module = _course(db, "cert-override")
    assignment, _chapter = _assignment(db, module, "cert-override")
    _submit(db, assignment, status="submitted", grade=None)
    db.add(
        StudentGrade(
            id=uuid.uuid4(),
            student_id=STUDENT_ID,
            course_id=course.id,
            override_score=Decimal("95.00"),
            graded_by=TEACHER_ID,
        )
    )
    db.commit()

    assert _blockers(db, course) == []


def test_a_student_excused_from_everything_needs_a_person_not_a_number(db: Session, teacher, student) -> None:
    """Progress reaches 100 because excusing an item also completes its chapter,
    so nothing was assessed and there is no grade to certify. The answer is a
    teacher setting one, and the refusal has to say that rather than quote a
    percentage."""
    course, module = _course(db, "cert-all-excused")
    only_assignment, _chapter = _assignment(db, module, "cert-all-excused")
    db.commit()
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=only_assignment.id,
        teacher_id=TEACHER_ID,
    )
    db.commit()

    assert _codes(_blockers(db, course)) == [NOT_ASSESSED]


def test_waiting_to_be_marked_is_not_the_same_as_nobody_will_ever_mark_it(db: Session, teacher, student) -> None:
    """Both arrive as «не аттестован» from the calculator and need opposite
    sentences. Nothing marked *yet* is already explained item by item and the
    answer is to wait; nothing left to mark at all needs a teacher to decide.
    Printing "your teacher must set a grade" under an essay sitting in that
    teacher's queue sends the student to ask for what would arrive on its own."""
    course, module = _course(db, "cert-not-yet")
    assignment, _chapter = _assignment(db, module, "cert-not-yet")
    _submit(db, assignment, status="submitted", grade=None)
    db.commit()

    codes = _codes(_blockers(db, course))

    assert codes == [WORK_NOT_GRADED]


# ---------------------------------------------------------------------------
# pass/fail courses (D2) — no percentage participates
# ---------------------------------------------------------------------------


def test_a_pass_fail_course_never_quotes_a_percentage(db: Session, teacher, student) -> None:
    course, module = _course(db, "cert-zachet", scheme="pass_fail")
    assignment, _chapter = _assignment(db, module, "cert-zachet")
    _submit(db, assignment, status="submitted", grade=None)
    db.commit()

    codes = _codes(_blockers(db, course))

    assert WORK_NOT_GRADED in codes
    # The rule is not arithmetic (D2), so a number has no standing here — and a
    # student told «незачёт, 64%» would reasonably argue about the 64.
    assert BELOW_THRESHOLD not in codes


def test_a_failed_quiz_is_a_retake_not_a_missing_hand_in(db: Session, teacher, student) -> None:
    course, module = _course(db, "cert-quiz-failed", scheme="pass_fail")
    quiz, chapter = _quiz(db, module, "cert-quiz-failed", passing_score=70)
    _attempt(db, quiz, score=45, passed=False)
    db.commit()

    blockers = _blockers(db, course)
    codes = _codes(blockers)

    assert QUIZZES_NOT_PASSED in codes
    # They sat it. Telling them to hand it in is an instruction they cannot follow.
    assert WORK_NOT_SUBMITTED not in codes
    assert next(b for b in blockers if b.code == QUIZZES_NOT_PASSED).chapter_ids == [chapter.id]


def test_one_essay_is_one_problem_not_two(db: Session, teacher, student) -> None:
    """The зачёт rule counts an unmarked essay as still owed, and so does the
    unmarked list. Both were true of the same essay, and the refusal used to
    print it twice under two headings."""
    course, module = _course(db, "cert-no-double", scheme="pass_fail")
    assignment, _chapter = _assignment(db, module, "cert-no-double")
    _submit(db, assignment, status="submitted", grade=None)
    db.commit()

    codes = _codes(_blockers(db, course))

    assert codes.count(WORK_NOT_GRADED) == 1
    assert WORK_NOT_SUBMITTED not in codes


def test_a_quiz_nobody_has_marked_is_not_also_a_failed_quiz(db: Session, teacher, student) -> None:
    """The зачёт rule sees a quiz that has not cleared its line; the unmarked
    list sees the essay inside it that nobody has read. Both describe the same
    test, and printing «1 тест не сдан» under «1 работа не проверена» tells the
    student to resit something the teacher has not finished reading."""
    course, module = _course(db, "cert-quiz-unread", scheme="pass_fail")
    quiz, _chapter = _quiz(db, module, "cert-quiz-unread")
    _attempt(db, quiz, score=40, passed=False, unread_essay=True)
    db.commit()

    codes = _codes(_blockers(db, course))

    assert WORK_NOT_GRADED in codes
    assert QUIZZES_NOT_PASSED not in codes


def test_a_quiz_never_sat_is_not_also_a_failed_quiz(db: Session, teacher, student) -> None:
    """ "Not handed in" and "not passed" collapse into one word in Russian and
    carry opposite instructions: sit it, versus sit it again."""
    course, module = _course(db, "cert-quiz-untouched", scheme="pass_fail")
    _quiz(db, module, "cert-quiz-untouched")
    db.commit()

    codes = _codes(_blockers(db, course))

    assert WORK_NOT_SUBMITTED in codes
    assert QUIZZES_NOT_PASSED not in codes


def test_an_auto_marked_answer_is_not_something_a_student_is_waiting_on(db: Session, teacher, student) -> None:
    """A multiple-choice answer is marked at submit and never appears on the
    teacher's queue. Told "your work is not marked yet" for an answer no teacher
    will ever open, a student waits for something that will not arrive — and the
    two screens disagree with neither number obviously wrong."""
    course, module = _course(db, "cert-auto-marked")
    quiz, _chapter = _quiz(db, module, "cert-auto-marked")
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=100,
        max_score=100,
        passed=True,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="multiple_choice", points=10, order_index=0)
    db.add(question)
    db.flush()
    # `graded_at` left NULL on purpose: the shape a pre-backfill row has.
    db.add(
        QuizAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            question_id=question.id,
            text_answer=None,
            points_earned=10,
        )
    )
    db.commit()

    assert WORK_NOT_GRADED not in _codes(_blockers(db, course))


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def test_the_student_reads_this_on_their_own_grade_page(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, "cert-wire")
    assignment, chapter = _assignment(db, module, "cert-wire")
    _submit(db, assignment, status="submitted", grade=None)
    db.commit()

    body = student_client.get(URL.format(course.id)).json()

    blocker = next(b for b in body["certificate_blockers"] if b["code"] == WORK_NOT_GRADED)
    assert blocker["chapter_ids"] == [chapter.id]
    # A code and numbers, never a sentence: the words live in the frontend
    # catalogues, so a new language is a translation change, not a release.
    assert set(blocker) == {"code", "params", "chapter_ids"}
    assert all(not isinstance(v, str) for v in blocker["params"].values())
