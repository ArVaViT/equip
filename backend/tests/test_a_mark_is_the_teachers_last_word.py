"""A marked piece of work is finished until a teacher says otherwise.

Before this, `submit_assignment` inserted a new submission unconditionally and
`latest_submissions` resolves the newest row as the one that counts. So a
student marked 90 pressed submit again and the 90 stopped being their grade:
the item went back to «ждёт проверки», their итоговая fell — unmarked work
counts as zero — and the certificate gate refused them.

Three things were wrong with that, and the third is why it is a design bug
rather than a missing validation: a student could undo a passing grade by
accident, it was a free re-grade on demand, and it put the last word with the
student rather than the teacher. Every document this platform issues — the
ведомость, the certificate, the transcript — rests on a grade being a decision
by a qualified person.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

SUBMIT = "/api/v1/assignments/{}/submit"


def _assignment(db: Session, course_id: str):
    course = Course(id=course_id, status="published", created_by=TEACHER_ID, grading_scheme="letter")
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.flush()
    chapter = Chapter(id=f"{course_id}-a", module_id=module.id, order_index=0, chapter_type="assignment", title="Эссе")
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()
    return assignment


def _existing(db: Session, assignment, *, status: str, grade: int | None):
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status=status,
            grade=grade,
            content="Первая версия",
        )
    )
    db.commit()


def test_marked_work_cannot_be_overwritten_by_the_student(student_client, db: Session, teacher, student) -> None:
    """The grade a teacher gave stays the grade until a teacher changes it."""
    assignment = _assignment(db, "lw-graded")
    _existing(db, assignment, status="graded", grade=90)

    response = student_client.post(
        SUBMIT.format(assignment.id),
        json={"content": "Вторая попытка", "declaration": {"ai_use": "none", "statement": "Я написал эту работу сам."}},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["context"]["reason"] == "already_graded"
    assert db.query(AssignmentSubmission).count() == 1, "and nothing was written"


def test_the_refusal_points_at_the_way_back_in(student_client, db: Session, teacher, student) -> None:
    """A refusal that does not say what would change the answer sends the
    student to their teacher by email — the exact outcome D12 exists to
    replace."""
    assignment = _assignment(db, "lw-points")
    _existing(db, assignment, status="graded", grade=40)

    body = student_client.post(
        SUBMIT.format(assignment.id),
        json={"content": "Ещё раз", "declaration": {"ai_use": "none", "statement": "Я написал эту работу сам."}},
    ).json()

    assert "retake" in body["detail"]["message"].lower()


def test_work_handed_back_may_be_submitted_again(student_client, db: Session, teacher, student) -> None:
    """«Вернуть на доработку» *is* the invitation to submit again, and it came
    from the teacher. Blocking it would make the button meaningless."""
    assignment = _assignment(db, "lw-returned")
    _existing(db, assignment, status="returned", grade=40)

    response = student_client.post(
        SUBMIT.format(assignment.id),
        json={"content": "Исправил", "declaration": {"ai_use": "none", "statement": "Я написал эту работу сам."}},
    )

    assert response.status_code == 201, response.text


def test_unmarked_work_may_still_be_replaced(student_client, db: Session, teacher, student) -> None:
    """Changing your mind before anybody has read it is not a second attempt."""
    assignment = _assignment(db, "lw-unmarked")
    _existing(db, assignment, status="submitted", grade=None)

    response = student_client.post(
        SUBMIT.format(assignment.id),
        json={"content": "Передумал", "declaration": {"ai_use": "none", "statement": "Я написал эту работу сам."}},
    )

    assert response.status_code == 201, response.text


def test_a_first_submission_is_untouched(student_client, db: Session, teacher, student) -> None:
    assignment = _assignment(db, "lw-first")
    db.commit()

    assert (
        student_client.post(
            SUBMIT.format(assignment.id),
            json={"content": "Сдаю", "declaration": {"ai_use": "none", "statement": "Я написал эту работу сам."}},
        ).status_code
        == 201
    )


def test_one_students_grade_does_not_block_another(student_client, db: Session, teacher, student) -> None:
    """The check is per student, and getting that wrong would lock a whole
    cohort out of an assignment the moment one person was marked."""
    from app.models.user import User

    assignment = _assignment(db, "lw-other")
    other = User(id=uuid.uuid4(), email="other-student@example.com", full_name="Другой", role="student")
    db.add(other)
    db.flush()
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=other.id,
            status="graded",
            grade=95,
            content="Чужая работа",
        )
    )
    db.commit()

    assert (
        student_client.post(
            SUBMIT.format(assignment.id),
            json={"content": "Моя", "declaration": {"ai_use": "none", "statement": "Я написал эту работу сам."}},
        ).status_code
        == 201
    )


def test_the_check_is_per_assignment(student_client, db: Session, teacher, student) -> None:
    """A marked essay in week one must not close week two."""
    first = _assignment(db, "lw-a1")
    second = Assignment(id=uuid.uuid4(), chapter_id=first.chapter_id, max_score=100)
    db.add(second)
    _existing(db, first, status="graded", grade=88)

    assert (
        student_client.post(
            SUBMIT.format(second.id),
            json={
                "content": "Вторая работа",
                "declaration": {"ai_use": "none", "statement": "Я написал эту работу сам."},
            },
        ).status_code
        == 201
    )
