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
from app.models.daily_challenge import DailyChallengeOption, DailyChallengeQuestion
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.models.rubric import Rubric, RubricCriterion, RubricLevel
from app.schemas.locale import normalize_locale
from app.services.language_detection import detect_locale
from app.services.translation.orchestrator import (
    OrchestratorReport,
    TranslationFieldSpec,
    translate_entity_fields,
)
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.content_version import ContentVersionField as TranslationField
    from app.schemas.locale import LocaleCode
    from app.services.translation.budget import TranslationBudget
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
    """Quiz -> chapter -> module -> course (same chapter_id walk as a block)."""
    return _resolve_course_via_chapter(db, entity)


def _resolve_course_via_question(db: Session, entity: Any) -> Course | None:
    """QuizQuestion -> quiz -> chapter -> ... -> course."""
    quiz_id = getattr(entity, "quiz_id", None)
    if not quiz_id:
        return None
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if quiz is None:
        return None
    return _resolve_course_via_quiz_chapter(db, quiz)


def _resolve_course_via_cohort_courses(db: Session, entity: Any) -> Course | None:
    """ADR-010: cohorts attach to courses via the ``cohort_courses``
    junction table, not via a ``course_id`` FK column. Pick any course
    the cohort is linked to so ``reconcile_entity`` can derive a
    source_locale + build a prompt context. A cohort attached to
    multiple courses with different source_locales is a rare edge —
    the first-link choice is deterministic (created_at ordering on the
    junction) and the cohort name is short, so re-translating against
    a different locale costs little.
    """
    from app.models.cohort import CohortCourse

    cohort_id = getattr(entity, "id", None)
    if cohort_id is None:
        return None
    course_id = (
        db.query(CohortCourse.course_id)
        .filter(CohortCourse.cohort_id == cohort_id)
        .order_by(CohortCourse.added_at)
        .limit(1)
        .scalar()
    )
    if not course_id:
        return None
    return db.query(Course).filter(Course.id == course_id).first()


def _resolve_course_via_rubric(db: Session, entity: Any) -> Course | None:
    """For a criterion: criterion -> rubric -> course."""
    rubric_id = getattr(entity, "rubric_id", None)
    if not rubric_id:
        return None
    return db.query(Course).join(Rubric, Rubric.course_id == Course.id).filter(Rubric.id == rubric_id).first()


def _resolve_course_via_criterion(db: Session, entity: Any) -> Course | None:
    """For a level: level -> criterion -> rubric -> course."""
    criterion_id = getattr(entity, "criterion_id", None)
    if not criterion_id:
        return None
    return (
        db.query(Course)
        .join(Rubric, Rubric.course_id == Course.id)
        .join(RubricCriterion, RubricCriterion.rubric_id == Rubric.id)
        .filter(RubricCriterion.id == criterion_id)
        .first()
    )


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
        resolve_course=_resolve_course_via_cohort_courses,
        build_context=lambda _co, c: f"Student cohort name in course «{c.title}»",
    ),
    # A rubric is the sentence a student is given for their mark. It was
    # the last reader-facing text with no translation path at all: a
    # German student read "Аргумент опирается на текст" and the level
    # they were given under it, in Russian, as the explanation of their
    # own grade.
    "rubric": EntityRegistration(
        entity_type="rubric",
        fields=(FieldSpec("title", "title"),),
        resolve_course=_resolve_course_via_attr("course_id"),
        build_context=lambda _r, c: f"Marking rubric in course «{c.title}»",
    ),
    "rubric_criterion": EntityRegistration(
        entity_type="rubric_criterion",
        fields=(FieldSpec("title", "title"), FieldSpec("description", "plain")),
        resolve_course=_resolve_course_via_rubric,
        build_context=lambda _c, c: f"One thing a marking rubric judges, in course «{c.title}»",
    ),
    "rubric_level": EntityRegistration(
        entity_type="rubric_level",
        # ``label`` is the column; ``title`` is what content_versions
        # calls a short heading, and the cohort entry above sets the
        # same precedent rather than growing the field vocabulary for
        # one synonym.
        fields=(FieldSpec("title", "title", model_attr="label"), FieldSpec("description", "plain")),
        resolve_course=_resolve_course_via_criterion,
        build_context=lambda _lv, c: f"One rung of a marking rubric criterion, in course «{c.title}»",
    ),
    # Phase 5c — Daily Challenge platform surface. Questions are
    # course-less by design (they're a platform-wide rotation, not
    # course content). ``reconcile_entity`` skips orphans, so the
    # standard "edit-triggers-translate" hook does NOT apply here —
    # the Daily Challenge editorial pipeline invokes
    # ``translate_entity_fields`` directly with ``source_locale``
    # read off ``daily_challenge_questions.source_locale``.
    #
    # We still register so:
    #   * the cv parity test passes (every entity_type referenced in
    #     ``ContentVersionEntityType`` has a registry row),
    #   * the ``ENTITY_MODEL`` table can route per-entity test
    #     parametrization,
    #   * ``resolve_for_display`` helpers that iterate the registry
    #     for "what fields are translatable on entity X?" continue to
    #     return correct answers for the daily challenge surfaces.
    "daily_challenge_question": EntityRegistration(
        entity_type="daily_challenge_question",
        fields=(
            FieldSpec("question_text", "quiz_question"),
            FieldSpec("explanation", "plain"),
        ),
        resolve_course=lambda _db, _q: None,  # platform-wide; no course
        build_context=lambda _q, _c: "Bible question for the Equip Daily Challenge.",
    ),
    "daily_challenge_option": EntityRegistration(
        entity_type="daily_challenge_option",
        fields=(FieldSpec("option_text", "quiz_option"),),
        resolve_course=lambda _db, _o: None,  # platform-wide; no course
        build_context=lambda _o, _c: "Answer option for an Equip Daily Challenge question.",
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
    "daily_challenge_question": DailyChallengeQuestion,
    "daily_challenge_option": DailyChallengeOption,
    "rubric": Rubric,
    "rubric_criterion": RubricCriterion,
    "rubric_level": RubricLevel,
}


# ---------------------------------------------------------------------------
# The single helper every write hook + tree-walker uses.
# ---------------------------------------------------------------------------


def entity_field_specs(
    db: Session,
    entity_type: EntityType,
    entity: object,
    source_locale: LocaleCode,
) -> list[TranslationFieldSpec]:
    """Return the translatable fields of ``entity`` with their source text
    and the language that text is actually in.

    Split out of ``reconcile_entity`` because publication needs the same
    answer for a different question. Translating asks "what do I send to
    the model"; the publication gate asks "what must exist in every
    locale before this course is servable". Both need the identical
    notion of which fields count and what language each one is in — a
    second implementation would be a second implementation that drifts.

    Empty and whitespace-only fields are dropped: there is nothing to
    translate and nothing to wait for.
    """
    reg = REGISTRY[entity_type]
    # Declared language of whatever owns this entity — the course for
    # course content, the question itself for a platform-wide Daily
    # Challenge row. Per-field detection below can still override it.
    declared: LocaleCode = normalize_locale(source_locale)

    # Phase 5e/5f: source text columns are dropped on several entities
    # (cohort, chapter_block, assignment, course_event, announcement,
    # quiz, quiz_question, quiz_option). ``getattr`` returns None for
    # those fields, so the author's text has to come from cv.
    #
    # It is read here at ANY locale, not at the course's declared one,
    # and that is the whole point. The reader-facing helper answers at
    # the display locale and returns None otherwise — correct for a
    # reader, catastrophic here. A teacher who pastes an English
    # paragraph into a Russian course has that paragraph filed under
    # ``en`` (``dual_write`` files by detected language, not by declared
    # one), so asking at ``ru`` got None, the field was dropped, and it
    # then existed for nobody: ``plan_course_tasks`` produced no task for
    # it, and ``course_translation_completeness`` required no locale for
    # it, so the publication gate — written precisely to stop a
    # half-translated course reaching the catalogue — counted the hole as
    # nothing at all. Measured: the same block authored in Russian
    # yielded three tasks; authored in English, zero tasks and zero gaps.
    #
    # Human rows only, and this is not a preference either: an mt row
    # answering here would make the pipeline translate its own output,
    # and a course would drift a language further from its author with
    # every pass.
    cv_source_texts: dict[str, tuple[str, LocaleCode] | None] = {}
    field_names_needing_cv: list[str] = [fs.name for fs in reg.fields if getattr(entity, fs.attr, None) is None]
    if field_names_needing_cv:
        cv_source_texts = _authored_texts(
            db,
            entity_type=entity_type,
            entity_id=str(entity.id),  # type: ignore[attr-defined]
            fields=field_names_needing_cv,
            preferred_locale=declared,
        )

    fields: list[TranslationFieldSpec] = []
    for fs in reg.fields:
        text = getattr(entity, fs.attr, None)
        authored_locale: LocaleCode | None = None
        if text is None:
            found = cv_source_texts.get(fs.name)
            if found is not None:
                text, authored_locale = found
        if text is None or not str(text).strip():
            continue
        # Per-field language detection: the entity's actual content
        # may be in a language different from the course's declared
        # source (e.g. a teacher who pastes an English chapter title
        # into a Russian-source course). The detector returns ``None``
        # on sub-threshold or no-signal input; in that case we fall
        # back to the course-level source so the existing behaviour
        # is preserved for ambiguous fields.
        # Three answers, in order of how much they know. The locale the
        # author's row is actually filed under is a fact; the detector is
        # a measurement of the text; the course's declared source is a
        # default. Preferring the filed locale also keeps this function
        # agreeing with the row it just read, which is what stops a field
        # from being planned as one language and stored as another.
        detected = detect_locale(str(text))
        field_source: LocaleCode = authored_locale or detected or declared
        fields.append(
            TranslationFieldSpec(
                field=fs.name,
                text=text,
                content_kind=fs.content_kind,
                source_locale=field_source,
            )
        )
    return fields


def _authored_texts(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    fields: list[str],
    preferred_locale: LocaleCode,
) -> dict[str, tuple[str, LocaleCode] | None]:
    """The human-written text for each field, and the language it is in.

    One query, and deliberately not the reader-facing resolver: that one
    answers "what may this person be shown", which is a different
    question from "what did the author write". Here the answer must
    exist whatever language it is in, because a field nobody can read in
    their own language is exactly the field that needs translating.

    Where a field has human rows in more than one locale — a hand
    translation alongside the original — the course's declared locale
    wins, then the earliest written. Both tie-breaks are arbitrary in
    isolation and matter only in that they are stable: the same field
    must not be planned from Russian on one tick and from English on the
    next.
    """
    from app.models.content_version import ContentVersion, ContentVersionStatus

    rows = (
        db.query(
            ContentVersion.field,
            ContentVersion.locale,
            ContentVersion.text,
            ContentVersion.created_at,
        )
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field.in_(fields),
            ContentVersion.origin == "human",
            ContentVersion.status == ContentVersionStatus.OK,
            ContentVersion.superseded_by.is_(None),
        )
        .all()
    )
    best: dict[str, tuple[str, LocaleCode]] = {}
    ranked: dict[str, tuple[int, datetime]] = {}
    for field, locale, text, created_at in rows:
        if not text or not str(text).strip():
            continue
        rank = (0 if locale == preferred_locale else 1, created_at)
        if field not in ranked or rank < ranked[field]:
            ranked[field] = rank
            best[field] = (text, normalize_locale(locale))
    return {field: best.get(field) for field in fields}


def reconcile_entity(
    db: Session,
    entity_type: EntityType,
    entity: object,
    *,
    provider: TranslationProvider | None = None,
    budget: TranslationBudget | None = None,
) -> OrchestratorReport:
    """Translate one entity into every locale ≠ its field's source locale.

    Idempotent: ``translate_entity_fields`` short-circuits unchanged
    fields via ``source_hash``, so re-calling on the same entity costs
    zero Gemini calls. Returns a per-entity report counting translated /
    skipped / failed / needs-review rows.

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
    course_source: LocaleCode = normalize_locale(course.source_locale)

    fields = entity_field_specs(db, entity_type, entity, course_source)
    if not fields:
        return OrchestratorReport()

    # Phase 5g: courses.title lives in cv. The fresh Course returned by
    # ``resolve_course`` is not guaranteed to have its runtime title
    # attribute attached — and every entity's ``build_context`` lambda
    # below reads ``c.title``. Without the hydration here, the lambda
    # raises AttributeError, the outer ``reconcile_entity_if_course_published``
    # try/except swallows it, and the entity silently stays
    # untranslated. Hydrate once so every lambda below is safe.
    from app.services.translation.resolve_for_display import populate_spine_texts

    populate_spine_texts(db, [course])

    context: str | None = None
    if reg.build_context is not None:
        context = reg.build_context(entity, course)

    return translate_entity_fields(
        db,
        entity_type=entity_type,
        entity_id=str(entity.id),  # type: ignore[attr-defined]
        # ``source_locale`` here is the entity-level fallback for any
        # field whose own ``source_locale`` is unset (couldn't be
        # detected). Per-field overrides set above in ``fields`` are
        # what actually drives the translation direction when the
        # entity's content drifts from the course's declared source.
        source_locale=course_source,
        fields=fields,
        context=context,
        provider=provider,
        budget=budget,
    )


__all__ = [
    "ENTITY_MODEL",
    "REGISTRY",
    "EntityRegistration",
    "FieldSpec",
    "entity_field_specs",
    "reconcile_entity",
]
