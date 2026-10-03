"""The gradebook matrix says who is excused from a piece of work.

The "write to those who…" list read excusal off ``completed_by``, but an
exemption granted after a teacher had ticked the chapter leaves the tick as
it was. The matrix now carries ``excused`` from the exemptions themselves.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.assignment import Assignment
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Module
from app.models.enrollment import Enrollment
from app.models.grade_exemption import GradeExemption
from tests._cv_helpers import make_course_with_text
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User


def test_excused_after_a_teachers_tick_is_still_excused(client: TestClient, db: Session, student: User) -> None:
    course = make_course_with_text(db, title="Acts", status="published", created_by=TEACHER_ID)
    module = Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0)
    essay = Chapter(
        id=f"a-{course.id}",
        course_id=course.id,
        module_id=module.id,
        title="A",
        order_index=0,
        chapter_type="assignment",
    )
    other = Chapter(
        id=f"b-{course.id}",
        course_id=course.id,
        module_id=module.id,
        title="B",
        order_index=1,
        chapter_type="assignment",
    )
    db.add_all([module, essay, other])
    db.flush()
    work = Assignment(id=uuid.uuid4(), chapter_id=essay.id, max_score=10)
    db.add_all([work, Assignment(id=uuid.uuid4(), chapter_id=other.id, max_score=10)])
    db.add(Enrollment(id=str(uuid.uuid4()), user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.add(ChapterProgress(user_id=STUDENT_ID, chapter_id=essay.id, completed=True, completion_type="teacher"))
    db.add(
        GradeExemption(
            student_id=STUDENT_ID, course_id=course.id, item_type="assignment", item_id=work.id, chapter_id=essay.id
        )
    )
    db.commit()

    r = client.get(f"/api/v1/progress/course/{course.id}/gradebook")
    assert r.status_code == 200, r.text
    [me] = [s for s in r.json()["students"] if s["id"] == str(STUDENT_ID)]
    by_id = {c["id"]: c for c in me["chapters"]}
    assert by_id[essay.id]["completed_by"] == "teacher"
    assert by_id[essay.id]["excused"] is True
    assert by_id[other.id]["excused"] is False


def test_a_chapter_is_excused_only_when_all_its_work_is(client: TestClient, db: Session, student: User) -> None:
    from app.models.quiz import Quiz

    course = make_course_with_text(db, title="Acts", status="published", created_by=TEACHER_ID)
    module = Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0)
    both = Chapter(
        id=f"q-{course.id}", course_id=course.id, module_id=module.id, title="Q", order_index=0, chapter_type="quiz"
    )
    db.add_all([module, both])
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=both.id)
    essay = Assignment(id=uuid.uuid4(), chapter_id=both.id, max_score=10)
    db.add_all([quiz, essay])
    db.add(Enrollment(id=str(uuid.uuid4()), user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.add(
        GradeExemption(
            student_id=STUDENT_ID, course_id=course.id, item_type="quiz", item_id=quiz.id, chapter_id=both.id
        )
    )
    db.commit()

    def excused() -> bool:
        me = next(s for s in client.get(f"/api/v1/progress/course/{course.id}/gradebook").json()["students"])
        return next(c for c in me["chapters"] if c["id"] == both.id)["excused"]

    assert excused() is False  # the essay is still owed
    db.add(
        GradeExemption(
            student_id=STUDENT_ID, course_id=course.id, item_type="assignment", item_id=essay.id, chapter_id=both.id
        )
    )
    db.commit()
    assert excused() is True
