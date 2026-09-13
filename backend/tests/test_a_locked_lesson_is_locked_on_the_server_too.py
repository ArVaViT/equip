"""``chapters.is_locked`` as a rule rather than a drawing.

Found on 2026-09-12, the day the first real course went out to real
students. Three of its four lessons were empty placeholders the teacher
had locked, and all three stood open: the web app decided the lock on
its own, and the API never asked.

Two failures, one flag.

The web app's rule only shut a lesson whose predecessor could be
*completed* — a quiz, an exam, an assignment. Lesson 1 was a reading,
so lessons 2 to 4 drew as open. That half lives in the frontend tests.

And underneath it, nothing at all: ``GET /blocks/chapter/{id}`` served
the lesson to anyone enrolled, so even a correct drawing was one typed
URL away from meaningless. That half is here.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from app.api.dependencies import verify_chapter_access
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course
from app.models.enrollment import Enrollment
from tests.conftest import ADMIN_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User

COURSE_ID = "preaching-lock"


@pytest.fixture()
def course(db: Session, teacher: User) -> Course:
    row = Course(
        id=COURSE_ID,
        status="published",
        access_mode="public",
        created_by=teacher.id,
        source_locale="ru",
    )
    db.add(row)
    db.commit()
    return row


def _chapter(db: Session, *, order: int, locked: bool, kind: str = "reading") -> Chapter:
    row = Chapter(
        id=str(uuid.uuid4()),
        course_id=COURSE_ID,
        title=f"Lesson {order + 1}",
        order_index=order,
        chapter_type=kind,
        is_locked=locked,
    )
    db.add(row)
    db.commit()
    return row


def _enrol(db: Session, student: User) -> None:
    db.add(Enrollment(id=str(uuid.uuid4()), user_id=student.id, course_id=COURSE_ID))
    db.commit()


def _finish(db: Session, student: User, chapter: Chapter) -> None:
    db.add(ChapterProgress(user_id=student.id, chapter_id=chapter.id, completed=True))
    db.commit()


class TestTheLockAStudentCannotOpen:
    def test_an_empty_lesson_behind_a_reading_is_refused(self, db: Session, course: Course, student: User) -> None:
        """The exact shape of the course that shipped."""
        _chapter(db, order=0, locked=False)
        shut = _chapter(db, order=1, locked=True)
        _enrol(db, student)

        with pytest.raises(HTTPException) as refusal:
            verify_chapter_access(db, shut.id, student)

        assert refusal.value.status_code == 403

    def test_the_first_lesson_can_be_the_locked_one(self, db: Session, course: Course, student: User) -> None:
        shut = _chapter(db, order=0, locked=True)
        _enrol(db, student)

        with pytest.raises(HTTPException) as refusal:
            verify_chapter_access(db, shut.id, student)

        assert refusal.value.status_code == 403

    def test_reading_the_lesson_before_it_does_not_open_it(self, db: Session, course: Course, student: User) -> None:
        """A reading carries no completion, so it opens nothing.

        Marking a reading read is a private bookmark. If it opened
        gates, every lock in the product would be one click deep.
        """
        first = _chapter(db, order=0, locked=False)
        shut = _chapter(db, order=1, locked=True)
        _enrol(db, student)
        _finish(db, student, first)

        with pytest.raises(HTTPException) as refusal:
            verify_chapter_access(db, shut.id, student)

        assert refusal.value.status_code == 403


class TestTheLockAStudentCanOpen:
    def test_an_unfinished_quiz_holds_the_next_lesson_shut(self, db: Session, course: Course, student: User) -> None:
        _chapter(db, order=0, locked=False, kind="quiz")
        shut = _chapter(db, order=1, locked=True)
        _enrol(db, student)

        with pytest.raises(HTTPException) as refusal:
            verify_chapter_access(db, shut.id, student)

        assert refusal.value.status_code == 403

    def test_passing_it_opens_the_next_lesson(self, db: Session, course: Course, student: User) -> None:
        quiz = _chapter(db, order=0, locked=False, kind="quiz")
        shut = _chapter(db, order=1, locked=True)
        _enrol(db, student)
        _finish(db, student, quiz)

        assert verify_chapter_access(db, shut.id, student).id == shut.id

    def test_one_student_finishing_does_not_open_it_for_another(
        self, db: Session, course: Course, student: User, admin: User
    ) -> None:
        """Progress is per person, and the query had better say so."""
        quiz = _chapter(db, order=0, locked=False, kind="quiz")
        shut = _chapter(db, order=1, locked=True)
        _enrol(db, student)
        db.add(ChapterProgress(user_id=ADMIN_ID, chapter_id=quiz.id, completed=True))
        db.commit()

        with pytest.raises(HTTPException) as refusal:
            verify_chapter_access(db, shut.id, student)

        assert refusal.value.status_code == 403


class TestWhoIsNotGated:
    def test_an_open_lesson_stays_open(self, db: Session, course: Course, student: User) -> None:
        open_one = _chapter(db, order=0, locked=False)
        _enrol(db, student)

        assert verify_chapter_access(db, open_one.id, student).id == open_one.id

    def test_the_teacher_reads_their_own_locked_lesson(self, db: Session, course: Course, teacher: User) -> None:
        """Otherwise a teacher could not write the lesson they locked."""
        shut = _chapter(db, order=0, locked=True)

        assert verify_chapter_access(db, shut.id, teacher).id == shut.id

    def test_an_admin_reads_it_too(self, db: Session, course: Course, admin: User) -> None:
        shut = _chapter(db, order=0, locked=True)

        assert verify_chapter_access(db, shut.id, admin).id == shut.id
