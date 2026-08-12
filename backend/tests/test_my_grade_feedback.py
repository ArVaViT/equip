"""The teacher's written note, where the student actually looks (D10.3).

It has always been stored and always been reachable — on the chapter, two
navigations away. It was never on the card the student opens to see how they
are doing. For a school teaching by correspondence the written note *is* the
teaching, and an essay showing "90%" with none of it beside the number is the
grade without the lesson.

Found by walking a course end to end against production rather than by a test:
every test asserted the number, and the number was right.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.services.grade_exemption_service import apply_exemption

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

URL = "/api/v1/grades/my/{}/breakdown"


def _course(db: Session, course_id: str):
    course = Course(id=course_id, status="published", created_by=TEACHER_ID, grading_scheme="letter")
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=100))
    db.flush()
    return course, module


def _essay(db: Session, module, course_id: str, *, status: str | None, grade: int | None, feedback: str | None):
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
    if status is not None:
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment.id,
                student_id=STUDENT_ID,
                status=status,
                grade=grade,
                feedback=feedback,
            )
        )
    return assignment


def _item(client, course_id: str) -> dict:
    return client.get(URL.format(course_id)).json()["items"][0]


def test_a_marked_essay_carries_what_the_teacher_wrote(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, "fb-graded")
    _essay(db, module, course.id, status="graded", grade=90, feedback="Much stronger on the second reading.")
    db.commit()

    assert _item(student_client, course.id)["feedback"] == "Much stronger on the second reading."


def test_work_handed_back_carries_it_most_of_all(student_client, db: Session, teacher, student) -> None:
    """The score is withheld on a returned row because it is provisional. The
    words are the opposite: work handed back with nothing said about what to
    change is the one row on this card a student cannot act on."""
    course, module = _course(db, "fb-returned")
    _essay(db, module, course.id, status="returned", grade=40, feedback="Add the passages you are arguing from.")
    db.commit()

    item = _item(student_client, course.id)

    assert item["status"] == "returned"
    assert item["score"] is None
    assert item["feedback"] == "Add the passages you are arguing from."


def test_nothing_is_invented_for_work_never_handed_in(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, "fb-missing")
    _essay(db, module, course.id, status=None, grade=None, feedback=None)
    db.commit()

    assert _item(student_client, course.id)["feedback"] is None


def test_an_excused_item_says_nothing(student_client, db: Session, teacher, student) -> None:
    """A note there is about a decision the student did not make."""
    course, module = _course(db, "fb-excused")
    assignment = _essay(db, module, course.id, status="graded", grade=50, feedback="Not your fault.")
    db.commit()
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="assignment",
        item_id=assignment.id,
        teacher_id=TEACHER_ID,
    )
    db.commit()

    item = _item(student_client, course.id)

    assert item["status"] == "excused"
    assert item["feedback"] is None


def test_an_unread_essay_has_nothing_to_show_yet(student_client, db: Session, teacher, student) -> None:
    course, module = _course(db, "fb-pending")
    _essay(db, module, course.id, status="submitted", grade=None, feedback=None)
    db.commit()

    item = _item(student_client, course.id)

    assert item["status"] == "pending_review"
    assert item["feedback"] is None
