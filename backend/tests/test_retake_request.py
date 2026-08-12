"""What does a student who failed actually do? (D12)

Until now the answer was "emails the teacher, if they know which teacher".
This adds no grading power — it routes the student to the four the teacher
already has: gift an attempt, return the work, excuse the item, set the grade
by hand. What it must get right is who may ask, for what, and how often.

The person using this button is anxious about failing. It has to be safe to
press twice.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.notification import Notification
from app.models.quiz import Quiz, QuizAttempt
from app.models.student_grade import StudentGrade
from app.services.certificate_readiness import RETAKE_REQUEST_NOTIFICATION

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

URL = "/api/v1/grades/my/{}/retake-request"


def _course(db: Session, course_id: str, *, scheme: str = "letter", threshold: int = 70):
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
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=100))
    db.flush()
    return course, module


def _failed_assignment(db: Session, module, course_id: str) -> None:
    """Handed in, marked, and not enough — the shape a retake exists for."""
    chapter = Chapter(
        id=f"{course_id}-a",
        module_id=module.id,
        order_index=0,
        chapter_type="assignment",
        title="Эссе",
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
            status="graded",
            grade=40,
        )
    )


def _unmarked_assignment(db: Session, module, course_id: str) -> None:
    chapter = Chapter(
        id=f"{course_id}-a",
        module_id=module.id,
        order_index=0,
        chapter_type="assignment",
        title="Эссе",
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
            status="submitted",
            grade=None,
        )
    )


def _requests(db: Session) -> list[Notification]:
    return db.query(Notification).filter(Notification.type == RETAKE_REQUEST_NOTIFICATION).all()


def test_a_failing_student_reaches_their_teacher(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, "retake-fail")
    _failed_assignment(db, module, course.id)
    db.commit()

    response = student_client.post(URL.format(course.id))

    assert response.status_code == 200
    assert response.json()["status"] == "requested"
    requests = _requests(db)
    assert len(requests) == 1
    # It lands on the teacher who owns the course, not in a queue nobody reads.
    assert requests[0].user_id == TEACHER_ID
    # And it says what is wrong, so the teacher opens the drawer already knowing
    # which of their four powers this calls for.
    assert requests[0].meta["blockers"] == ["below_threshold"]
    assert requests[0].link == f"/teacher/courses/{course.id}/gradebook"


def test_pressing_it_twice_does_not_ask_twice(student_client, db: Session, teacher, student) -> None:
    """The person pressing this is anxious about failing. Three notifications a
    teacher has to dismiss is how the button gets removed."""
    course, module = _course(db, "retake-twice")
    _failed_assignment(db, module, course.id)
    db.commit()

    first = student_client.post(URL.format(course.id)).json()
    second = student_client.post(URL.format(course.id)).json()

    assert first["status"] == "requested"
    assert second["status"] == "already_requested"
    assert len(_requests(db)) == 1


def test_asking_again_after_the_teacher_read_it_and_slept_on_it_is_allowed(
    student_client, db: Session, teacher, student
) -> None:
    """A read notification the teacher acted on nothing about, a day later, is
    a student with no other channel. Folding that into silence is how the
    recovery path stops being one."""
    course, module = _course(db, "retake-again")
    _failed_assignment(db, module, course.id)
    db.commit()
    student_client.post(URL.format(course.id))
    stale = _requests(db)[0]
    stale.is_read = True
    stale.created_at = datetime.now(UTC) - timedelta(hours=48)
    db.commit()

    assert student_client.post(URL.format(course.id)).json()["status"] == "requested"
    assert len(_requests(db)) == 2


def test_unread_work_is_not_something_to_retake(student_client, db: Session, teacher, student) -> None:
    """The answer to "nobody has read my essay" is to wait. A request button
    there sends a student chasing a teacher for something already in their
    queue — and teaches them the button means nothing."""
    course, module = _course(db, "retake-unmarked")
    _unmarked_assignment(db, module, course.id)
    db.commit()

    assert student_client.post(URL.format(course.id)).status_code == 400
    assert _requests(db) == []


def test_a_passing_student_has_nothing_to_ask_for(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, "retake-passing")
    chapter = Chapter(
        id="retake-passing-a",
        module_id=module.id,
        order_index=0,
        chapter_type="assignment",
        title="Эссе",
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
            status="graded",
            grade=95,
        )
    )
    db.commit()

    assert student_client.post(URL.format(course.id)).status_code == 400


def test_a_hand_set_pass_closes_the_request_too(student_client, db: Session, teacher, student) -> None:
    """The teacher already decided (D7). A request against that decision asks
    them to reconsider something they settled, and reads as the student
    disputing it."""
    course, module = _course(db, "retake-override")
    _failed_assignment(db, module, course.id)
    db.add(
        StudentGrade(
            id=uuid.uuid4(),
            student_id=STUDENT_ID,
            course_id=course.id,
            override_score=Decimal("90.00"),
            graded_by=TEACHER_ID,
        )
    )
    db.commit()

    assert student_client.post(URL.format(course.id)).status_code == 400


def test_a_failed_quiz_is_a_reason_to_ask(student_client, db: Session, teacher, student) -> None:
    """The one shape where the student genuinely cannot proceed alone: attempts
    are spent, and only the teacher can gift another."""
    course, module = _course(db, "retake-quiz", scheme="pass_fail")
    chapter = Chapter(
        id="retake-quiz-q",
        module_id=module.id,
        order_index=0,
        chapter_type="quiz",
        title="Тест",
    )
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
            score=30,
            max_score=100,
            passed=False,
            completed_at=datetime.now(UTC),
        )
    )
    db.commit()

    assert student_client.post(URL.format(course.id)).json()["status"] == "requested"
    assert _requests(db)[0].meta["blockers"] == ["quizzes_not_passed"]


def test_a_stranger_cannot_ask_about_a_course_they_do_not_take(student_client, db: Session, teacher, student) -> None:
    course = Course(id="retake-foreign", status="published", created_by=TEACHER_ID)
    db.add(course)
    db.commit()

    assert student_client.post(URL.format(course.id)).status_code == 403


def test_one_students_request_does_not_speak_for_another(student_client, db: Session, teacher, student) -> None:
    """The route takes no student parameter — identity comes from the token —
    and this is the test that says so on purpose, so that adding one later is a
    deliberate act rather than a convenience."""
    course, module = _course(db, "retake-self")
    _failed_assignment(db, module, course.id)
    db.commit()

    student_client.post(URL.format(course.id))

    assert _requests(db)[0].meta["student_id"] == str(STUDENT_ID)
