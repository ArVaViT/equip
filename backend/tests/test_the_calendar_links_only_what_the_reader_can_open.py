"""A deadline in a locked lesson stays on the calendar, without a door.

On 2026-10-25 a student pressed «Open the assignment» on their calendar
and got the lesson's 403 twice: the lesson was locked by the teacher,
and the calendar knew which lessons were released, not which were open
to this reader. The date is real, so it stays; the link goes only to a
lesson the reader can open — by the same rule ``GET /blocks/chapter``
applies (``chapter_gate``). The course's owner is not gated.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.assignment import Assignment
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.services.calendar_service import build_calendar_events
from app.services.content_versions.write import record_human_version
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


def _course(db: Session) -> tuple[str, str]:
    cid = f"live-{uuid.uuid4().hex[:6]}"
    db.add(Course(id=cid, status="published", source_locale="ru", created_by=TEACHER_ID, access_mode="public"))
    module = Module(id=f"mod-{cid}", course_id=cid, order_index=0)
    db.add(module)
    db.flush()
    record_human_version(db, entity_type="course", entity_id=cid, field="title", locale="ru", text="Деяния")
    db.add(Enrollment(id=f"enr-{cid}", user_id=STUDENT_ID, course_id=cid, progress=0))
    db.commit()
    return cid, module.id


def _chapter(db: Session, cid: str, mid: str, *, order_index: int, chapter_type: str, locked: bool = False) -> str:
    chapter = Chapter(
        id=f"ch-{uuid.uuid4().hex[:6]}",
        course_id=cid,
        module_id=mid,
        title="Урок",
        order_index=order_index,
        chapter_type=chapter_type,
        is_locked=locked,
    )
    db.add(chapter)
    db.flush()
    record_human_version(db, entity_type="chapter", entity_id=chapter.id, field="title", locale="ru", text="Урок")
    db.commit()
    return chapter.id


def _assignment_in(db: Session, chapter_id: str) -> None:
    db.add(
        Assignment(
            id=uuid.uuid4(), chapter_id=chapter_id, max_score=100, due_date=datetime.now(UTC) + timedelta(days=7)
        )
    )
    db.commit()


def _deadline(db: Session, user: User, cid: str):
    (event,) = [
        e
        for e in build_calendar_events(db, user=user, course_id=cid, display_locale="ru")
        if e.source == "assignment_deadline"
    ]
    return event


def test_a_lesson_the_teacher_locked_keeps_its_date_and_loses_its_link(
    db: Session, teacher: User, student: User
) -> None:
    cid, mid = _course(db)
    _chapter(db, cid, mid, order_index=0, chapter_type="reading")
    locked = _chapter(db, cid, mid, order_index=1, chapter_type="assignment", locked=True)
    _assignment_in(db, locked)

    event = _deadline(db, student, cid)

    assert event.chapter_id is None


def test_the_teacher_still_gets_the_link(db: Session, teacher: User, student: User) -> None:
    cid, mid = _course(db)
    _chapter(db, cid, mid, order_index=0, chapter_type="reading")
    locked = _chapter(db, cid, mid, order_index=1, chapter_type="assignment", locked=True)
    _assignment_in(db, locked)

    assert _deadline(db, teacher, cid).chapter_id == locked


def test_the_link_appears_once_the_student_has_earned_the_lesson(db: Session, teacher: User, student: User) -> None:
    cid, mid = _course(db)
    quiz = _chapter(db, cid, mid, order_index=0, chapter_type="quiz")
    locked = _chapter(db, cid, mid, order_index=1, chapter_type="assignment", locked=True)
    _assignment_in(db, locked)
    assert _deadline(db, student, cid).chapter_id is None

    db.add(ChapterProgress(id=uuid.uuid4(), user_id=STUDENT_ID, chapter_id=quiz, completed=True))
    db.commit()

    assert _deadline(db, student, cid).chapter_id == locked


def test_an_open_lesson_keeps_its_link(db: Session, teacher: User, student: User) -> None:
    cid, mid = _course(db)
    open_lesson = _chapter(db, cid, mid, order_index=0, chapter_type="assignment")
    _assignment_in(db, open_lesson)

    assert _deadline(db, student, cid).chapter_id == open_lesson
