"""Single source of truth for translatable entities.

Adding a new translatable entity is a 2-step ritual:

1. Append an ``EntityRegistration`` here. Include the fields you want
   translated, the course-id resolver (so the reconcile helper knows the
   source locale + owner), and an optional prompt-context builder.
2. If the new ``entity_type`` literal value isn't yet in the
   ``content_translations.entity_type`` ``CHECK`` constraint, ship a
   migration that extends the constraint. The
   ``test_registry_matches_check_constraint`` test guards drift in
   either direction.

Everything else — the tree walker in ``course_pipeline``, the resolve
helpers in ``resolve_for_display``, the per-entity write hooks in
``pipeline_hooks`` — reads from this registry. There is one place to
update, not five.

Why a registry instead of inheritance / Protocol-per-entity? The
specifics are short (field list + a 2-line course resolver) and the
indirection of subclasses would obscure that. Data-driven is cheaper to
read and lets unit tests assert structural invariants (registry vs
migration vs Pydantic ``Literal``) at the same level of abstraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.models.announcement import Announcement
from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.cohort import Cohort
from app.models.course import Chapter, Course, Module
from app.models.course_event import CourseEvent
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.schemas.locale import normalize_locale
from app.services.translation.orchestrator import (
    OrchestratorReport,
    TranslationFieldSpec,
    translate_entity_fields,
)
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.models.content_translation import TranslationField
    from app.schemas.locale import LocaleCode
    from app.services.translation.protocol import (
        ContentKind,
        EntityType,
        TranslationProvider,
    )


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """A translatable field on an entity model.

    ``name`` is what gets stored in ``content_translations.field``; it
    must be a member of the ``TranslationField`` literal (which maps to
    the DB ``field`` CHECK constraint). ``model_attr`` is the Python
    attribute on the entity to read source text from — defaults to
    ``name`` when the model attribute matches the DB field. They differ
    when an entity uses a non-canonical field name (e.g. ``Cohort.name``
    is conceptually a title — store it under ``field='title'``).
    """

    name: TranslationField
    content_kind: ContentKind
    model_attr: str | None = None

    @property
    def attr(self) -> str:
        return self.model_attr or self.name


@dataclass(frozen=True, slots=True)
class EntityRegistration:
    """How to reconcile one translatable entity type."""

    entity_type: EntityType
    fields: tuple[FieldSpec, ...]
    # Returns the course this entity belongs to, or ``None`` if the entity
    # is orphaned (e.g. an announcement with no ``course_id``). Orphans are
    # skipped: there is no source-locale to translate from.
    resolve_course: Callable[[Session, Any], Course | None]
    # Optional per-call prompt context. Kept short — Gemini gets confused by
    # walls of context and the system prompt already covers the global rules.
    # Entity arg is ``Any`` because the lambda is paired with the entity_type
    # at registration time; mypy can't statically prove the type pairing.
    build_context: Callable[[Any, Course], str | None] | None = None


# ---------------------------------------------------------------------------
# Course resolvers — a couple shared lambdas to keep registrations one-liner.
# ---------------------------------------------------------------------------


def _resolve_course_self(_db: Session, entity: Any) -> Course | None:
    return entity if isinstance(entity, Course) else None


def _resolve_course_via_attr(attr: str) -> Callable[[Session, Any], Course | None]:
    def resolver(db: Session, entity: Any) -> Course | None:
        course_id = getattr(entity, attr, None)
        if not course_id:
            return None
        return db.query(Course).filter(Course.id == course_id).first()

    return resolver


def _resolve_course_via_module(_db: Session, entity: Any) -> Course | None:
    """For chapters: walk chapter -> module -> course via loaded relations."""
    module = getattr(entity, "module", None)
    if module is None:
        return None
    return getattr(module, "course", None)


def _resolve_course_via_chapter(db: Session, entity: Any) -> Course | None:
    """For chapter_block / assignment: chapter_id -> chapter -> module -> course."""
    chapter_id = getattr(entity, "chapter_id", None)
    if not chapter_id:
        return None
    row = (
        db.query(Course)
        .join(Module, Module.course_id == Course.id)
        .join(Chapter, Chapter.module_id == Module.id)
        .filter(Chapter.id == chapter_id)
        .first()
    )
    return row


def _resolve_course_via_quiz_chapter(db: Session, entity: Any) -> Course | None:
    """Quiz -> chapter -> module -> course."""
    chapter_id = getattr(entity, "chapter_id", None)
    if not chapter_id:
        return None
    row = (
        db.query(Course)
        .join(Module, Module.course_id == Course.id)
        .join(Chapter, Chapter.module_id == Module.id)
        .filter(Chapter.id == chapter_id)
        .first()
    )
    return row


def _resolve_course_via_question(db: Session, entity: Any) -> Course | None:
    """QuizQuestion -> quiz -> chapter -> ... -> course."""
    quiz_id = getattr(entity, "quiz_id", None)
    if not quiz_id:
        return None
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if quiz is None:
        return None
    return _resolve_course_via_quiz_chapter(db, quiz)


def _resolve_course_via_option(db: Session, entity: Any) -> Course | None:
    """QuizOption -> question -> quiz -> chapter -> ... -> course."""
    question_id = getattr(entity, "question_id", None)
    if not question_id:
        return None
    question = db.query(QuizQuestion).filter(QuizQuestion.id == question_id).first()
    if question is None:
        return None
    return _resolve_course_via_question(db, question)


# ---------------------------------------------------------------------------
# Registry — list every translatable entity once.
# ---------------------------------------------------------------------------


REGISTRY: dict[EntityType, EntityRegistration] = {
    "course": EntityRegistration(
        entity_type="course",
        fields=(FieldSpec("title", "title"), FieldSpec("description", "plain")),
        resolve_course=_resolve_course_self,
        build_context=lambda c, _: f"Course title: {c.title}" if getattr(c, "title", None) else None,
    ),
    "module": EntityRegistration(
        entity_type="module",
        fields=(FieldSpec("title", "title"), FieldSpec("description", "plain")),
        resolve_course=_resolve_course_via_attr("course_id"),
        build_context=lambda _m, c: f"Course module in «{c.title}»",
    ),
    "chapter": EntityRegistration(
        entity_type="chapter",
        fields=(FieldSpec("title", "title"),),
        resolve_course=_resolve_course_via_module,
        build_context=lambda _ch, c: f"Chapter in course «{c.title}»",
    ),
    "chapter_block": EntityRegistration(
        entity_type="chapter_block",
        fields=(FieldSpec("content", "html"),),
        resolve_course=_resolve_course_via_chapter,
        build_context=lambda _b, c: f"HTML fragment from course «{c.title}»",
    ),
    "quiz": EntityRegistration(
        entity_type="quiz",
        fields=(FieldSpec("title", "title"), FieldSpec("description", "plain")),
        resolve_course=_resolve_course_via_quiz_chapter,
        build_context=lambda _q, c: f"Quiz in course: {c.title}",
    ),
    "quiz_question": EntityRegistration(
        entity_type="quiz_question",
        fields=(FieldSpec("question_text", "quiz_question"),),
        resolve_course=_resolve_course_via_question,
        build_context=lambda _q, c: f"Quiz question in course «{c.title}»",
    ),
    "quiz_option": EntityRegistration(
        entity_type="quiz_option",
        fields=(FieldSpec("option_text", "quiz_option"),),
        resolve_course=_resolve_course_via_option,
        build_context=lambda _o, _c: "Answer option for a Bible-study quiz question.",
    ),
    "assignment": EntityRegistration(
        entity_type="assignment",
        fields=(FieldSpec("title", "title"), FieldSpec("description", "plain")),
        resolve_course=_resolve_course_via_chapter,
        build_context=lambda _a, c: f"Assignment in course «{c.title}»",
    ),
    "announcement": EntityRegistration(
        entity_type="announcement",
        fields=(FieldSpec("title", "title"), FieldSpec("content", "plain")),
        resolve_course=_resolve_course_via_attr("course_id"),
        build_context=lambda _a, c: f"Announcement in course «{c.title}»",
    ),
    "course_event": EntityRegistration(
        entity_type="course_event",
        fields=(FieldSpec("title", "title"), FieldSpec("description", "plain")),
        resolve_course=_resolve_course_via_attr("course_id"),
        build_context=lambda _e, c: f"Calendar event in course «{c.title}»",
    ),
    "cohort": EntityRegistration(
        entity_type="cohort",
        fields=(FieldSpec("title", "title", model_attr="name"),),
        resolve_course=_resolve_course_via_attr("course_id"),
        build_context=lambda _co, c: f"Student cohort name in course «{c.title}»",
    ),
}


# Quick model-class lookup for the CI guard / tests. Order doesn't matter.
ENTITY_MODEL: dict[EntityType, type] = {
    "course": Course,
    "module": Module,
    "chapter": Chapter,
    "chapter_block": ChapterBlock,
    "quiz": Quiz,
    "quiz_question": QuizQuestion,
    "quiz_option": QuizOption,
    "assignment": Assignment,
    "announcement": Announcement,
    "course_event": CourseEvent,
    "cohort": Cohort,
}


# ---------------------------------------------------------------------------
# The single helper every write hook + tree-walker uses.
# ---------------------------------------------------------------------------


def reconcile_entity(
    db: Session,
    entity_type: EntityType,
    entity: object,
    *,
    provider: TranslationProvider | None = None,
) -> OrchestratorReport:
    """Translate one entity into every locale ≠ its course's source_locale.

    Idempotent: ``translate_entity_fields`` short-circuits unchanged
    fields via ``source_hash``, so re-calling on the same entity costs
    zero Gemini calls. Returns a per-entity report counting translated /
    skipped / failed rows.

    Skipped (returns empty report) when:
    * Translation provider not configured.
    * Entity has no associated course (orphan announcement, unattached
      quiz). No source locale → nothing to do.
    * All entity fields are empty / whitespace.
    """
    if not is_translation_enabled():
        return OrchestratorReport()
    reg = REGISTRY[entity_type]
    course = reg.resolve_course(db, entity)
    if course is None:
        return OrchestratorReport()
    source_locale: LocaleCode = normalize_locale(course.source_locale)

    fields: list[TranslationFieldSpec] = []
    for fs in reg.fields:
        text = getattr(entity, fs.attr, None)
        if text is None or not str(text).strip():
            continue
        fields.append(TranslationFieldSpec(field=fs.name, text=text, content_kind=fs.content_kind))
    if not fields:
        return OrchestratorReport()

    context: str | None = None
    if reg.build_context is not None:
        context = reg.build_context(entity, course)

    return translate_entity_fields(
        db,
        entity_type=entity_type,
        entity_id=str(entity.id),  # type: ignore[attr-defined]
        source_locale=source_locale,
        fields=fields,
        context=context,
        provider=provider,
    )


__all__ = [
    "ENTITY_MODEL",
    "REGISTRY",
    "EntityRegistration",
    "FieldSpec",
    "reconcile_entity",
]
