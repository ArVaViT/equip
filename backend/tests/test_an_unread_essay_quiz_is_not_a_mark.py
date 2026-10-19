"""An essay quiz nobody has read is not a mark — on the quiz side too.

The assignment door was closed on 2026-10-02: a student whose essay sat
unmarked no longer read «0,0% F» the moment a classmate's was marked. The
quiz door was not. A quiz with an open question is *completed* the instant
the student submits it, with ``score`` holding only the auto-graded part and
``max_score`` the full total (``attempts.py``: "so that students can't be
auto-passed on half-graded work"). Until a teacher reads the open answers,
that attempt is a running total, not a result — the per-item list already
says ``pending_review`` and hides the number for exactly that reason.

The calculator counted it anyway: ``student_has_quiz_marks`` went true and
«текущая» — the average "over the work that has been marked" (D10) — took the
unread essay as a 0. So the student read «0,0% F» for work nobody had looked
at, and the teacher's board put a 0 in their quiz column.

«Итоговая» is untouched by these tests on purpose: it counts what is not yet
marked as a floor that can only rise, and a running total is exactly that.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.models.user import User, UserRole
from app.services.grade_calculator import calculate_all_student_grades, calculate_student_grade_for_course
from app.services.my_grade_service import build_my_course_grade
from app.services.student_progress_service import build_course_student_progress

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID

CLASSMATE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _course(db: Session, teacher, course_id: str, *, quizzes: int) -> tuple[Course, list[Quiz], Enrollment]:
    course = Course(
        id=course_id,
        status="published",
        created_by=teacher.id,
        quiz_weight=100,
        assignment_weight=0,
        grading_scheme="letter",
        pass_threshold=Decimal("70.00"),
    )
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    made = []
    for i in range(quizzes):
        chapter = Chapter(
            id=f"{course_id}-q{i}", module_id=module.id, order_index=i, chapter_type="quiz", title=f"Q{i}"
        )
        db.add(chapter)
        db.flush()
        quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
        db.add(quiz)
        db.flush()
        made.append(quiz)
    enrollment = Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=50)
    db.add(enrollment)
    db.add(User(id=CLASSMATE_ID, email="classmate@example.com", full_name="Classmate", role=UserRole.STUDENT.value))
    db.flush()
    db.add(Enrollment(id=f"enr-{course_id}-2", user_id=CLASSMATE_ID, course_id=course_id, progress=50))
    db.commit()
    return course, made, enrollment


def _essay_attempt(db: Session, quiz: Quiz, user_id: uuid.UUID, *, read: bool, points: int = 0) -> QuizAttempt:
    """A finished attempt on a one-essay quiz worth 10, read or still waiting."""
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=10, order_index=0)
    db.add(question)
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=user_id,
        score=points,
        max_score=10,
        passed=points >= 7,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    db.add(
        QuizAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            question_id=question.id,
            text_answer="Мой ответ",
            points_earned=points,
            graded_at=datetime.now(UTC) if read else None,
        )
    )
    db.commit()
    return attempt


def test_a_classmates_marked_quiz_does_not_hand_me_an_f(db: Session, teacher, student) -> None:
    """The 2026-10-02 defect, through the quiz door: my essay quiz is waiting,
    theirs was read. The course is «graded»; nothing of mine is."""
    course, (quiz,), enrollment = _course(db, teacher, "c-quiz-door", quizzes=1)
    _essay_attempt(db, quiz, CLASSMATE_ID, read=True, points=9)
    _essay_attempt(db, quiz, STUDENT_ID, read=False)

    mine = calculate_student_grade_for_course(db, course, STUDENT_ID)
    assert mine.result_state == "graded", "the category is live: a classmate was marked"
    assert mine.student_has_quiz_marks is False, "nothing of mine has been read"

    body = build_my_course_grade(db, course, enrollment, STUDENT_ID)
    assert body["result_state"] == "not_graded_yet"
    assert body["current_score"] is None
    assert body["final_score"] is None
    assert body["final_symbol"] is None
    codes = [b["code"] for b in body["certificate_blockers"]]
    assert "work_not_graded" in codes
    assert "below_threshold" not in codes


def test_the_teachers_board_shows_no_quiz_average_for_an_unread_essay(db: Session, teacher, student) -> None:
    course, (quiz,), _ = _course(db, teacher, "c-quiz-door-board", quizzes=1)
    _essay_attempt(db, quiz, CLASSMATE_ID, read=True, points=9)
    _essay_attempt(db, quiz, STUDENT_ID, read=False)

    rows = {s["id"]: s for s in build_course_student_progress(db, course, course.id)["students"]}

    assert rows[str(CLASSMATE_ID)]["quiz_avg"] == 90
    assert rows[str(STUDENT_ID)]["quiz_avg"] is None, "nobody has read it — that is not a zero"


def test_the_current_score_averages_only_the_quizzes_that_were_read(db: Session, teacher, student) -> None:
    """Two quizzes: one read at 8/10, one submitted and waiting. «Текущая» is
    80, not 40 — the unread one is not yet a mark. «Итоговая» still counts it
    as a floor: (80 + 0) / 2 = 40."""
    course, (read_quiz, waiting_quiz), _ = _course(db, teacher, "c-quiz-door-current", quizzes=2)
    _essay_attempt(db, read_quiz, STUDENT_ID, read=True, points=8)
    _essay_attempt(db, waiting_quiz, STUDENT_ID, read=False)

    single = calculate_student_grade_for_course(db, course, STUDENT_ID)
    (batch,) = [r["breakdown"] for r in calculate_all_student_grades(db, course) if r["student_id"] == str(STUDENT_ID)]

    assert single.current_score == batch.current_score == 80.0
    assert single.final_score == batch.final_score == 40.0
    assert single.scores_differ is batch.scores_differ is True


def test_reading_the_essay_turns_it_into_a_mark(db: Session, teacher, student) -> None:
    course, (quiz,), enrollment = _course(db, teacher, "c-quiz-door-read", quizzes=1)
    _essay_attempt(db, quiz, CLASSMATE_ID, read=True, points=9)
    attempt = _essay_attempt(db, quiz, STUDENT_ID, read=False)

    db.query(QuizAnswer).filter(QuizAnswer.attempt_id == attempt.id).update(
        {"points_earned": 7, "graded_at": datetime.now(UTC)}
    )
    attempt.score = 7
    db.commit()

    body = build_my_course_grade(db, course, enrollment, STUDENT_ID)
    assert body["result_state"] == "graded"
    assert body["current_score"] == 70.0
    assert body["final_score"] == 70.0


def test_an_older_read_attempt_still_counts_while_a_retake_waits(db: Session, teacher, student) -> None:
    """A read attempt at 6/10, then a retake whose essay is waiting. The read
    one is a mark and stands; the waiting one is not a mark yet. The retake
    cannot *lower* «текущая» by being unread."""
    course, (quiz,), _ = _course(db, teacher, "c-quiz-door-retake", quizzes=1)
    _essay_attempt(db, quiz, STUDENT_ID, read=True, points=6)
    _essay_attempt(db, quiz, STUDENT_ID, read=False)

    single = calculate_student_grade_for_course(db, course, STUDENT_ID)
    (batch,) = [r["breakdown"] for r in calculate_all_student_grades(db, course) if r["student_id"] == str(STUDENT_ID)]

    assert single.student_has_quiz_marks is batch.student_has_quiz_marks is True
    assert single.current_score == batch.current_score == 60.0
    assert single.final_score == batch.final_score == 60.0


def _mixed_attempt(
    db: Session, quiz: Quiz, choice: QuizQuestion, essay: QuizQuestion, *, choice_points: int, essay_points: int | None
) -> None:
    """A finished attempt on a choice-plus-essay quiz worth 10. ``essay_points``
    None leaves the essay unread: the attempt's ``score`` is then the choice
    part alone — the running total ``attempts.py`` stores at submit."""
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=choice_points + (essay_points or 0),
        max_score=10,
        passed=False,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    now = datetime.now(UTC)
    db.add(
        QuizAnswer(
            id=uuid.uuid4(), attempt_id=attempt.id, question_id=choice.id, points_earned=choice_points, graded_at=now
        )
    )
    db.add(
        QuizAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            question_id=essay.id,
            text_answer="Мой ответ",
            points_earned=essay_points or 0,
            graded_at=None if essay_points is None else now,
        )
    )
    db.commit()


def test_a_retake_whose_running_total_beats_the_read_mark_raises_only_the_final(db: Session, teacher, student) -> None:
    """Choice 5 + essay 5. The read attempt is 3/10; the retake has the choice
    part right (5/10 so far) and its essay waiting. The running total is the
    higher number, and it belongs to «итоговая» alone: «текущая» stays on the
    mark a teacher gave. Pins that ``best`` and ``best_read`` are two different
    columns — a path reading the wrong one agrees with the other tests here,
    where the unread attempt never outscores the read one."""
    course, (quiz,), _ = _course(db, teacher, "c-quiz-door-running-total", quizzes=1)
    choice = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="multiple_choice", points=5, order_index=0)
    essay = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=5, order_index=1)
    db.add_all([choice, essay])
    db.commit()
    _mixed_attempt(db, quiz, choice, essay, choice_points=0, essay_points=3)
    _mixed_attempt(db, quiz, choice, essay, choice_points=5, essay_points=None)

    single = calculate_student_grade_for_course(db, course, STUDENT_ID)
    (batch,) = [r["breakdown"] for r in calculate_all_student_grades(db, course) if r["student_id"] == str(STUDENT_ID)]

    assert single == batch
    assert single.student_has_quiz_marks is True
    assert single.current_score == 30.0, "the retake is not a mark until its essay is read"
    assert single.final_score == 50.0, "the floor can only rise, and the running total is the floor"
    assert single.scores_differ is True
