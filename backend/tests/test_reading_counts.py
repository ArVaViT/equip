"""A student saying they have read a chapter.

Reading is the core act of this product and, until now, the one act it did not
record. A quiz completes its chapter by being taken; an assignment by being
submitted. A reading chapter had no way to be finished at all — by anybody
except a teacher marking it on the student's behalf.

The endpoint is deliberately explicit rather than inferred from scrolling. A
scroll heuristic guesses wrongly in both directions: the skimmer who reaches
the bottom is credited, the careful reader on a phone who closes the tab is
not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID

URL = "/api/v1/progress/chapter/{}/read"


def _chapter(db: Session, course_id: str, *, kind: str = "reading", enrol: bool = True):
    course = Course(id=course_id, status="published", created_by=TEACHER_ID)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    if enrol:
        db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.flush()
    chapter = Chapter(id=f"{course_id}-ch", module_id=module.id, order_index=0, chapter_type=kind, title="Глава")
    db.add(chapter)
    db.commit()
    return chapter


def _progress(db: Session, chapter_id: str) -> ChapterProgress | None:
    return (
        db.query(ChapterProgress)
        .filter(ChapterProgress.user_id == STUDENT_ID, ChapterProgress.chapter_id == chapter_id)
        .first()
    )


def test_a_student_can_say_they_read_it(student_client, db: Session, teacher, student) -> None:
    chapter = _chapter(db, "read-basic")

    response = student_client.put(URL.format(chapter.id))

    assert response.status_code == 200, response.text
    saved = _progress(db, chapter.id)
    assert saved is not None and saved.completed is True


def test_the_record_says_the_student_decided(student_client, db: Session, teacher, student) -> None:
    """A chapter a teacher ticked and one a student read are different facts,
    and the progress board already distinguishes them."""
    chapter = _chapter(db, "read-who")

    student_client.put(URL.format(chapter.id))

    assert _progress(db, chapter.id).completion_type == "self"


def test_saying_it_twice_does_not_move_the_date(student_client, db: Session, teacher, student) -> None:
    """Pressing it again is the same statement made twice. Overwriting would
    rewrite when the chapter was first read."""
    chapter = _chapter(db, "read-twice")
    student_client.put(URL.format(chapter.id))
    first = _progress(db, chapter.id).completed_at

    student_client.put(URL.format(chapter.id))

    assert _progress(db, chapter.id).completed_at == first


def test_a_quiz_cannot_be_declared_read(student_client, db: Session, teacher, student) -> None:
    """A quiz is finished by taking it. Letting a student mark it read would be
    a way around the work — and, once reading counts toward progress, a way
    around the certificate gate."""
    chapter = _chapter(db, "read-quiz", kind="quiz")

    response = student_client.put(URL.format(chapter.id))

    assert response.status_code == 400
    assert _progress(db, chapter.id) is None


def test_an_assignment_cannot_be_declared_read(student_client, db: Session, teacher, student) -> None:
    chapter = _chapter(db, "read-asg", kind="assignment")

    assert student_client.put(URL.format(chapter.id)).status_code == 400


def test_somebody_not_enrolled_cannot_mark_anything(student_client, db: Session, teacher, student) -> None:
    chapter = _chapter(db, "read-outsider", enrol=False)

    assert student_client.put(URL.format(chapter.id)).status_code == 403
    assert _progress(db, chapter.id) is None


def test_a_chapter_that_does_not_exist_is_a_404(student_client, db: Session, teacher, student) -> None:
    assert student_client.put(URL.format("no-such-chapter")).status_code == 404
