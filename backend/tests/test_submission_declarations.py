"""What a student says about their own work, at the moment they hand it in.

Nothing here detects anything, and that is the design rather than a gap: AI
detectors false-positive on writers whose English is a second language — most
of this school — so a platform that renders «87% AI» has manufactured an
accusation it cannot support against the students least able to argue back.

The rule the tests exist to protect is the uncomfortable one. A student who
declares they used AI where the course forbids it is telling the truth about a
rule they broke. The work is accepted, the declaration recorded, and a person
handles it — because refusing at the door teaches the next student to tick the
other box, and a declaration nobody makes honestly is worth nothing.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.assignment import Assignment
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.submission_declaration import SubmissionDeclaration

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

SUBMIT = "/api/v1/assignments/{}/submit"

STATEMENT = "Я написал эту работу сам. ИИ не использовал."


def _assignment(db: Session, course_id: str, *, policy: str = "ai_with_disclosure"):
    course = Course(id=course_id, status="published", created_by=TEACHER_ID, ai_policy=policy)
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
    db.commit()
    return assignment


def _declaration(db: Session) -> SubmissionDeclaration | None:
    return db.query(SubmissionDeclaration).first()


def test_what_the_student_said_is_stored_with_the_work(student_client, db: Session, teacher, student) -> None:
    assignment = _assignment(db, "dec-basic")

    response = student_client.post(
        SUBMIT.format(assignment.id),
        json={"content": "Работа", "declaration": {"ai_use": "none", "statement": STATEMENT}},
    )

    assert response.status_code == 201, response.text
    saved = _declaration(db)
    assert saved is not None
    assert saved.ai_use == "none"
    assert saved.policy == "ai_with_disclosure"


def test_the_text_stored_is_the_text_shown(student_client, db: Session, teacher, student) -> None:
    """Not a key into a catalogue somebody can edit next month. Same principle
    as the ведомость and the certificate: what a person agreed to has to
    survive the thing they agreed to being changed."""
    assignment = _assignment(db, "dec-text")

    student_client.post(
        SUBMIT.format(assignment.id),
        json={"content": "Работа", "declaration": {"ai_use": "none", "statement": STATEMENT}},
    )

    assert _declaration(db).statement == STATEMENT


def test_a_disclosed_use_is_recorded_with_the_students_own_sentence(
    student_client, db: Session, teacher, student
) -> None:
    """That sentence, sitting next to the essay, tells a teacher more than any
    detector would."""
    assignment = _assignment(db, "dec-disclosed")

    student_client.post(
        SUBMIT.format(assignment.id),
        json={
            "content": "Работа",
            "declaration": {
                "ai_use": "assisted",
                "statement": "Я использовал ИИ и указываю, где именно.",
                "note": "Просил перефразировать два абзаца во введении.",
            },
        },
    )

    saved = _declaration(db)
    assert saved.ai_use == "assisted"
    assert "перефразировать" in saved.statement


def test_honesty_under_a_ban_is_recorded_not_refused(student_client, db: Session, teacher, student) -> None:
    """The uncomfortable case, and the one the design turns on. Refusing the
    work here would teach the next student to tick the other box — and a
    declaration nobody makes honestly is worth nothing at all."""
    assignment = _assignment(db, "dec-breach", policy="ai_forbidden")

    response = student_client.post(
        SUBMIT.format(assignment.id),
        json={
            "content": "Работа",
            "declaration": {"ai_use": "assisted", "statement": "ИИ на этом курсе нельзя, но я использовал."},
        },
    )

    assert response.status_code == 201, "the work is accepted"
    saved = _declaration(db)
    assert saved.ai_use == "assisted"
    assert saved.policy == "ai_forbidden", "and the teacher can see it was declared against a ban"


def test_a_course_that_asks_nothing_stores_nothing(student_client, db: Session, teacher, student) -> None:
    """`ai_open` has nothing to declare, and inventing a statement for a
    student who was never shown one would put words in their mouth."""
    assignment = _assignment(db, "dec-open", policy="ai_open")

    response = student_client.post(SUBMIT.format(assignment.id), json={"content": "Работа"})

    assert response.status_code == 201
    assert _declaration(db) is None


def test_the_policy_is_frozen_onto_the_declaration(student_client, db: Session, teacher, student) -> None:
    """A teacher tightening the course policy next month must not rewrite what
    a student was asked last month."""
    assignment = _assignment(db, "dec-frozen", policy="ai_with_disclosure")
    student_client.post(
        SUBMIT.format(assignment.id),
        json={"content": "Работа", "declaration": {"ai_use": "none", "statement": STATEMENT}},
    )

    course = db.query(Course).filter(Course.id == "dec-frozen").one()
    course.ai_policy = "ai_forbidden"
    db.commit()

    assert _declaration(db).policy == "ai_with_disclosure"


def test_the_default_policy_is_disclosure_not_a_ban(db: Session, teacher) -> None:
    """A ban nobody can enforce is broken silently, and it teaches students to
    conceal rather than to say. The strict setting stays available per course."""
    course = Course(id="dec-default", status="published", created_by=TEACHER_ID)
    db.add(course)
    db.commit()
    db.refresh(course)

    assert course.ai_policy == "ai_with_disclosure"
