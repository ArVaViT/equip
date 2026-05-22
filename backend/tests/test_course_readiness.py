"""Course-readiness checklist — service and route coverage.

We exercise every rule by building a deliberately broken course, then
verify that ``compute_readiness`` flags the right checks and that the
``GET /courses/{id}/readiness`` route serializes the verdict for the
frontend. The route also has a permission test to confirm a non-owner
teacher can't read someone else's checklist.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session  # noqa: TC002  (used at runtime by fixtures)

from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.models.user import User
from app.services.course_readiness import (
    ReadinessReport,
    compute_readiness,
)

from .conftest import TEACHER_ID

# ─── Helpers ────────────────────────────────────────────────────────────


def _make_course(
    db: Session,
    *,
    title: str = "Course",
    description: str | None = None,
    image_url: str | None = None,
    access_mode: str = "public",
    enrollment_start=None,
    enrollment_end=None,
) -> Course:
    course = Course(
        id=str(uuid.uuid4()),
        title=title,
        description=description,
        image_url=image_url,
        status=CourseStatus.DRAFT,
        access_mode=access_mode,
        created_by=TEACHER_ID,
        enrollment_start=enrollment_start,
        enrollment_end=enrollment_end,
        source_locale="en",
    )
    db.add(course)
    db.flush()
    return course


def _add_module(db: Session, course: Course, *, title: str = "Module") -> Module:
    module = Module(id=str(uuid.uuid4()), course_id=course.id, title=title, order_index=0)
    db.add(module)
    db.flush()
    return module


def _add_chapter(
    db: Session,
    module: Module,
    *,
    title: str = "Chapter",
    chapter_type: str = "reading",
) -> Chapter:
    chapter = Chapter(
        id=str(uuid.uuid4()),
        module_id=module.id,
        title=title,
        chapter_type=chapter_type,
        order_index=0,
    )
    db.add(chapter)
    db.flush()
    return chapter


def _add_text_block(db: Session, chapter: Chapter, *, content: str = "Hello") -> ChapterBlock:
    block = ChapterBlock(chapter_id=chapter.id, block_type="text", order_index=0, content=content)
    db.add(block)
    db.flush()
    return block


def _add_quiz_with_question(
    db: Session,
    chapter: Chapter,
    *,
    qtype: str = "multiple_choice",
    options: int = 2,
    correct: int = 1,
) -> Quiz:
    quiz = Quiz(chapter_id=chapter.id, title="Quiz")
    db.add(quiz)
    db.flush()
    question = QuizQuestion(quiz_id=quiz.id, question_text="Q?", question_type=qtype, order_index=0)
    db.add(question)
    db.flush()
    for i in range(options):
        db.add(
            QuizOption(
                question_id=question.id,
                option_text=f"Option {i}",
                is_correct=(i < correct),
                order_index=i,
            )
        )
    db.flush()
    return quiz


def _add_assignment(db: Session, chapter: Chapter, *, description: str | None = None) -> Assignment:
    assignment = Assignment(chapter_id=chapter.id, title="Assignment", description=description)
    db.add(assignment)
    db.flush()
    return assignment


def _check(report: ReadinessReport, check_id_prefix: str):
    return next((c for c in report.checks if c.id.startswith(check_id_prefix)), None)


# ─── Service-level tests ────────────────────────────────────────────────


def test_empty_course_flags_critical_missing_module(db: Session, teacher: User):
    course = _make_course(db)
    report = compute_readiness(db, course)
    has_module_check = _check(report, "has_at_least_one_module")
    assert has_module_check is not None
    assert has_module_check.passed is False
    assert has_module_check.severity == "critical"
    assert report.critical_failing >= 1


def test_module_without_chapters_flags_critical(db: Session, teacher: User):
    course = _make_course(db)
    _add_module(db, course)
    report = compute_readiness(db, course)
    check = _check(report, "module_has_chapters:")
    assert check is not None
    assert check.passed is False
    assert check.severity == "critical"
    assert check.subject and check.subject.type == "module"


def test_reading_chapter_with_empty_block_fails(db: Session, teacher: User):
    course = _make_course(db)
    module = _add_module(db, course)
    chapter = _add_chapter(db, module, chapter_type="reading")
    _add_text_block(db, chapter, content="   ")  # whitespace-only counts as empty
    report = compute_readiness(db, course)
    check = _check(report, "reading_has_content:")
    assert check is not None
    assert check.passed is False
    assert check.action and check.action.type == "open_chapter"
    assert check.action.params == {
        "module_id": module.id,
        "chapter_id": chapter.id,
    }


def test_reading_chapter_with_non_empty_block_passes(db: Session, teacher: User):
    course = _make_course(db)
    module = _add_module(db, course)
    chapter = _add_chapter(db, module, chapter_type="reading")
    _add_text_block(db, chapter, content="Real content")
    report = compute_readiness(db, course)
    check = _check(report, "reading_has_content:")
    assert check is not None
    assert check.passed is True


def test_quiz_chapter_without_questions_fails(db: Session, teacher: User):
    course = _make_course(db)
    module = _add_module(db, course)
    _add_chapter(db, module, chapter_type="quiz")
    report = compute_readiness(db, course)
    has_question = _check(report, "quiz_has_question:")
    assert has_question is not None
    assert has_question.passed is False


def test_exam_chapter_uses_exam_message_key(db: Session, teacher: User):
    course = _make_course(db)
    module = _add_module(db, course)
    _add_chapter(db, module, chapter_type="exam")
    report = compute_readiness(db, course)
    has_question = _check(report, "quiz_has_question:")
    assert has_question is not None
    assert has_question.message_key == "courseReadiness.checks.examHasQuestion"


def test_quiz_with_multiple_choice_no_correct_fails_completeness(db: Session, teacher: User):
    course = _make_course(db)
    module = _add_module(db, course)
    chapter = _add_chapter(db, module, chapter_type="quiz")
    _add_quiz_with_question(db, chapter, qtype="multiple_choice", options=4, correct=0)
    report = compute_readiness(db, course)
    completeness = _check(report, "quiz_questions_complete:")
    assert completeness is not None
    assert completeness.passed is False


def test_quiz_with_true_false_one_correct_passes_completeness(db: Session, teacher: User):
    course = _make_course(db)
    module = _add_module(db, course)
    chapter = _add_chapter(db, module, chapter_type="quiz")
    _add_quiz_with_question(db, chapter, qtype="true_false", options=2, correct=1)
    report = compute_readiness(db, course)
    completeness = _check(report, "quiz_questions_complete:")
    assert completeness is not None
    assert completeness.passed is True


def test_assignment_chapter_without_brief_fails(db: Session, teacher: User):
    course = _make_course(db)
    module = _add_module(db, course)
    chapter = _add_chapter(db, module, chapter_type="assignment")
    _add_assignment(db, chapter, description=None)
    report = compute_readiness(db, course)
    check = _check(report, "assignment_has_brief:")
    assert check is not None
    assert check.passed is False


def test_assignment_chapter_with_brief_passes(db: Session, teacher: User):
    course = _make_course(db)
    module = _add_module(db, course)
    chapter = _add_chapter(db, module, chapter_type="assignment")
    _add_assignment(db, chapter, description="Write a 500-word reflection")
    report = compute_readiness(db, course)
    check = _check(report, "assignment_has_brief:")
    assert check is not None
    assert check.passed is True


def test_course_without_description_flags_recommended(db: Session, teacher: User):
    course = _make_course(db, description=None)
    report = compute_readiness(db, course)
    check = _check(report, "has_description")
    assert check is not None
    assert check.passed is False
    assert check.severity == "recommended"


def test_institute_course_skips_enrollment_window_check(db: Session, teacher: User):
    course = _make_course(db, access_mode="institute")
    report = compute_readiness(db, course)
    assert _check(report, "has_enrollment_window") is None


def test_public_course_with_no_window_flags(db: Session, teacher: User):
    course = _make_course(db, access_mode="public")
    report = compute_readiness(db, course)
    check = _check(report, "has_enrollment_window")
    assert check is not None
    assert check.passed is False


def test_quiz_weight_zero_flags_polish_when_quiz_chapter_present(db: Session, teacher: User):
    course = _make_course(db)
    course.quiz_weight = 0
    course.assignment_weight = 80
    course.participation_weight = 20
    module = _add_module(db, course)
    chapter = _add_chapter(db, module, chapter_type="quiz")
    _add_quiz_with_question(db, chapter)
    report = compute_readiness(db, course)
    check = _check(report, "quiz_weight_nonzero")
    assert check is not None
    assert check.severity == "polish"
    assert check.passed is False


def test_score_is_100_when_everything_passes(db: Session, teacher: User):
    """Sanity: a fully-completed course reports score=100, no critical fails."""
    from datetime import UTC, datetime, timedelta

    course = _make_course(
        db,
        description="A complete course",
        image_url="https://example.com/cover.jpg",
        enrollment_start=datetime.now(UTC),
        enrollment_end=datetime.now(UTC) + timedelta(days=30),
    )
    module_a = _add_module(db, course, title="Module A")
    module_b = _add_module(db, course, title="Module B")
    chapter = _add_chapter(db, module_a, chapter_type="reading")
    _add_text_block(db, chapter, content="Solid lesson")
    _add_chapter(db, module_b, chapter_type="reading")
    _add_text_block(
        db, module_b.chapters[0] if module_b.chapters else _add_chapter(db, module_b, chapter_type="reading")
    )
    report = compute_readiness(db, course)
    assert report.critical_failing == 0
    assert report.score == 100


def test_report_score_is_percent(db: Session, teacher: User):
    course = _make_course(db)
    report = compute_readiness(db, course)
    assert 0 <= report.score <= 100


# ─── Route-level tests ──────────────────────────────────────────────────


def test_route_returns_report_for_owner(client, db: Session, teacher: User):
    course = _make_course(db)
    db.commit()
    resp = client.get(f"/api/v1/courses/{course.id}/readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["course_id"] == course.id
    assert "checks" in body
    assert isinstance(body["score"], int)


def test_route_404_for_missing_course(client):
    resp = client.get(f"/api/v1/courses/{uuid.uuid4()}/readiness")
    assert resp.status_code == 404


def test_route_denies_other_teacher(db: Session, client, teacher: User):
    """A teacher who isn't the course owner gets 403."""
    from app.api.dependencies import get_current_user
    from app.main import app
    from app.models.user import UserRole

    other = User(
        id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        email="other@example.com",
        full_name="Other Teacher",
        role=UserRole.TEACHER.value,
    )
    db.add(other)
    course = _make_course(db)
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: other
    try:
        resp = client.get(f"/api/v1/courses/{course.id}/readiness")
        assert resp.status_code == 403
    finally:
        # Restore the teacher fixture's override so trailing tests still see it.
        app.dependency_overrides[get_current_user] = lambda: teacher


@pytest.mark.parametrize(
    "field",
    ["course_id", "total", "passing", "critical_failing", "score", "checks"],
)
def test_route_response_has_all_top_level_fields(client, db: Session, field: str):
    course = _make_course(db)
    db.commit()
    resp = client.get(f"/api/v1/courses/{course.id}/readiness")
    assert resp.status_code == 200
    assert field in resp.json()
