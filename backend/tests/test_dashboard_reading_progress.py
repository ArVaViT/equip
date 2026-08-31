"""The dashboard's second number: how much of the course has been read.

``enrollment.progress`` is assessment-only by design. The dashboard showed
nothing else, so a student who had read every lesson of a course and not yet
sat a quiz was told 0%. In production on 2026-08-24 and 2026-08-30 two people
completed a reading chapter each; both enrolment rows still read
``progress = 0``, and the dashboard was the only thing either of them saw.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.services.course_service import reading_progress_by_course
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


def _seed_course(db: Session, *, course_id: str, readings: int, quizzes: int) -> None:
    course = Course(
        id=course_id,
        title="Course",
        created_by=TEACHER_ID,
        status="published",
        source_locale="ru",
    )
    module = Module(id=f"mod-{course_id}", course_id=course_id, title="Module", order_index=0)
    db.add_all([course, module])
    for i in range(readings):
        db.add(
            Chapter(
                id=f"{course_id}-read-{i}",
                module_id=module.id,
                title=f"Lesson {i}",
                order_index=i,
                chapter_type="reading",
            )
        )
    for i in range(quizzes):
        db.add(
            Chapter(
                id=f"{course_id}-quiz-{i}",
                module_id=module.id,
                title=f"Quiz {i}",
                order_index=readings + i,
                chapter_type="quiz",
            )
        )
    db.commit()


def _mark_read(db: Session, chapter_id: str, user_id: object = STUDENT_ID) -> None:
    db.add(
        ChapterProgress(
            id=uuid.uuid4(),
            user_id=user_id,
            chapter_id=chapter_id,
            completed=True,
        )
    )
    db.commit()


def test_counts_only_the_chapters_there_are_to_read(db: Session, teacher: User, student: User) -> None:
    _seed_course(db, course_id="c-read", readings=16, quizzes=5)

    read, to_read = reading_progress_by_course(db, STUDENT_ID, ["c-read"])["c-read"]

    # 16, not 21: the five quizzes belong to the percentage, not to this.
    assert (read, to_read) == (0, 16)


def test_a_read_chapter_shows_up(db: Session, teacher: User, student: User) -> None:
    _seed_course(db, course_id="c-read", readings=16, quizzes=5)
    _mark_read(db, "c-read-read-0")

    assert reading_progress_by_course(db, STUDENT_ID, ["c-read"])["c-read"] == (1, 16)


def test_another_students_reading_is_not_counted(db: Session, teacher: User, student: User) -> None:
    _seed_course(db, course_id="c-read", readings=4, quizzes=0)
    _mark_read(db, "c-read-read-0", user_id=TEACHER_ID)

    assert reading_progress_by_course(db, STUDENT_ID, ["c-read"]) == {"c-read": (0, 4)}


def test_one_query_covers_every_course_on_the_page(db: Session, teacher: User, student: User) -> None:
    _seed_course(db, course_id="c-one", readings=3, quizzes=1)
    _seed_course(db, course_id="c-two", readings=5, quizzes=0)
    _mark_read(db, "c-one-read-0")
    _mark_read(db, "c-two-read-1")

    result = reading_progress_by_course(db, STUDENT_ID, ["c-one", "c-two"])

    assert result == {"c-one": (1, 3), "c-two": (1, 5)}


def test_no_courses_asks_the_database_nothing(db: Session, teacher: User, student: User) -> None:
    assert reading_progress_by_course(db, STUDENT_ID, []) == {}


def test_the_dashboard_reports_reading_beside_the_percentage(
    db: Session, student_client, student, teacher: User
) -> None:
    _seed_course(db, course_id="c-read", readings=16, quizzes=5)
    db.add(Enrollment(id="enr-read", user_id=student.id, course_id="c-read", progress=0))
    db.commit()
    _mark_read(db, "c-read-read-0", user_id=student.id)
    _mark_read(db, "c-read-read-1", user_id=student.id)

    body = student_client.get("/api/v1/users/me/courses").json()

    row = next(r for r in body if r["course_id"] == "c-read")
    # The percentage stays honest about assessment...
    assert row["progress"] == 0
    # ...and the dashboard is no longer silent about the reading.
    assert (row["chapters_read"], row["chapters_to_read"]) == (2, 16)
