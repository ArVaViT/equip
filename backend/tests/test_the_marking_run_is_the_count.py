"""The marking run behind the review queue, and the number that leads into it.

A teacher taps «5 на проверку» on the dashboard and lands in a run that walks
every one of those five, across every course they teach, with «Дальше» between
them. The run and the number are built on the same two queries; these tests
hold them to it, because the past defect here was exactly a badge counting
work the grading page would not show — a number that could never reach zero.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.models.user import User
from app.services.content_versions.write import record_human_version

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

RUN = "/api/v1/grades/queue/work"
PENDING = "/api/v1/grades/pending"

# Fixed ids: parametrized and collected identically on every xdist worker.
ESSAY_QUESTION = uuid.UUID("00000000-0000-4000-8000-00000000e551")


def _course(db: Session, course_id: str, owner=TEACHER_ID):
    db.add(Course(id=course_id, status="published", created_by=owner))
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    return module


def _student(db: Session, name: str) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4().hex[:8]}@example.com", full_name=name, role="student")
    db.add(user)
    db.flush()
    return user


def _assignment(db: Session, module, *, index: int, title: str = "Эссе", max_score: int = 20) -> Assignment:
    chapter = Chapter(
        id=f"{module.course_id}-a{index}",
        module_id=module.id,
        order_index=index,
        chapter_type="assignment",
        title=title,
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=max_score)
    db.add(assignment)
    db.flush()
    return assignment


def _hand_in(db: Session, assignment, student_id, *, minutes_ago: int, content: str = "Работа") -> AssignmentSubmission:
    submission = AssignmentSubmission(
        id=uuid.uuid4(),
        assignment_id=assignment.id,
        student_id=student_id,
        status="submitted",
        grade=None,
        content=content,
        submitted_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    db.add(submission)
    db.flush()
    return submission


def _essay(db: Session, module, *, index: int, question_id=None, points: int = 5):
    chapter = Chapter(
        id=f"{module.course_id}-q{index}", module_id=module.id, order_index=index, chapter_type="quiz", title="Тест"
    )
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.flush()
    question = QuizQuestion(
        id=question_id or uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=points, order_index=0
    )
    db.add(question)
    db.flush()
    return quiz, question


def _answer(db: Session, quiz, question, student_id, *, minutes_ago: int, text: str = "Ответ") -> QuizAnswer:
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=student_id,
        score=0,
        max_score=question.points,
        passed=False,
        completed_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    db.add(attempt)
    db.flush()
    answer = QuizAnswer(id=uuid.uuid4(), attempt_id=attempt.id, question_id=question.id, text_answer=text)
    db.add(answer)
    db.flush()
    return answer


def _two_courses(db: Session) -> dict:
    """A week's grading: an essay question in one course, an assignment in another."""
    anna, boris = _student(db, "Анна"), _student(db, "Борис")
    first = _course(db, "run-one")
    quiz, question = _essay(db, first, index=0, question_id=ESSAY_QUESTION)
    old_answer = _answer(db, quiz, question, anna.id, minutes_ago=60 * 24 * 3, text="Благодать — дар")
    new_answer = _answer(db, quiz, question, boris.id, minutes_ago=60)
    second = _course(db, "run-two")
    assignment = _assignment(db, second, index=0, title="Письмо церкви")
    submission = _hand_in(db, assignment, STUDENT_ID, minutes_ago=60 * 24)
    db.commit()
    return {"old_answer": old_answer, "new_answer": new_answer, "submission": submission, "question": question}


def test_the_run_is_every_piece_the_count_counts(client, db: Session, teacher, student) -> None:
    _two_courses(db)

    run = client.get(RUN).json()["items"]
    pending = client.get(PENDING).json()

    assert len(run) == pending["total"] == 3
    per_course: dict[str, int] = {}
    for item in run:
        per_course[item["course_id"]] = per_course.get(item["course_id"], 0) + 1
    assert per_course == pending["by_course"]


def test_the_run_goes_by_question_oldest_first(client, db: Session, teacher, student) -> None:
    """The question that has waited longest leads, and its answers stay
    together — the standard loaded once — before the next item starts."""
    seeded = _two_courses(db)

    run = client.get(RUN).json()["items"]

    assert [i["id"] for i in run] == [
        str(seeded["old_answer"].id),
        str(seeded["new_answer"].id),
        str(seeded["submission"].id),
    ]


def test_each_piece_carries_what_it_takes_to_mark_it(client, db: Session, teacher, student) -> None:
    seeded = _two_courses(db)
    record_human_version(
        db,
        entity_type="quiz_question",
        entity_id=str(seeded["question"].id),
        field="question_text",
        locale="ru",
        text="Что такое благодать?",
    )
    db.commit()

    first, _, last = client.get(RUN, headers={"Accept-Language": "ru"}).json()["items"]

    # An answer read without its question cannot be judged.
    assert first["kind"] == "quiz_answer"
    assert first["prompt"] == "Что такое благодать?"
    assert first["content"] == "Благодать — дар"
    assert first["student_name"] == "Анна"
    assert first["max_points"] == 5
    assert last["kind"] == "assignment"
    assert last["title"] == "Письмо церкви"
    assert last["max_points"] == 20


def test_marked_through_the_existing_routes_it_leaves_both(client, db: Session, teacher, student) -> None:
    """No grading path of its own: the run says what is next, the routes that
    already mark work do the marking, and the number follows."""
    seeded = _two_courses(db)

    answered = client.patch(
        f"/api/v1/quizzes/answers/{seeded['old_answer'].id}",
        json={"points_earned": 4, "grader_comment": "Хорошо раскрыта тема"},
    )
    graded = client.put(
        f"/api/v1/assignments/submissions/{seeded['submission'].id}/grade",
        json={"grade": 18, "feedback": "Структура ясная", "status": "graded"},
    )

    assert answered.status_code == 200, answered.text
    assert graded.status_code == 200, graded.text
    run = client.get(RUN).json()["items"]
    assert [i["id"] for i in run] == [str(seeded["new_answer"].id)]
    assert client.get(PENDING).json()["total"] == 1


def test_another_teachers_work_is_not_in_my_run(client, db: Session, teacher, student) -> None:
    other = User(id=uuid.uuid4(), email="other-run@example.com", full_name="Другой", role="teacher")
    db.add(other)
    db.flush()
    module = _course(db, "run-foreign", owner=other.id)
    _hand_in(db, _assignment(db, module, index=0), STUDENT_ID, minutes_ago=5)
    db.commit()

    assert client.get(RUN).json()["items"] == []
    assert client.get(PENDING).json()["total"] == 0


def test_a_student_cannot_read_the_run(student_client) -> None:
    assert student_client.get(RUN).status_code == 403


# Each case is a way a piece of work stops waiting on the teacher. Whatever
# the reason, it has to leave the count and the run together.
@pytest.mark.parametrize(
    "case",
    [
        "marked",
        "handed_back",
        "student_deactivated",
        "lesson_deleted",
        "course_deleted",
        "answer_read",
        "resubmitted",
        "second_version_marked",
    ],
)
def test_the_count_and_the_run_never_disagree(client, db: Session, teacher, student, case: str) -> None:
    seeded = _two_courses(db)
    submission = db.get(AssignmentSubmission, seeded["submission"].id)
    if case == "marked":
        submission.status, submission.grade = "graded", 15
    elif case == "handed_back":
        submission.status = "returned"
    elif case == "student_deactivated":
        db.get(User, STUDENT_ID).deactivated_at = datetime.now(UTC)
    elif case == "lesson_deleted":
        db.get(Chapter, "run-one-q0").deleted_at = datetime.now(UTC)
    elif case == "course_deleted":
        db.get(Course, "run-two").deleted_at = datetime.now(UTC)
    elif case == "answer_read":
        db.get(QuizAnswer, seeded["old_answer"].id).graded_at = datetime.now(UTC)
    elif case in ("resubmitted", "second_version_marked"):
        # A second version of the same student's work: only the latest counts.
        newer = _hand_in(db, db.get(Assignment, submission.assignment_id), STUDENT_ID, minutes_ago=5, content="v2")
        if case == "second_version_marked":
            newer.status, newer.grade = "graded", 19
    db.commit()

    run = client.get(RUN).json()["items"]
    pending = client.get(PENDING).json()
    groups = client.get("/api/v1/grades/queue").json()

    assert len(run) == pending["total"] == sum(g["waiting"] for g in groups)
    if case == "resubmitted":
        assert pending["total"] == 3
        assert "v2" in [i["content"] for i in run]
        assert str(submission.id) not in [i["id"] for i in run]
    else:
        assert pending["total"] < 3


def test_the_student_and_the_teacher_agree_on_which_version_waits(client, db: Session, teacher, student) -> None:
    """The student is told «not marked yet» about exactly the work the teacher
    has in the queue — the same latest version, not a stale first draft."""
    from app.services.grading_queue import work_awaiting_marking

    seeded = _two_courses(db)
    assignment = db.get(Assignment, seeded["submission"].assignment_id)
    newer = _hand_in(db, assignment, STUDENT_ID, minutes_ago=5, content="v2")
    newer.status, newer.grade = "graded", 19
    db.commit()

    awaiting = work_awaiting_marking(db, STUDENT_ID, course_id="run-two", quizzes=[], assignments=[assignment])
    assert awaiting == set()
    assert client.get(PENDING).json()["by_course"].get("run-two") is None


def test_a_long_run_is_sent_in_part_and_counted_in_full(db: Session, teacher, student) -> None:
    from app.services.grading_queue import waiting_work

    _two_courses(db)

    run = waiting_work(db, TEACHER_ID, display_locale="ru", limit=2)

    # The whole first question (two answers), then the cap; the count is whole.
    assert len(run["items"]) == 2
    assert run["total"] == 3


def test_an_assignment_says_what_was_asked(client, db: Session, teacher, student) -> None:
    seeded = _two_courses(db)
    assignment_id = str(seeded["submission"].assignment_id)
    for field, text in (("title", "Письмо церкви в Фессалониках"), ("description", "Напишите письмо на страницу.")):
        record_human_version(db, entity_type="assignment", entity_id=assignment_id, field=field, locale="ru", text=text)
    db.commit()

    last = client.get(RUN, headers={"Accept-Language": "ru"}).json()["items"][-1]

    assert last["title"] == "Письмо церкви в Фессалониках"
    assert last["prompt"] == "Напишите письмо на страницу."


def test_ready_comments_know_the_students_language(client, db: Session, teacher, student) -> None:
    _two_courses(db)
    db.get(User, STUDENT_ID).preferred_locale = "uk"
    db.commit()

    last = client.get(RUN).json()["items"][-1]

    assert last["student_locale"] == "uk"


def test_the_run_will_not_mark_over_work_marked_meanwhile(client, db: Session, teacher, student) -> None:
    """Loaded as waiting, marked by somebody else since: refused, not overwritten."""
    seeded = _two_courses(db)
    submission = db.get(AssignmentSubmission, seeded["submission"].id)
    submission.status, submission.grade = "returned", 10
    db.get(QuizAnswer, seeded["old_answer"].id).graded_at = datetime.now(UTC)
    db.commit()

    graded = client.put(
        f"/api/v1/assignments/submissions/{submission.id}/grade",
        json={"grade": 18, "status": "graded", "expect_waiting": True},
    )
    answered = client.patch(
        f"/api/v1/quizzes/answers/{seeded['old_answer'].id}", json={"points_earned": 4, "expect_waiting": True}
    )

    assert graded.status_code == 409
    assert graded.json()["detail"]["code"] == "grading.already_marked"
    assert answered.status_code == 409
    db.refresh(submission)
    assert (submission.status, submission.grade) == ("returned", 10)
    # Without the flag the course screens re-mark on purpose, as before.
    again = client.put(f"/api/v1/assignments/submissions/{submission.id}/grade", json={"grade": 18, "status": "graded"})
    assert again.status_code == 200
