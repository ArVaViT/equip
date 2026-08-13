"""The queue itself, not the count of it.

#961 told a teacher there were seven pieces of work waiting. This is the seven.
Until now the grading interface lived inside the course editor — dashboard,
course, editor, module, chapter, quiz editor, submissions tab — so the weekly
task sat seven levels inside the occasional one and the count had nowhere good
to lead.

Grouped by item rather than by student, because that is how marking actually
goes: thirty answers to one prompt in a row, the standard loaded once instead
of thirty times.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

QUEUE = "/api/v1/grades/queue"


def _course(db: Session, course_id: str):
    course = Course(id=course_id, status="published", created_by=TEACHER_ID)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    return course, module


def _assignment(db: Session, module, course_id: str, index: int = 0, *, title: str = "Эссе"):
    chapter = Chapter(
        id=f"{course_id}-a{index}", module_id=module.id, order_index=index, chapter_type="assignment", title=title
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()
    return assignment


def _submit(db: Session, assignment, *, student_id=STUDENT_ID, minutes_ago: int = 0, content: str = "Работа"):
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=student_id,
            status="submitted",
            grade=None,
            content=content,
            submitted_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )
    )


def _student(db: Session, name: str) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4().hex[:8]}@example.com", full_name=name, role="student")
    db.add(user)
    db.flush()
    return user


def test_the_queue_lists_the_work_not_the_number(client, db: Session, teacher, student) -> None:
    course, module = _course(db, "q-basic")
    assignment = _assignment(db, module, course.id, title="Эссе про благодать")
    _submit(db, assignment)
    db.commit()

    body = client.get(QUEUE).json()

    assert len(body) == 1
    assert body[0]["kind"] == "assignment"
    assert body[0]["title"] == "Эссе про благодать"
    assert body[0]["waiting"] == 1


def test_one_prompt_is_one_group_however_many_answered_it(client, db: Session, teacher, student) -> None:
    """Thirty answers to one prompt is one thing to sit down to, not thirty."""
    course, module = _course(db, "q-group")
    assignment = _assignment(db, module, course.id)
    for i in range(3):
        _submit(db, assignment, student_id=_student(db, f"Студент {i}").id)
    db.commit()

    body = client.get(QUEUE).json()

    assert len(body) == 1
    assert body[0]["waiting"] == 3


def test_the_oldest_thing_waiting_comes_first(client, db: Session, teacher, student) -> None:
    """A queue sorted by size buries the essay that has been waiting three
    weeks under the assignment twelve people just handed in — and the
    three-week-old one is what somebody is upset about."""
    course, module = _course(db, "q-order")
    old = _assignment(db, module, course.id, 0, title="Старое")
    fresh = _assignment(db, module, course.id, 1, title="Свежее")
    _submit(db, old, minutes_ago=60 * 24 * 21)
    for i in range(5):
        _submit(db, fresh, student_id=_student(db, f"Новый {i}").id, minutes_ago=5)
    db.commit()

    body = client.get(QUEUE).json()

    assert [g["title"] for g in body] == ["Старое", "Свежее"]


def test_marked_work_is_not_in_the_queue(client, db: Session, teacher, student) -> None:
    course, module = _course(db, "q-marked")
    assignment = _assignment(db, module, course.id)
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="graded",
            grade=90,
            content="Проверено",
        )
    )
    db.commit()

    assert client.get(QUEUE).json() == []


def test_another_teachers_work_is_not_in_my_queue(client, db: Session, teacher, student) -> None:
    other = User(id=uuid.uuid4(), email="other-q@example.com", full_name="Другой", role="teacher")
    db.add(other)
    db.flush()
    course = Course(id="q-foreign", status="published", created_by=other.id)
    db.add(course)
    module = Module(id="q-foreign-m", course_id="q-foreign", order_index=0, title="M")
    db.add(module)
    db.flush()
    assignment = _assignment(db, module, "q-foreign")
    _submit(db, assignment)
    db.commit()

    assert client.get(QUEUE).json() == []


def test_opening_a_group_gives_the_work_oldest_first(client, db: Session, teacher, student) -> None:
    """A student who handed in three weeks ago has been waiting three weeks,
    and marking newest-first is how they keep waiting."""
    course, module = _course(db, "q-open")
    assignment = _assignment(db, module, course.id)
    first = _student(db, "Первый")
    second = _student(db, "Второй")
    _submit(db, assignment, student_id=first.id, minutes_ago=500, content="Раньше")
    _submit(db, assignment, student_id=second.id, minutes_ago=5, content="Позже")
    db.commit()

    body = client.get(f"{QUEUE}/assignment/{assignment.id}").json()

    assert [w["student_name"] for w in body] == ["Первый", "Второй"]
    assert body[0]["content"] == "Раньше"


def test_a_teacher_cannot_open_a_group_in_a_course_they_do_not_own(client, db: Session, teacher, student) -> None:
    """A queue route that leaks is a route that leaks somebody's essay."""
    other = User(id=uuid.uuid4(), email="other-q2@example.com", full_name="Чужой", role="teacher")
    db.add(other)
    db.flush()
    course = Course(id="q-notmine", status="published", created_by=other.id)
    db.add(course)
    module = Module(id="q-notmine-m", course_id="q-notmine", order_index=0, title="M")
    db.add(module)
    db.flush()
    assignment = _assignment(db, module, "q-notmine")
    _submit(db, assignment)
    db.commit()

    assert client.get(f"{QUEUE}/assignment/{assignment.id}").status_code in {403, 404}


def test_a_student_cannot_read_the_queue(student_client, db: Session, teacher, student) -> None:
    assert student_client.get(QUEUE).status_code == 403
