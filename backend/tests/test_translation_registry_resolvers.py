"""Unit tests for the translation-registry course resolvers.

Each registered translatable entity (``module``, ``chapter``,
``chapter_block``, ``quiz``, ``quiz_question``, ``quiz_option``,
``assignment``, ``announcement``, ``course_event``, ``cohort``) ships
with a ``resolve_course`` lambda that the orchestrator calls to look
up the entity's course (for ``source_locale`` and ownership). The
resolvers are *the* indirection that makes the registry work for
nested entities — a bug in one of them silently de-syncs translation
for every row of that type.

The existing registry suite covers structural invariants (REGISTRY ↔
``EntityType`` ↔ migration ↔ models) and a single happy-path
``module`` resolver call. Resolvers for ``chapter``, ``chapter_block``,
``quiz``, ``quiz_question``, ``quiz_option``, ``assignment``,
``announcement``, ``course_event``, and ``cohort`` were all
0%-covered. This file adds direct tests for each:

  * positive case — the resolver finds the right course.
  * negative cases — missing FK / unreachable parent → ``None``
    (the orchestrator interprets ``None`` as "orphan, skip").

Tests target the *private* resolver helpers because:
  - The public ``reconcile_entity`` runs through ``is_translation_enabled``
    + Gemini orchestration; either short-circuits or hits the network.
  - Resolvers are pure DB lookups — no provider, no API key.
  - This is the granularity the bug would actually live at: a wrong
    join, a wrong attribute name. ``reconcile_entity`` tests would
    smear that signal across the orchestrator's other branches.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy.types as _sa_types
from sqlalchemy.orm import Session

from app.models.announcement import Announcement
from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.cohort import Cohort
from app.models.course import Chapter, Course, Module
from app.models.course_event import CourseEvent
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.services.translation.registry import (
    _resolve_course_self,
    _resolve_course_via_attr,
    _resolve_course_via_chapter,
    _resolve_course_via_module,
    _resolve_course_via_option,
    _resolve_course_via_question,
    _resolve_course_via_quiz_chapter,
)
from tests.conftest import TEACHER_ID

# SQLite compatibility — see notes in ``test_cohorts_calendar_notifications.py``.
_orig_uuid_bp = _sa_types.Uuid.bind_processor


def _uuid_bp_accepting_strings(self, dialect):
    processor = _orig_uuid_bp(self, dialect)
    if processor is None:
        return None

    def _process(value):
        if isinstance(value, str):
            with contextlib.suppress(ValueError):
                value = uuid.UUID(value)
        return processor(value)

    return _process


_sa_types.Uuid.bind_processor = _uuid_bp_accepting_strings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def course(db: Session, teacher) -> Course:
    c = Course(
        id="resolver-course",
        title="Resolver Test",
        description="x",
        status="published",
        source_locale="ru",
        created_by=teacher.id,
    )
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def module(db: Session, course: Course) -> Module:
    m = Module(
        id="resolver-module",
        course_id=course.id,
        title="M1",
        order_index=0,
    )
    db.add(m)
    db.flush()
    return m


@pytest.fixture
def chapter(db: Session, module: Module) -> Chapter:
    ch = Chapter(
        id="resolver-chapter",
        module_id=module.id,
        title="C1",
        order_index=0,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture
def quiz(db: Session, chapter: Chapter) -> Quiz:
    q = Quiz(
        id=uuid.uuid4(),
        chapter_id=chapter.id,
        title="Q1",
        description="d",
    )
    db.add(q)
    db.flush()
    return q


@pytest.fixture
def quiz_question(db: Session, quiz: Quiz) -> QuizQuestion:
    qq = QuizQuestion(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        question_text="t?",
        question_type="multiple_choice",
        order_index=0,
        points=1,
    )
    db.add(qq)
    db.flush()
    return qq


@pytest.fixture
def quiz_option(db: Session, quiz_question: QuizQuestion) -> QuizOption:
    qo = QuizOption(
        id=uuid.uuid4(),
        question_id=quiz_question.id,
        option_text="A",
        is_correct=True,
        order_index=0,
    )
    db.add(qo)
    db.flush()
    return qo


# ---------------------------------------------------------------------------
# _resolve_course_self
# ---------------------------------------------------------------------------


class TestResolveCourseSelf:
    """Used by the ``course`` registration — the entity IS the course."""

    def test_returns_entity_when_it_is_a_course(self, db: Session, course: Course):
        assert _resolve_course_self(db, course) is course

    def test_returns_none_when_entity_is_not_a_course(self, db: Session):
        # A non-Course instance should fall through to None — guards
        # against a future caller swapping the resolver and missing
        # the isinstance guard.
        assert _resolve_course_self(db, "not-a-course") is None
        assert _resolve_course_self(db, None) is None


# ---------------------------------------------------------------------------
# _resolve_course_via_attr
# ---------------------------------------------------------------------------


class TestResolveCourseViaAttr:
    """Used by module / announcement / course_event / cohort. Walks
    ``entity.<attr>`` (e.g. ``course_id``) and looks the course up
    by primary key."""

    def test_resolves_course_via_course_id(self, db: Session, course: Course, module: Module):
        resolver = _resolve_course_via_attr("course_id")
        assert resolver(db, module) is not None
        assert resolver(db, module).id == course.id

    def test_returns_none_when_attr_missing_or_falsy(self, db: Session, course: Course):
        resolver = _resolve_course_via_attr("course_id")
        # Announcement without course_id is the canonical "orphan" — the
        # comment on the resolver explicitly says this returns None.
        orphan = Announcement(title="Orphan", content="x", course_id=None, created_by=TEACHER_ID)
        db.add(orphan)
        db.flush()
        assert resolver(db, orphan) is None

    def test_returns_none_when_referenced_course_doesnt_exist(self, db: Session):
        # course_id pointing nowhere → None (DB lookup returns nothing).
        # We can't add a real FK pointing nowhere on SQLite — emulate
        # with a fake entity-shape object.
        class FakeAnnouncement:
            course_id = "ghost-course"

        resolver = _resolve_course_via_attr("course_id")
        assert resolver(db, FakeAnnouncement()) is None


# ---------------------------------------------------------------------------
# _resolve_course_via_module — used by ``chapter``
# ---------------------------------------------------------------------------


class TestResolveCourseViaModule:
    def test_resolves_chapter_to_course_via_relationship(
        self, db: Session, course: Course, chapter: Chapter
    ):
        # The relationship is lazy-loaded; trigger it once before the
        # resolver runs to mirror the orchestrator's usage path.
        _ = chapter.module
        assert _resolve_course_via_module(db, chapter) is course

    def test_returns_none_when_module_missing(self, db: Session):
        class FakeChapter:
            module = None

        assert _resolve_course_via_module(db, FakeChapter()) is None

    def test_returns_none_when_module_has_no_course(self, db: Session):
        class FakeChapter:
            class _M:
                course = None

            module = _M()

        assert _resolve_course_via_module(db, FakeChapter()) is None


# ---------------------------------------------------------------------------
# _resolve_course_via_chapter — used by chapter_block + assignment
# ---------------------------------------------------------------------------


class TestResolveCourseViaChapter:
    def test_resolves_chapter_block_to_course(self, db: Session, course: Course, chapter: Chapter):
        block = ChapterBlock(
            id=uuid.uuid4(),
            chapter_id=chapter.id,
            block_type="text",
            order_index=0,
            content="<p>Hi</p>",
        )
        db.add(block)
        db.flush()
        assert _resolve_course_via_chapter(db, block) is not None
        assert _resolve_course_via_chapter(db, block).id == course.id

    def test_resolves_assignment_to_course(self, db: Session, course: Course, chapter: Chapter):
        asgn = Assignment(
            id=uuid.uuid4(),
            chapter_id=chapter.id,
            title="A1",
            description="d",
            max_score=10,
        )
        db.add(asgn)
        db.flush()
        assert _resolve_course_via_chapter(db, asgn) is not None
        assert _resolve_course_via_chapter(db, asgn).id == course.id

    def test_returns_none_when_chapter_id_missing(self, db: Session):
        class FakeBlock:
            chapter_id = None

        assert _resolve_course_via_chapter(db, FakeBlock()) is None

    def test_returns_none_when_chapter_id_points_to_ghost(self, db: Session):
        class FakeBlock:
            chapter_id = "non-existent-chapter"

        assert _resolve_course_via_chapter(db, FakeBlock()) is None


# ---------------------------------------------------------------------------
# _resolve_course_via_quiz_chapter — used by ``quiz``
# ---------------------------------------------------------------------------


class TestResolveCourseViaQuizChapter:
    def test_resolves_quiz_to_course(self, db: Session, course: Course, quiz: Quiz):
        assert _resolve_course_via_quiz_chapter(db, quiz) is not None
        assert _resolve_course_via_quiz_chapter(db, quiz).id == course.id

    def test_returns_none_when_chapter_id_missing(self, db: Session):
        class FakeQuiz:
            chapter_id = None

        assert _resolve_course_via_quiz_chapter(db, FakeQuiz()) is None

    def test_returns_none_when_chapter_doesnt_exist(self, db: Session):
        class FakeQuiz:
            chapter_id = "non-existent"

        assert _resolve_course_via_quiz_chapter(db, FakeQuiz()) is None


# ---------------------------------------------------------------------------
# _resolve_course_via_question — used by ``quiz_question``
# ---------------------------------------------------------------------------


class TestResolveCourseViaQuestion:
    def test_resolves_question_to_course(
        self, db: Session, course: Course, quiz_question: QuizQuestion
    ):
        assert _resolve_course_via_question(db, quiz_question) is not None
        assert _resolve_course_via_question(db, quiz_question).id == course.id

    def test_returns_none_when_quiz_id_missing(self, db: Session):
        class FakeQ:
            quiz_id = None

        assert _resolve_course_via_question(db, FakeQ()) is None

    def test_returns_none_when_quiz_doesnt_exist(self, db: Session):
        class FakeQ:
            quiz_id = uuid.uuid4()

        assert _resolve_course_via_question(db, FakeQ()) is None


# ---------------------------------------------------------------------------
# _resolve_course_via_option — used by ``quiz_option``
# ---------------------------------------------------------------------------


class TestResolveCourseViaOption:
    def test_resolves_option_to_course(
        self, db: Session, course: Course, quiz_option: QuizOption
    ):
        assert _resolve_course_via_option(db, quiz_option) is not None
        assert _resolve_course_via_option(db, quiz_option).id == course.id

    def test_returns_none_when_question_id_missing(self, db: Session):
        class FakeOpt:
            question_id = None

        assert _resolve_course_via_option(db, FakeOpt()) is None

    def test_returns_none_when_question_doesnt_exist(self, db: Session):
        class FakeOpt:
            question_id = uuid.uuid4()

        assert _resolve_course_via_option(db, FakeOpt()) is None


# ---------------------------------------------------------------------------
# Per-entity resolver smoke through the REGISTRY (catches registration bugs)
# ---------------------------------------------------------------------------


class TestRegistryWiring:
    """Cross-check: the REGISTRY entries must point at the right resolver.
    These tests catch a registration swap (e.g. ``announcement`` pointing
    at ``_resolve_course_via_module`` by accident) that the structural
    suite would miss — every resolver function would still be a callable
    of the right shape."""

    def test_announcement_resolves_via_course_id_attr(
        self, db: Session, course: Course, teacher
    ):
        from app.services.translation.registry import REGISTRY

        ann = Announcement(
            id=uuid.uuid4(),
            title="t",
            content="c",
            course_id=course.id,
            created_by=teacher.id,
        )
        db.add(ann)
        db.flush()
        resolved = REGISTRY["announcement"].resolve_course(db, ann)
        assert resolved is not None
        assert resolved.id == course.id

    def test_course_event_resolves_via_course_id_attr(
        self, db: Session, course: Course, teacher
    ):
        from app.services.translation.registry import REGISTRY

        ev = CourseEvent(
            id=uuid.uuid4(),
            course_id=course.id,
            title="t",
            description="d",
            event_type="exam",
            event_date=datetime(2026, 12, 1, 10, 0, tzinfo=UTC),
            created_by=teacher.id,
        )
        db.add(ev)
        db.flush()
        resolved = REGISTRY["course_event"].resolve_course(db, ev)
        assert resolved is not None
        assert resolved.id == course.id

    def test_cohort_resolves_via_course_id_attr_and_is_none_for_top_level_cohort(
        self, db: Session
    ):
        """The cohort entry uses ``_resolve_course_via_attr('course_id')``
        but Cohort is a top-level admin entity (ADR-010) that doesn't HAVE
        a ``course_id`` column. The resolver therefore returns None for
        every cohort — which is exactly what makes cohort name reconciliation
        a no-op until ADR-010 evolves. Lock the current behavior in so a
        future schema change is forced through this test."""
        from app.services.translation.registry import REGISTRY

        cohort = Cohort(
            id=uuid.uuid4(),
            name="Test Cohort",
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 6, 1, tzinfo=UTC),
            status="upcoming",
        )
        db.add(cohort)
        db.flush()
        assert REGISTRY["cohort"].resolve_course(db, cohort) is None


# ---------------------------------------------------------------------------
# build_context lambdas — each entity's prompt context should be a non-empty
# string when the entity has a title (the field most builders read).
# ---------------------------------------------------------------------------


class TestBuildContextLambdas:
    """Every entity in the registry (except ``quiz_option`` which uses a
    static string) builds its prompt context from the course title. A
    refactor that swaps the lambda's signature would surface as a crash
    inside ``reconcile_entity`` only when translation is enabled — these
    tests pin the lambdas' shape statically."""

    def test_each_entity_with_a_builder_returns_a_string(self, db: Session, course: Course):
        from app.services.translation.registry import REGISTRY

        for entity_type, reg in REGISTRY.items():
            if reg.build_context is None:
                continue
            ctx = reg.build_context(object(), course)
            assert ctx is None or isinstance(ctx, str), (
                f"{entity_type}: build_context returned a non-string: {type(ctx).__name__}"
            )

    def test_course_self_context_uses_course_title(self, course: Course):
        from app.services.translation.registry import REGISTRY

        ctx = REGISTRY["course"].build_context(course, course)
        assert ctx is not None
        assert course.title in ctx

    def test_module_context_mentions_the_course_title(self, course: Course):
        from app.services.translation.registry import REGISTRY

        ctx = REGISTRY["module"].build_context(object(), course)
        assert ctx is not None
        assert course.title in ctx
