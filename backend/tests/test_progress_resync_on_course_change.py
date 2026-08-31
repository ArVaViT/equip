"""The percentage is a fraction of the course, so the course changing moves it.

`sync_enrollment_progress` runs when one student's pass-state flips. Nothing
ran when the *course* changed shape — and deleting a quiz, adding one, or
changing a chapter's type moves the denominator for everybody at once.

Seen on production 2026-08-31: four enrolments stored 100% while the teacher's
board counted "0/5 chapters" in the same row. Those students had passed a quiz
that was deleted afterwards, and nothing ever revisited the number.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.schemas.course import ChapterCreate, ChapterUpdate
from app.services.course_service import (
    create_chapter,
    delete_chapter,
    delete_module,
    resync_course_progress,
    update_chapter,
)
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User

COURSE_ID = "c-resync"
MODULE_ID = "m-resync"


def _seed(db: Session, *, quizzes: int = 2, readings: int = 1) -> None:
    db.add(Course(id=COURSE_ID, title="Course", created_by=TEACHER_ID, status="published", source_locale="ru"))
    db.add(Module(id=MODULE_ID, course_id=COURSE_ID, title="Module", order_index=0))
    for i in range(quizzes):
        db.add(
            Chapter(
                id=f"{COURSE_ID}-quiz-{i}",
                module_id=MODULE_ID,
                title=f"Quiz {i}",
                order_index=i,
                chapter_type="quiz",
            )
        )
    for i in range(readings):
        db.add(
            Chapter(
                id=f"{COURSE_ID}-read-{i}",
                module_id=MODULE_ID,
                title=f"Lesson {i}",
                order_index=quizzes + i,
                chapter_type="reading",
            )
        )
    db.add(Enrollment(id="enr-resync", user_id=STUDENT_ID, course_id=COURSE_ID, progress=0))
    db.commit()


def _pass(db: Session, chapter_id: str) -> None:
    db.add(ChapterProgress(id=uuid.uuid4(), user_id=STUDENT_ID, chapter_id=chapter_id, completed=True))
    db.commit()


def _progress(db: Session) -> int:
    row = db.query(Enrollment).filter(Enrollment.id == "enr-resync").first()
    assert row is not None
    db.refresh(row)
    return row.progress


def test_deleting_the_quiz_somebody_passed_does_not_leave_them_at_100(db: Session, teacher: User, student: User):
    _seed(db, quizzes=1)
    _pass(db, f"{COURSE_ID}-quiz-0")
    resync_course_progress(db, COURSE_ID)
    assert _progress(db) == 100

    chapter = db.query(Chapter).filter(Chapter.id == f"{COURSE_ID}-quiz-0").first()
    assert chapter is not None
    delete_chapter(db, chapter)

    # Nothing gradable is left, so there is nothing to have finished. The old
    # behaviour left this at 100 — the exact shape of the production rows.
    assert _progress(db) == 0


def test_adding_a_quiz_dilutes_everybody_already_enrolled(db: Session, teacher: User, student: User):
    _seed(db, quizzes=1)
    _pass(db, f"{COURSE_ID}-quiz-0")
    resync_course_progress(db, COURSE_ID)
    assert _progress(db) == 100

    create_chapter(
        db,
        MODULE_ID,
        ChapterCreate(title="Quiz 2", chapter_type="quiz", order_index=5),
    )

    assert _progress(db) == 50


def test_adding_a_reading_chapter_changes_nothing(db: Session, teacher: User, student: User):
    _seed(db, quizzes=2)
    _pass(db, f"{COURSE_ID}-quiz-0")
    resync_course_progress(db, COURSE_ID)
    assert _progress(db) == 50

    create_chapter(
        db,
        MODULE_ID,
        ChapterCreate(title="Lesson", chapter_type="reading", order_index=9),
    )

    # Reading is not in the fraction — see the note in
    # ``frontend/src/pages/Course/moduleProgress.ts``.
    assert _progress(db) == 50


def test_turning_a_lesson_into_a_quiz_moves_the_denominator(db: Session, teacher: User, student: User):
    _seed(db, quizzes=1, readings=1)
    _pass(db, f"{COURSE_ID}-quiz-0")
    resync_course_progress(db, COURSE_ID)
    assert _progress(db) == 100

    lesson = db.query(Chapter).filter(Chapter.id == f"{COURSE_ID}-read-0").first()
    assert lesson is not None
    update_chapter(db, lesson, ChapterUpdate(chapter_type="quiz"))

    assert _progress(db) == 50


def test_deleting_the_module_takes_its_quizzes_out_of_the_fraction(db: Session, teacher: User, student: User):
    _seed(db, quizzes=2)
    _pass(db, f"{COURSE_ID}-quiz-0")
    resync_course_progress(db, COURSE_ID)
    assert _progress(db) == 50

    module = db.query(Module).filter(Module.id == MODULE_ID).first()
    assert module is not None
    delete_module(db, module)

    assert _progress(db) == 0


def test_a_course_with_nothing_gradable_is_zero_not_a_crash(db: Session, teacher: User, student: User):
    _seed(db, quizzes=0, readings=2)
    assert resync_course_progress(db, COURSE_ID) == 1
    assert _progress(db) == 0
