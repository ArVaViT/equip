"""A chapter without a module is still walked, still resolved, still a gap.

Step 2 of the chapter→course move (step 1: ``chapters.course_id``, PR
#1227) turns the translation contour from ``course → module → chapter``
to ``course → chapter``. The contour is the dangerous one to move,
because here a chapter that cannot be reached does not fail — it
disappears:

* ``iter_course_entities`` walked ``course.modules → module.chapters``.
  A chapter with no module was not walked, and neither were its blocks,
  quizzes and assignments. ``plan_course_tasks`` planned nothing for it;
  ``course_translation_completeness`` found no gap; ``promote_if_complete``
  published the course as whole in every language with one lesson still
  in the author's.
* the ``chapter`` resolver walked ``chapter.module.course`` and answered
  ``None`` for a chapter with no module. ``None`` is "orphan, skip":
  ``reconcile_entity`` did nothing, the post-edit hook did nothing, and
  ``edit_should_be_staged`` returned False — a teacher's edit on a
  published course went live at once, in one language.
* ``_resolve_course_via_chapter`` (blocks, assignments, quizzes,
  questions, options) joined through ``modules`` and lost the same rows.

Two proofs. First, on a course where every chapter has a module — every
course today — the module walk and the course walk name exactly the same
entities, so nothing changes. Second, on a course with one chapter that
has no module, the contour sees the chapter and everything under it.

The test schema is built from the model, so ``Chapter.module_id`` is
``nullable=True`` on the model while production still says NOT NULL — the
one deliberate step ahead of the database, so this file can be written.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.quiz import Quiz, QuizQuestion
from app.schemas.course import ChapterResponse
from app.schemas.locale import LOCALE_CODES
from app.services.content_versions.write import record_human_version
from app.services.course_service import get_course
from app.services.staged_edits import edit_should_be_staged
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.course_pipeline import plan_course_tasks
from app.services.translation.course_tree import iter_course_entities
from app.services.translation.registry import REGISTRY, _resolve_course_via_chapter
from app.services.translation.resolve_for_display import resolve_chapter_locale_context
from app.services.translation.service import reset_translation_provider_cache
from tests._cv_helpers import (
    make_assignment_with_text,
    make_quiz_option_with_text,
    make_quiz_question_with_text,
    make_quiz_with_text,
)
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

pytestmark = pytest.mark.usefixtures("teacher")

#: The entity types the chapter walk produces. Side entities (rubrics,
#: announcements, events, cohorts) hang off ``course_id`` and never went
#: through the modules; the course and its modules are the walk's root.
TREE_TYPES = frozenset({"chapter", "chapter_block", "quiz", "quiz_question", "quiz_option", "assignment"})
TARGETS = frozenset(code for code in LOCALE_CODES if code != "ru")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _course(db: Session) -> Course:
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        title="Основания",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.flush()
    return course


def _module(db: Session, course: Course, order_index: int, *, binned: bool = False) -> Module:
    module = Module(
        id=f"mod-{uuid.uuid4().hex[:8]}",
        course_id=course.id,
        title=f"Модуль {order_index + 1}",
        order_index=order_index,
        deleted_at=datetime.now(UTC) if binned else None,
    )
    db.add(module)
    db.flush()
    return module


def _chapter(db: Session, course: Course, module: Module | None, title: str, *, binned: bool = False) -> Chapter:
    """A chapter of ``course``; grouped under ``module`` when one is given.

    ``course_id`` is set here, as every production write path sets it —
    so the conftest autopopulator (which fills it in from the module)
    has nothing to do, and a chapter with no module is simply a chapter
    that names its course.
    """
    chapter = Chapter(
        id=f"ch-{uuid.uuid4().hex[:8]}",
        course_id=course.id,
        module_id=module.id if module is not None else None,
        title=title,
        order_index=0,
        deleted_at=datetime.now(UTC) if binned else None,
    )
    db.add(chapter)
    db.flush()
    return chapter


def _block(db: Session, chapter: Chapter, text: str) -> ChapterBlock:
    block = ChapterBlock(id=uuid.uuid4(), chapter_id=chapter.id, block_type="text", order_index=0)
    db.add(block)
    db.flush()
    record_human_version(
        db, entity_type="chapter_block", entity_id=str(block.id), field="content", locale="ru", text=text
    )
    return block


def _quiz_tree(db: Session, chapter: Chapter) -> tuple[Quiz, QuizQuestion, uuid.UUID]:
    quiz = make_quiz_with_text(db, chapter_id=chapter.id, title="Проверка", locale="ru")
    question = make_quiz_question_with_text(db, quiz_id=quiz.id, question_text="Кто написал Послание?", locale="ru")
    option = make_quiz_option_with_text(db, question_id=question.id, option_text="Павел", is_correct=True, locale="ru")
    return quiz, question, option.id


def _walk(db: Session, course: Course) -> set[tuple[str, str]]:
    return {(kind, str(entity.id)) for kind, entity in iter_course_entities(db, course) if kind in TREE_TYPES}  # type: ignore[attr-defined]


def _walk_through_the_modules(db: Session, course: Course) -> set[tuple[str, str]]:
    """The walk as it was before 2026-09-07: modules → chapters → the rest.

    Kept here, not in the product, so the two can be compared. Binned
    modules and binned chapters are skipped exactly as the old code did.
    """
    modules = [module for module in course.modules if module.deleted_at is None]
    chapter_ids = [ch.id for mod in modules for ch in mod.chapters if ch.deleted_at is None]
    found: set[tuple[str, str]] = {("chapter", cid) for cid in chapter_ids}
    if not chapter_ids:
        return found
    blocks = db.query(ChapterBlock).filter(ChapterBlock.chapter_id.in_(chapter_ids)).all()
    found |= {("chapter_block", str(b.id)) for b in blocks}
    block_quiz_ids = [b.quiz_id for b in blocks if b.quiz_id]
    block_assignment_ids = [b.assignment_id for b in blocks if b.assignment_id]
    quizzes = (
        db.query(Quiz)
        .filter((Quiz.chapter_id.in_(chapter_ids)) | (Quiz.id.in_(block_quiz_ids) if block_quiz_ids else False))
        .all()
    )
    for quiz in quizzes:
        found.add(("quiz", str(quiz.id)))
        for question in quiz.questions:
            found.add(("quiz_question", str(question.id)))
            found |= {("quiz_option", str(option.id)) for option in question.options}
    assignments = (
        db.query(Assignment)
        .filter(
            (Assignment.chapter_id.in_(chapter_ids))
            | (Assignment.id.in_(block_assignment_ids) if block_assignment_ids else False)
        )
        .all()
    )
    found |= {("assignment", str(a.id)) for a in assignments}
    return found


# ---------------------------------------------------------------------------
# Proof 1: while every chapter has a module, the two walks agree
# ---------------------------------------------------------------------------


@pytest.fixture
def course_where_every_chapter_has_a_module(db: Session) -> Course:
    """Two live modules, one binned; live, binned and orphaned-by-bin
    chapters; a block, a quiz tree and an assignment under each."""
    course = _course(db)
    first = _module(db, course, 0)
    second = _module(db, course, 1)
    binned_module = _module(db, course, 2, binned=True)

    live = [
        _chapter(db, course, first, "Урок 1"),
        _chapter(db, course, first, "Урок 2"),
        _chapter(db, course, second, "Урок 3"),
    ]
    hidden = [
        _chapter(db, course, first, "Урок в корзине", binned=True),
        _chapter(db, course, binned_module, "Урок модуля в корзине"),
    ]
    for chapter in [*live, *hidden]:
        _block(db, chapter, f"<p>Абзац к «{chapter.title}».</p>")
        _quiz_tree(db, chapter)
        make_assignment_with_text(db, chapter_id=chapter.id, title="Задание", locale="ru")
    db.commit()
    return course


class TestTheTwoWalksAgree:
    def test_the_course_walk_names_exactly_what_the_module_walk_named(
        self, db: Session, course_where_every_chapter_has_a_module: Course
    ) -> None:
        course = course_where_every_chapter_has_a_module
        through_modules = _walk_through_the_modules(db, course)
        from_the_course = _walk(db, course)

        assert from_the_course == through_modules
        # Not vacuous: every kind of entity is in the comparison.
        assert {kind for kind, _ in from_the_course} == TREE_TYPES
        assert len([1 for kind, _ in from_the_course if kind == "chapter"]) == 3

    def test_whichever_way_the_course_was_loaded(
        self, db: Session, course_where_every_chapter_has_a_module: Course
    ) -> None:
        # ``get_course`` filters the bin in its loader; a plain fetch does
        # not. The course walk must give one answer either way, and it
        # must be the module walk's answer.
        plain = _walk(db, course_where_every_chapter_has_a_module)
        db.expire_all()
        loaded = get_course(db, course_where_every_chapter_has_a_module.id)
        assert loaded is not None
        assert _walk(db, loaded) == plain == _walk_through_the_modules(db, loaded)

    def test_a_chapter_under_a_binned_module_is_still_not_walked(
        self, db: Session, course_where_every_chapter_has_a_module: Course
    ) -> None:
        walked_titles = {
            entity.title
            for kind, entity in iter_course_entities(db, course_where_every_chapter_has_a_module)
            if kind == "chapter"
        }
        assert walked_titles == {"Урок 1", "Урок 2", "Урок 3"}


# ---------------------------------------------------------------------------
# Proof 2: a chapter with no module is a chapter
# ---------------------------------------------------------------------------


@pytest.fixture
def course_with_a_chapter_outside_any_module(db: Session) -> tuple[Course, Chapter, Chapter]:
    """One grouped chapter, one ungrouped, a block and a quiz tree and an
    assignment under each; returns ``(course, grouped, ungrouped)``."""
    course = _course(db)
    module = _module(db, course, 0)
    grouped = _chapter(db, course, module, "Урок в модуле")
    ungrouped = _chapter(db, course, None, "Урок без модуля")
    for chapter in (grouped, ungrouped):
        _block(db, chapter, f"<p>Абзац к «{chapter.title}».</p>")
        _quiz_tree(db, chapter)
        make_assignment_with_text(db, chapter_id=chapter.id, title="Задание", locale="ru")
    db.commit()
    return course, grouped, ungrouped


def _under(db: Session, chapter: Chapter) -> set[tuple[str, str]]:
    """Everything the walk should produce for one chapter."""
    found = {("chapter", chapter.id)}
    found |= {("chapter_block", str(b.id)) for b in db.query(ChapterBlock).filter_by(chapter_id=chapter.id)}
    for quiz in db.query(Quiz).filter_by(chapter_id=chapter.id):
        found.add(("quiz", str(quiz.id)))
        for question in quiz.questions:
            found.add(("quiz_question", str(question.id)))
            found |= {("quiz_option", str(o.id)) for o in question.options}
    found |= {("assignment", str(a.id)) for a in db.query(Assignment).filter_by(chapter_id=chapter.id)}
    return found


class TestTheWalkReachesIt:
    def test_the_chapter_and_everything_under_it_are_walked(
        self, db: Session, course_with_a_chapter_outside_any_module: tuple[Course, Chapter, Chapter]
    ) -> None:
        course, grouped, ungrouped = course_with_a_chapter_outside_any_module
        expected = _under(db, grouped) | _under(db, ungrouped)
        assert len(expected) == 12  # 2 x (chapter, block, quiz, question, option, assignment)

        assert _walk(db, course) == expected
        db.expire_all()
        loaded = get_course(db, course.id)
        assert loaded is not None
        assert _walk(db, loaded) == expected

    def test_the_plan_has_work_for_it(
        self, db: Session, course_with_a_chapter_outside_any_module: tuple[Course, Chapter, Chapter]
    ) -> None:
        course, _grouped, ungrouped = course_with_a_chapter_outside_any_module
        planned = {(t.entity_type, t.entity_id, t.field, t.target_locale) for t in plan_course_tasks(db, course)}
        assert {("chapter", ungrouped.id, "title", locale) for locale in TARGETS} <= planned
        block = db.query(ChapterBlock).filter_by(chapter_id=ungrouped.id).one()
        assert {("chapter_block", str(block.id), "content", locale) for locale in TARGETS} <= planned

    def test_the_course_is_not_complete_while_it_is_untranslated(
        self, db: Session, course_with_a_chapter_outside_any_module: tuple[Course, Chapter, Chapter]
    ) -> None:
        # The failure this guards: no gap, ``is_complete`` True, and
        # ``promote_if_complete`` publishing a course with a lesson in one
        # language.
        course, _grouped, ungrouped = course_with_a_chapter_outside_any_module
        completeness = course_translation_completeness(db, course)
        assert not completeness.is_complete
        gaps = {(g.entity_type, g.entity_id, g.field, g.locale) for g in completeness.gaps}
        assert {("chapter", ungrouped.id, "title", locale) for locale in TARGETS} <= gaps
        block = db.query(ChapterBlock).filter_by(chapter_id=ungrouped.id).one()
        assert {("chapter_block", str(block.id), "content", locale) for locale in TARGETS} <= gaps


class TestTheResolversReachIt:
    def test_the_chapter_resolves_to_its_course(
        self, db: Session, course_with_a_chapter_outside_any_module: tuple[Course, Chapter, Chapter]
    ) -> None:
        course, _grouped, ungrouped = course_with_a_chapter_outside_any_module
        assert ungrouped.module_id is None
        resolved = REGISTRY["chapter"].resolve_course(db, ungrouped)
        assert resolved is not None
        assert resolved.id == course.id

    def test_what_hangs_off_the_chapter_resolves_to_its_course(
        self, db: Session, course_with_a_chapter_outside_any_module: tuple[Course, Chapter, Chapter]
    ) -> None:
        course, _grouped, ungrouped = course_with_a_chapter_outside_any_module
        block = db.query(ChapterBlock).filter_by(chapter_id=ungrouped.id).one()
        quiz = db.query(Quiz).filter_by(chapter_id=ungrouped.id).one()
        question = quiz.questions[0]
        option = question.options[0]
        assignment = db.query(Assignment).filter_by(chapter_id=ungrouped.id).one()

        assert _resolve_course_via_chapter(db, block) is not None
        for entity_type, entity in (
            ("chapter_block", block),
            ("quiz", quiz),
            ("quiz_question", question),
            ("quiz_option", option),
            ("assignment", assignment),
        ):
            resolved = REGISTRY[entity_type].resolve_course(db, entity)
            assert resolved is not None, entity_type
            assert resolved.id == course.id, entity_type

    def test_an_edit_to_it_on_a_published_course_is_staged(
        self, db: Session, course_with_a_chapter_outside_any_module: tuple[Course, Chapter, Chapter]
    ) -> None:
        # The headline consequence of the old resolver: False here means
        # a teacher's new title skips staging and reaches every student
        # at once, in the author's language only.
        course, grouped, ungrouped = course_with_a_chapter_outside_any_module
        assert course.status == CourseStatus.PUBLISHED
        assert edit_should_be_staged(db, "chapter", grouped.id)
        assert edit_should_be_staged(db, "chapter", ungrouped.id)
        block = db.query(ChapterBlock).filter_by(chapter_id=ungrouped.id).one()
        assert edit_should_be_staged(db, "chapter_block", str(block.id))

    def test_the_reader_s_locale_context_finds_it(
        self, db: Session, course_with_a_chapter_outside_any_module: tuple[Course, Chapter, Chapter]
    ) -> None:
        _, _grouped, ungrouped = course_with_a_chapter_outside_any_module
        context = resolve_chapter_locale_context(db, chapter_id=ungrouped.id, current_user=None)
        assert context.found
        assert context.source_locale == "ru"

    def test_the_reader_s_locale_context_honours_the_chapter_s_own_bin_only(
        self, db: Session, course_where_every_chapter_has_a_module: Course
    ) -> None:
        # The bin that counts is the chapter's own. A binned module used
        # to hide its chapters here too; now that the module is optional
        # it is a heading, and a missing heading does not make the lesson
        # unreadable — the reader would otherwise get ``found=False``,
        # which is not an error but a silent default (``ru``, overlay on)
        # that misdescribes the chapter's language to everyone.
        by_title = {
            chapter.title: chapter
            for chapter in db.query(Chapter).filter_by(course_id=course_where_every_chapter_has_a_module.id)
        }
        assert resolve_chapter_locale_context(db, chapter_id=by_title["Урок 1"].id, current_user=None).found
        assert resolve_chapter_locale_context(
            db, chapter_id=by_title["Урок модуля в корзине"].id, current_user=None
        ).found
        assert not resolve_chapter_locale_context(db, chapter_id=by_title["Урок в корзине"].id, current_user=None).found


# ---------------------------------------------------------------------------
# The response can carry a chapter with no module
# ---------------------------------------------------------------------------


def test_the_chapter_response_carries_no_module_as_null():
    response = ChapterResponse.model_validate(
        {
            "id": "ch-1",
            "module_id": None,
            "course_id": "c-1",
            "title": "Урок",
            "order_index": 0,
            "chapter_type": "reading",
            "requires_completion": False,
            "is_locked": False,
        }
    )
    assert response.module_id is None
