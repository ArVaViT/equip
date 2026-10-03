"""A chapter held for its first release does not exist for students — anywhere.

The first pass of this rule (``staged_edits.visibility``, 2026-10-03) took
a held chapter out of the student's tree and out of the progress
denominators. Review found the places it still showed through: a student
with the URL could still open the lesson, mark it read, and sit the quiz
in it — an attempt that would count the moment the quiz was released; the
pass/fail attestation (зачёт) still owed the student a quiz nobody could
take; the calendar listed its assignment's deadline; the catalog card, the
invitation letter and the student's PDF export counted or printed it.

One rule, now everywhere a student meets a chapter: held means not yet
there. The owner and an admin are unaffected throughout.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from app.api.consent_gate import consent_subject
from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.assignment import Assignment
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAttempt, QuizQuestion
from app.services.calendar_service import build_calendar_events
from app.services.certificate_readiness import QUIZZES_NOT_PASSED, certificate_blockers
from app.services.content_versions.write import record_human_version
from app.services.course_service._queries import attach_counts
from app.services.email.invitation import _lesson_count
from app.services.staged_edits import stage_human_edit
from app.services.zachet import assignments_in_course, course_quiz_rows, unpassed_quizzes
from tests._cv_helpers import make_quiz_question_with_text, make_quiz_with_text
from tests._pdf_text import pdf_lines
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from app.models.user import User

API = "/api/v1"


@pytest.fixture
def c(db: Session) -> Iterator[TestClient]:
    def _db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _as(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_user] = lambda: user
    app.dependency_overrides[consent_subject] = lambda: user


def _live_course(db: Session, *, scheme: str = "letter") -> tuple[Course, str, str]:
    """A published Russian course, one module, one released lesson, the
    student enrolled. Returns ``(course, module_id, chapter_id)``."""
    cid = f"live-{uuid.uuid4().hex[:6]}"
    course = Course(
        id=cid,
        status="published",
        source_locale="ru",
        created_by=TEACHER_ID,
        access_mode="public",
        grading_scheme=scheme,
    )
    module = Module(id=f"mod-{cid}", course_id=cid, order_index=0)
    db.add_all([course, module])
    db.flush()
    record_human_version(db, entity_type="course", entity_id=cid, field="title", locale="ru", text="Деяния")
    record_human_version(db, entity_type="module", entity_id=module.id, field="title", locale="ru", text="Начало")
    chapter_id = _chapter(db, cid, module.id, title="Пятидесятница", order_index=0, held=False)
    db.add(Enrollment(id=f"enr-{cid}", user_id=STUDENT_ID, course_id=cid, progress=100))
    db.commit()
    return course, module.id, chapter_id


def _chapter(
    db: Session,
    course_id: str,
    module_id: str,
    *,
    title: str,
    order_index: int,
    held: bool,
    chapter_type: str = "reading",
) -> str:
    """A chapter whose title is released — or, as ``create_chapter`` leaves it
    on a published course, held in the staging table."""
    chapter = Chapter(
        id=f"ch-{uuid.uuid4().hex[:6]}",
        course_id=course_id,
        module_id=module_id,
        title=title,
        order_index=order_index,
        chapter_type=chapter_type,
    )
    db.add(chapter)
    db.flush()
    if held:
        stage_human_edit(
            db,
            entity_type="chapter",
            entity_id=chapter.id,
            course_id=course_id,
            field="title",
            locale="ru",
            text=title,
        )
    else:
        record_human_version(db, entity_type="chapter", entity_id=chapter.id, field="title", locale="ru", text=title)
    db.commit()
    return chapter.id


def _quiz(db: Session, chapter_id: str, *, title: str) -> Quiz:
    quiz = make_quiz_with_text(db, chapter_id=chapter_id, title=title, locale="ru", passing_score=70)
    make_quiz_question_with_text(db, quiz_id=quiz.id, question_text="Кто?", locale="ru")
    db.commit()
    return quiz


def _passed(db: Session, quiz: Quiz) -> None:
    db.add(
        QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=STUDENT_ID,
            score=90,
            max_score=100,
            passed=True,
            completed_at=datetime.now(UTC),
        )
    )
    db.commit()


def _ok(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, f"{r.request.method} {r.request.url}: {r.text}"
    return r.json()


# ---------------------------------------------------------------------------
# Pass/fail attestation
# ---------------------------------------------------------------------------


def test_the_attestation_does_not_owe_the_student_a_held_quiz_or_essay(db: Session, teacher: User, student: User):
    course, mid, _reading = _live_course(db, scheme="pass_fail")
    passed_chapter = _chapter(db, course.id, mid, title="Тест 1", order_index=1, held=False, chapter_type="quiz")
    _passed(db, _quiz(db, passed_chapter, title="Тест 1"))
    held_quiz_chapter = _chapter(db, course.id, mid, title="Тест 2", order_index=2, held=True, chapter_type="quiz")
    _quiz(db, held_quiz_chapter, title="Тест 2")
    held_essay_chapter = _chapter(db, course.id, mid, title="Эссе", order_index=3, held=True, chapter_type="assignment")
    db.add(Assignment(id=uuid.uuid4(), chapter_id=held_essay_chapter, max_score=100))
    db.commit()

    assert [row.id for row in course_quiz_rows(db, course.id)] == [
        q.id for q in db.query(Quiz).filter(Quiz.chapter_id == passed_chapter)
    ]
    assert assignments_in_course(db, course.id) == []
    assert unpassed_quizzes(db, student_id=STUDENT_ID, course_id=course.id) == []

    enrollment = db.query(Enrollment).filter(Enrollment.course_id == course.id).one()
    blockers = certificate_blockers(db, course, enrollment, STUDENT_ID)
    # Зачёт: the one quiz they could take, they passed.
    assert QUIZZES_NOT_PASSED not in [b.code for b in blockers]
    assert blockers == []


# ---------------------------------------------------------------------------
# Reaching it by id
# ---------------------------------------------------------------------------


def test_a_student_cannot_reach_a_held_chapter_by_its_id(c: TestClient, db: Session, teacher: User, student: User):
    course, mid, _reading = _live_course(db)
    held = _chapter(db, course.id, mid, title="Тест 2", order_index=2, held=True, chapter_type="quiz")
    quiz = _quiz(db, held, title="Тест 2")
    held_lesson = _chapter(db, course.id, mid, title="Новый урок", order_index=3, held=True)

    _as(student)
    assert c.get(f"{API}/blocks/chapter/{held}").status_code == 404
    assert c.get(f"{API}/quizzes/chapter/{held}").status_code == 404
    assert c.put(f"{API}/progress/chapter/{held_lesson}/read").status_code == 404
    # The quiz behind it, too: an attempt here would count on release.
    question = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).one()
    submit = c.post(
        f"{API}/quizzes/{quiz.id}/submit",
        json={"answers": [{"question_id": str(question.id), "text_answer": "Пётр"}]},
    )
    assert submit.status_code == 404, submit.text
    assert db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).count() == 0

    # The owner reaches all of it, as in the editor.
    _as(teacher)
    assert c.get(f"{API}/blocks/chapter/{held}").status_code == 200
    assert c.put(f"{API}/progress/chapter/{held_lesson}/read").status_code == 200


# ---------------------------------------------------------------------------
# Calendar, counts, export
# ---------------------------------------------------------------------------


def test_a_deadline_in_a_held_chapter_is_not_on_the_calendar(db: Session, teacher: User, student: User):
    course, mid, _reading = _live_course(db)
    due = datetime.now(UTC) + timedelta(days=7)
    shown = _chapter(db, course.id, mid, title="Эссе 1", order_index=1, held=False, chapter_type="assignment")
    db.add(Assignment(id=uuid.uuid4(), chapter_id=shown, max_score=100, due_date=due))
    held = _chapter(db, course.id, mid, title="Эссе 2", order_index=2, held=True, chapter_type="assignment")
    db.add(Assignment(id=uuid.uuid4(), chapter_id=held, max_score=100, due_date=due))
    db.commit()

    events = build_calendar_events(db, user=student, course_id=course.id, display_locale="ru")

    assert [e.source for e in events] == ["assignment_deadline"]


def test_the_catalog_card_and_the_invitation_count_only_the_lessons_there_are(
    db: Session, teacher: User, student: User
):
    course, mid, _reading = _live_course(db)
    _chapter(db, course.id, mid, title="Новый урок", order_index=1, held=True)

    attach_counts(db, [course])

    assert course.chapter_count == 1  # type: ignore[attr-defined]
    assert _lesson_count(db, course.id) == 1


def test_the_students_export_leaves_the_held_lesson_out(c: TestClient, db: Session, teacher: User, student: User):
    # Latin titles: the PDF text extractor in the tests reads glyph ids
    # back for the embedded Cyrillic font, so Cyrillic cannot be asserted on.
    course, mid, _reading = _live_course(db)
    shown = _chapter(db, course.id, mid, title="Pentecost", order_index=1, held=False)
    _chapter(db, course.id, mid, title="Jerusalem Council", order_index=2, held=True)
    db.expire_all()
    assert shown

    _as(student)
    student_text = "\n".join(pdf_lines(c.get(f"{API}/courses/{course.id}/export.pdf").content))
    assert "Pentecost" in student_text
    assert "Jerusalem Council" not in student_text

    # The owner prints the course as it will be.
    _as(teacher)
    owner_text = "\n".join(pdf_lines(c.get(f"{API}/courses/{course.id}/export.pdf").content))
    assert "Jerusalem Council" in owner_text
