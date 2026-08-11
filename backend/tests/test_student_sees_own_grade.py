"""What a student may see of their own grade, and what they may never see (D10).

Until now a student could see a progress bar, individual quiz scores, and — if
a teacher had hand-set one — a bare letter on their dashboard. Not their course
grade. That is the wrong way round for what this phase builds toward: the
certificate pass-gate goes live at the end of it, and a student refused a
certificate has to have known why for weeks.

Half of these tests are about what the endpoint must NOT contain. The privacy
rules are the ones nobody notices are broken until it is a person's grade on
someone else's screen.
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
from app.services.grade_exemption_service import apply_exemption

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID

URL = "/api/v1/grades/my/{course_id}/breakdown"


def _course(db: Session, teacher, course_id: str, *, scheme: str = "letter", qw: int = 100, aw: int = 0):
    course = Course(
        id=course_id,
        status="published",
        created_by=teacher.id,
        quiz_weight=qw,
        assignment_weight=aw,
        grading_scheme=scheme,
        pass_threshold=Decimal("70.00"),
    )
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=50))
    db.commit()
    return course, module


def _quiz(db: Session, module, course_id: str, index: int, title: str) -> Quiz:
    chapter = Chapter(
        id=f"{course_id}-q{index}", module_id=module.id, order_index=index, chapter_type="quiz", title=title
    )
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.flush()
    return quiz


def _assignment(db: Session, module, course_id: str, index: int, title: str) -> Assignment:
    chapter = Chapter(
        id=f"{course_id}-a{index}",
        module_id=module.id,
        order_index=100 + index,
        chapter_type="assignment",
        title=title,
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()
    return assignment


def _attempt(db: Session, quiz, score: int) -> QuizAttempt:
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=score,
        max_score=100,
        passed=score >= 70,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    return attempt


# --------------------------------------------------------------------------
# the numbers
# --------------------------------------------------------------------------


def test_a_student_sees_both_of_their_grades(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, teacher, "c-my-pair")
    quizzes = [_quiz(db, module, course.id, i, f"Тест {i}") for i in range(4)]
    _attempt(db, quizzes[0], 100)
    db.commit()

    resp = student_client.get(URL.format(course_id=course.id))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_score"] == 100.0
    assert body["final_score"] == 25.0
    assert body["scores_differ"] is True
    assert body["pass_threshold"] == "70.00"


def test_a_student_is_told_why_there_is_no_number(student_client, db: Session, teacher, student) -> None:
    """Nobody has marked anything yet. A 0% here would say they failed a course
    that has not started marking."""
    course, module = _course(db, teacher, "c-my-unmarked")
    _quiz(db, module, course.id, 0, "Тест")
    db.commit()

    body = student_client.get(URL.format(course_id=course.id)).json()

    assert body["current_score"] is None
    assert body["final_score"] is None
    assert body["result_state"] == "not_graded_yet"


def test_a_hand_set_grade_is_what_the_student_is_told(student_client, db: Session, teacher, student) -> None:
    """The override IS the official grade (D7), so it is the answer to "what
    did I get" — and the teacher's note to them comes with it."""
    course, module = _course(db, teacher, "c-my-override")
    _quiz(db, module, course.id, 0, "Тест")
    db.add(
        StudentGrade(
            course_id=course.id,
            student_id=STUDENT_ID,
            override_code="B",
            comment="Хорошая работа, но раздел 3 стоит переписать",
            reason="Поставлено по просьбе пастора",
        )
    )
    db.commit()

    body = student_client.get(URL.format(course_id=course.id)).json()

    assert body["official_grade"] == "B"
    assert body["comment"] == "Хорошая работа, но раздел 3 стоит переписать"


# --------------------------------------------------------------------------
# what must never be in it
# --------------------------------------------------------------------------


def test_the_teachers_private_reason_never_reaches_the_student(student_client, db: Session, teacher, student) -> None:
    """`comment` is the note written TO the student; `reason` is the note about
    them, written for the institution — «поставлено по просьбе пастора»,
    «исправлено после апелляции». They are different audiences (D7), and the
    second one arriving on a student's screen is the kind of mistake that ends
    a teacher's relationship with a class."""
    course, module = _course(db, teacher, "c-my-reason")
    _quiz(db, module, course.id, 0, "Тест")
    db.add(
        StudentGrade(
            course_id=course.id,
            student_id=STUDENT_ID,
            override_code="C",
            comment="Виден рост",
            reason="Натянуто, чтобы не отчислять",
        )
    )
    db.commit()

    resp = student_client.get(URL.format(course_id=course.id))

    assert "Натянуто" not in resp.text
    assert "reason" not in resp.json()
    # The response check above passes for free — the response model drops
    # unknown keys, so it cannot catch the way this would actually break.
    # The failure mode is somebody adding the field to the schema, so that is
    # what is asserted.
    from app.schemas.grade import MyCourseGrade

    assert "reason" not in MyCourseGrade.model_fields, (
        "`reason` is the teacher's note to the institution (D7) and must never gain a home in a student-facing schema"
    )


def test_no_class_average_no_peers_no_rank(student_client, db: Session, teacher, student) -> None:
    """A grade is between a student, their teacher and the school. Absent from
    the schema rather than filtered out of a query, so putting one back would
    take a deliberate change (D10.4)."""
    from app.models.user import User

    course, module = _course(db, teacher, "c-my-private")
    quiz = _quiz(db, module, course.id, 0, "Тест")
    _attempt(db, quiz, 40)

    classmate = User(id=uuid.uuid4(), email="classmate@example.com", full_name="Одноклассник", role="student")
    db.add(classmate)
    db.add(Enrollment(id="enr-classmate", user_id=classmate.id, course_id=course.id, progress=100))
    db.commit()

    body = student_client.get(URL.format(course_id=course.id))

    assert "Одноклассник" not in body.text
    assert "classmate@example.com" not in body.text
    for forbidden in ("class_average", "rank", "percentile", "students"):
        assert forbidden not in body.json()


def test_a_student_cannot_read_a_course_they_are_not_in(student_client, db: Session, teacher, student) -> None:
    course = Course(id="c-my-outsider", status="published", created_by=teacher.id)
    db.add(course)
    db.commit()

    resp = student_client.get(URL.format(course_id=course.id))

    assert resp.status_code == 403


# --------------------------------------------------------------------------
# the per-item list
# --------------------------------------------------------------------------


def test_an_unread_essay_says_it_is_waiting_not_that_it_is_zero(student_client, db: Session, teacher, student) -> None:
    """The same defect the teacher's gradebook had, on the side of the person
    it frightens: an essay sits at 0 out of 10 with `passed = false` from the
    moment it is submitted until somebody reads it."""
    course, module = _course(db, teacher, "c-my-pending")
    quiz = _quiz(db, module, course.id, 0, "Эссе")
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=10, order_index=0)
    db.add(question)
    attempt = _attempt(db, quiz, 0)
    db.add(
        QuizAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            question_id=question.id,
            text_answer="Мой ответ",
            points_earned=0,
        )
    )
    db.commit()

    items = student_client.get(URL.format(course_id=course.id)).json()["items"]
    essay = next(i for i in items if i["title"] == "Эссе")

    assert essay["status"] == "pending_review"
    assert essay["score"] is None, "a number here is the running total, which is the thing being hidden"


def test_work_never_started_is_listed_as_owed(student_client, db: Session, teacher, student) -> None:
    """The result arrays only carry items with an attempt or a submission, so
    without this the list quietly omits exactly the work a student needs to
    see."""
    course, module = _course(db, teacher, "c-my-owed", qw=50, aw=50)
    _quiz(db, module, course.id, 0, "Нетронутый тест")
    _assignment(db, module, course.id, 0, "Нетронутое задание")
    db.commit()

    items = student_client.get(URL.format(course_id=course.id)).json()["items"]

    assert {i["title"] for i in items} == {"Нетронутый тест", "Нетронутое задание"}
    assert {i["status"] for i in items} == {"not_submitted"}


def test_excused_work_says_excused_not_missing(student_client, db: Session, teacher, student) -> None:
    """«Освобождено», never «не сдано» — the work was not missed, it was set
    aside by a teacher who wrote down why."""
    course, module = _course(db, teacher, "c-my-excused")
    quiz = _quiz(db, module, course.id, 0, "Пропущенный тест")
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

    items = student_client.get(URL.format(course_id=course.id)).json()["items"]

    assert [i["status"] for i in items] == ["excused"]


def test_a_marked_assignment_shows_its_percentage(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, teacher, "c-my-marked", qw=0, aw=100)
    assignment = _assignment(db, module, course.id, 0, "Эссе по Деяниям")
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="graded",
            grade=88,
            graded_by=teacher.id,
        )
    )
    db.commit()

    items = student_client.get(URL.format(course_id=course.id)).json()["items"]

    assert items[0]["status"] == "graded"
    assert items[0]["score"] == 88.0


def test_a_submitted_but_unmarked_assignment_is_pending(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, teacher, "c-my-submitted", qw=0, aw=100)
    assignment = _assignment(db, module, course.id, 0, "Эссе")
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="submitted",
        )
    )
    db.commit()

    items = student_client.get(URL.format(course_id=course.id)).json()["items"]

    assert items[0]["status"] == "pending_review"
    assert items[0]["score"] is None


# --------------------------------------------------------------------------
# the scheme whose rule is not arithmetic
# --------------------------------------------------------------------------


def test_a_pass_fail_course_does_not_show_a_percentage(student_client, db: Session, teacher, student) -> None:
    """«Зачёт» means every required piece of work accepted, not an average
    clearing a line (D2). That rule is not built yet, so the weighted number is
    not this course's result — and showing it as one would be exactly the
    hidden-average behaviour the design removed."""
    course, module = _course(db, teacher, "c-my-passfail", scheme="pass_fail")
    quiz = _quiz(db, module, course.id, 0, "Тест")
    _attempt(db, quiz, 95)
    db.commit()

    body = student_client.get(URL.format(course_id=course.id)).json()

    assert body["scores_withheld"] is True
    assert body["current_score"] is None
    assert body["final_score"] is None
    assert body["items"], "the per-item list is still the honest part and stays"
    # And the student is told the actual result rather than nothing: «зачёт» is
    # predictable without arithmetic, which is the point of the scheme (D2).
    assert body["zachet"] in {"zachet", "nezachet", "not_attested"}


# --------------------------------------------------------------------------
# a chapter is not one piece of work
#
# Found by an adversarial pass over the first version of this endpoint — and
# it was the very thing the change claimed to fix.
# --------------------------------------------------------------------------


def _two_quizzes_in_one_chapter(db: Session, teacher, course_id: str):
    course, module = _course(db, teacher, course_id)
    chapter = Chapter(id=f"{course_id}-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Глава")
    db.add(chapter)
    db.flush()
    first = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    second = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add_all([first, second])
    db.commit()
    return course, first, second


def test_the_second_quiz_in_a_chapter_is_not_swallowed(student_client, db: Session, teacher, student) -> None:
    """One quiz of two, answered perfectly, is 50% — and the list has to say
    where the other half went.

    The list was keyed by chapter while the grade is computed per item, so the
    untouched sibling vanished: the student was shown 50% overall and a single
    piece of work at 100%, with nothing accounting for the difference. That is
    worse than a wrong number, because there is nothing on screen to question.
    """
    course, first, _second = _two_quizzes_in_one_chapter(db, teacher, "c-my-two-quizzes")
    _attempt(db, first, 100)
    db.commit()

    body = student_client.get(URL.format(course_id=course.id)).json()

    assert body["final_score"] == 50.0
    assert len(body["items"]) == 2, "one row per piece of work, not per chapter"
    assert sorted(i["status"] for i in body["items"]) == ["graded", "not_submitted"]


def test_a_quiz_and_an_assignment_in_one_chapter_are_both_listed(student_client, db: Session, teacher, student) -> None:
    """`gradable_item` names one item per chapter and the quiz wins, so an
    assignment sharing a chapter was both absent and, when it was the only one
    left, mislabelled as a quiz."""
    course, module = _course(db, teacher, "c-my-mixed-chapter", qw=50, aw=50)
    chapter = Chapter(
        id="c-my-mixed-chapter-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Глава"
    )
    db.add(chapter)
    db.flush()
    db.add(Quiz(id=uuid.uuid4(), chapter_id=chapter.id))
    db.add(Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100))
    db.commit()

    items = student_client.get(URL.format(course_id=course.id)).json()["items"]

    assert sorted(i["kind"] for i in items) == ["assignment", "quiz"]
    assert {i["status"] for i in items} == {"not_submitted"}


def test_each_item_carries_its_own_id(student_client, db: Session, teacher, student) -> None:
    """Two items in one chapter were indistinguishable to the client, which
    keyed its list on the chapter and collapsed them."""
    course, first, second = _two_quizzes_in_one_chapter(db, teacher, "c-my-item-ids")
    _attempt(db, first, 100)
    db.commit()

    items = student_client.get(URL.format(course_id=course.id)).json()["items"]

    ids = {i["item_id"] for i in items}
    assert ids == {str(first.id), str(second.id)}


def test_a_pass_fail_student_is_told_zachet_not_a_silence(student_client, db: Session, teacher, student) -> None:
    """Withholding the percentage while saying nothing in its place would leave
    the student worse informed than before the scheme existed."""
    from app.models.assignment import AssignmentSubmission

    course, module = _course(db, teacher, "c-my-zachet", scheme="pass_fail", qw=0, aw=100)
    assignment = _assignment(db, module, course.id, 0, "Эссе")
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="graded",
            grade=55,
            graded_by=teacher.id,
        )
    )
    enrolment = db.query(Enrollment).filter(Enrollment.course_id == course.id).first()
    enrolment.progress = 100
    db.commit()

    body = student_client.get(URL.format(course_id=course.id)).json()

    assert body["zachet"] == "zachet", "the work was accepted; the 55 on it is not the rule"
    assert body["current_score"] is None, "and no percentage is shown for it"


def test_a_pass_fail_student_with_work_returned_is_told_nezachet(student_client, db: Session, teacher, student) -> None:
    from app.models.assignment import AssignmentSubmission

    course, module = _course(db, teacher, "c-my-nezachet", scheme="pass_fail", qw=0, aw=100)
    assignment = _assignment(db, module, course.id, 0, "Эссе")
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="returned",
            grade=90,
            graded_by=teacher.id,
        )
    )
    enrolment = db.query(Enrollment).filter(Enrollment.course_id == course.id).first()
    enrolment.progress = 100
    db.commit()

    body = student_client.get(URL.format(course_id=course.id)).json()

    assert body["zachet"] == "nezachet"
    # `returned` rather than `pending_review`: pending work waits on the
    # teacher, returned work waits on the student. Shown as «проверено» — which
    # is what a graded-and-returned essay used to render as — the list would say
    # everything is done while the course result says «незачёт».
    assert body["items"][0]["status"] == "returned"
    assert body["items"][0]["score"] is None, "the mark on it is not the state it is in"
