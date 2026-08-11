"""What is waiting for a teacher to mark it.

An essay is submitted and then nothing happens until somebody opens the right
course, the right chapter and the right attempt. There was no place that said
"seven pieces of work are waiting on you" — for a school taking its first
cohort, that is where student work sits unread for a fortnight.

The line that matters in every test below: the queue counts work waiting on the
**teacher**, never work waiting on the student. A number a teacher cannot act
on is a number they stop reading.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

URL = "/api/v1/grades/pending"


def _course(db: Session, owner_id, course_id: str):
    course = Course(id=course_id, status="published", created_by=owner_id)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    return course, module


def _essay_awaiting(db: Session, module, course_id: str, *, graded: bool) -> None:
    chapter = Chapter(id=f"{course_id}-q", module_id=module.id, order_index=0, chapter_type="quiz", title="Эссе")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.flush()
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=10, order_index=0)
    db.add(question)
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=0,
        max_score=10,
        passed=False,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    db.add(
        QuizAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            question_id=question.id,
            text_answer="Ответ",
            points_earned=0,
            graded_at=datetime.now(UTC) if graded else None,
        )
    )


def _assignment_submission(db: Session, module, course_id: str, *, status: str, grade: int | None):
    chapter = Chapter(
        id=f"{course_id}-a",
        module_id=module.id,
        order_index=1,
        chapter_type="assignment",
        title="Работа",
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status=status,
            grade=grade,
        )
    )


def test_an_unread_essay_is_waiting(client, db: Session, teacher, student) -> None:
    course, module = _course(db, TEACHER_ID, "c-q-essay")
    _essay_awaiting(db, module, course.id, graded=False)
    db.commit()

    body = client.get(URL).json()

    assert body["total"] == 1
    assert body["by_course"][course.id] == 1


def test_a_marked_essay_is_not(client, db: Session, teacher, student) -> None:
    course, module = _course(db, TEACHER_ID, "c-q-marked")
    _essay_awaiting(db, module, course.id, graded=True)
    db.commit()

    assert client.get(URL).json()["total"] == 0


def test_a_submitted_assignment_is_waiting(client, db: Session, teacher, student) -> None:
    course, module = _course(db, TEACHER_ID, "c-q-submitted")
    _assignment_submission(db, module, course.id, status="submitted", grade=None)
    db.commit()

    assert client.get(URL).json()["by_course"][course.id] == 1


def test_work_handed_back_is_the_students_move_not_the_teachers(client, db: Session, teacher, student) -> None:
    """«Вернуть на доработку» means the teacher has read it and decided. Leaving
    it in their queue would make the number unactionable — which is how a queue
    stops being read."""
    course, module = _course(db, TEACHER_ID, "c-q-returned")
    _assignment_submission(db, module, course.id, status="returned", grade=40)
    db.commit()

    assert client.get(URL).json()["total"] == 0


def test_the_status_filter_carries_its_own_weight(client, db: Session, teacher, student) -> None:
    """A returned submission normally carries a grade, so the "no mark" filter
    hides it anyway — which means the status filter is never exercised and a
    test that only uses the ordinary case passes with it deleted. This is the
    ungraded-return shape: not reachable through the API today, reachable the
    moment somebody adds a route that returns work without marking it."""
    course, module = _course(db, TEACHER_ID, "c-q-returned-unmarked")
    _assignment_submission(db, module, course.id, status="returned", grade=None)
    db.commit()

    assert client.get(URL).json()["total"] == 0


def test_work_never_handed_in_is_not_in_the_queue(client, db: Session, teacher, student) -> None:
    """There is nothing to open."""
    _course_row, module = _course(db, TEACHER_ID, "c-q-never")
    chapter = Chapter(id="c-q-never-a", module_id=module.id, order_index=0, chapter_type="assignment", title="Work")
    db.add(chapter)
    db.flush()
    db.add(Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100))
    db.commit()

    assert client.get(URL).json()["total"] == 0


def test_an_attempt_still_being_taken_is_not_waiting(client, db: Session, teacher, student) -> None:
    """The student has not finished it. Counting it would put work in the
    teacher's queue that nobody has handed over."""
    _course_row, module = _course(db, TEACHER_ID, "c-q-inflight")
    chapter = Chapter(id="c-q-inflight-q", module_id=module.id, order_index=0, chapter_type="quiz", title="Тест")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.flush()
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=10, order_index=0)
    db.add(question)
    attempt = QuizAttempt(
        id=uuid.uuid4(), quiz_id=quiz.id, user_id=STUDENT_ID, score=0, max_score=10, completed_at=None
    )
    db.add(attempt)
    db.flush()
    db.add(
        QuizAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            question_id=question.id,
            text_answer="черновик",
            points_earned=0,
        )
    )
    db.commit()

    assert client.get(URL).json()["total"] == 0


def test_another_teachers_course_is_not_in_my_queue(client, db: Session, teacher, student) -> None:
    other = User(id=uuid.uuid4(), email="other@example.com", full_name="Другой", role="teacher")
    db.add(other)
    db.flush()
    course, module = _course(db, other.id, "c-q-foreign")
    _essay_awaiting(db, module, course.id, graded=False)
    db.commit()

    body = client.get(URL).json()

    assert body["total"] == 0
    assert course.id not in body["by_course"]


def test_a_deleted_course_stops_asking_for_attention(client, db: Session, teacher, student) -> None:
    course, module = _course(db, TEACHER_ID, "c-q-deleted")
    _essay_awaiting(db, module, course.id, graded=False)
    course.deleted_at = datetime.now(UTC)
    db.commit()

    assert client.get(URL).json()["total"] == 0


def test_both_kinds_of_waiting_are_one_number(client, db: Session, teacher, student) -> None:
    """A teacher's question is "what do I owe", not "which table is it in"."""
    course, module = _course(db, TEACHER_ID, "c-q-both")
    _essay_awaiting(db, module, course.id, graded=False)
    _assignment_submission(db, module, course.id, status="submitted", grade=None)
    db.commit()

    assert client.get(URL).json()["by_course"][course.id] == 2


def test_a_student_cannot_read_the_queue(student_client, db: Session, teacher, student) -> None:
    assert student_client.get(URL).status_code == 403
