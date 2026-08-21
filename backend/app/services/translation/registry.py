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

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

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
    from collections.abc import Callable, Sequence
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
    #: Context that needs a query of its own — an answer option has to
    #: be told which question it answers, and the question's text lives
    #: in ``content_versions`` rather than on the row.
    build_context_with_db: Callable[[Session, Any, Course | None], str | None] | None = None


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


def _block_context(db: Session, block: Any, course: Course | None) -> str | None:
    """A lesson block, and enough of what surrounds it to judge by.

    A block is translated on its own and, until now, described only as
    "HTML fragment from course X". That is enough to translate the words
    and not enough to check the result, which is the half that matters:
    an editor reading a paragraph in isolation cannot see that its
    teaching point has been turned around, and a translator cannot see
    that the term it is choosing was already chosen differently one
    paragraph earlier.

    Production has both. "Значение задаёт употребление" — usage
    determines meaning — came back as its own opposite in German while
    English and Ukrainian got it right, and the sentence that settles it
    is in the next block. The Sanhedrin is three different German words
    across one course, "Проверьте себя" is four, because each was decided
    alone.

    So the block before it comes along, trimmed: enough to place the
    text, not so much that it becomes the thing being translated. The
    prompt already tells the model that context is not to be translated.
    """
    from app.models.chapter_block import ChapterBlock
    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    # ``course.title`` is hydrated from content_versions rather than
    # stored on the row, and a caller that has not hydrated it raises
    # AttributeError — which the pipeline hook swallows, leaving the
    # entity silently untranslated. The registry has a comment about
    # exactly this trap; getattr keeps this path out of it.
    title = getattr(course, "title", None) if course is not None else None
    course_line = f"Lesson block from the course «{title}»" if title else "Lesson block"
    chapter_id = getattr(block, "chapter_id", None)
    order_index = getattr(block, "order_index", None)
    if chapter_id is None or order_index is None:
        return course_line

    previous = (
        db.query(ChapterBlock)
        .filter(
            ChapterBlock.chapter_id == chapter_id,
            ChapterBlock.order_index < order_index,
        )
        .order_by(ChapterBlock.order_index.desc())
        .first()
    )
    if previous is None:
        return course_line

    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="chapter_block",
        entity_ids=[str(previous.id)],
        fields=["content"],
        display_locale="ru",
        source_locale="ru",
        fallback="source_then_any",
    )
    before = texts.get((str(previous.id), "content"))
    if not before:
        return course_line

    stripped = _PLAIN_TEXT.sub(" ", before).strip()
    stripped = " ".join(stripped.split())
    if not stripped:
        return course_line
    return f"{course_line}. The paragraph immediately before it reads: {stripped[:400]}"


def _question_text_for_option(db: Session, option: Any, *, entity_type: str) -> str | None:
    """The question an answer option belongs to, in the source language."""
    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    question_id = getattr(option, "question_id", None)
    if not question_id:
        return None
    field = "question_text"
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type=entity_type,
        entity_ids=[str(question_id)],
        fields=[field],
        display_locale="ru",
        source_locale="ru",
        fallback="source_then_any",
    )
    return texts.get((str(question_id), field))


def _option_context(db: Session, option: Any, course: Course | None) -> str | None:
    """Tell the translator what this option is an answer to.

    An answer option is a fragment, and a fragment has to agree with the
    sentence that introduces it. Translated alone — which is how it was
    translated, with the context line "Answer option for a Bible-study
    quiz question" — the model had no way to know whether the stem ends
    in a colon and governs a case, so it picks the dictionary form.
    An editor counted the damage across one course: eight German options
    that do not read with their stem, nine English, four Ukrainian.
    Russian keeps the case in all four options every time, because the
    author wrote them together.

    So the question comes along — and the instruction that goes with it
    matters more than the question does. Given the question and nothing
    else, the model helpfully repairs the wrong answers: measured on the
    corpus, 18 question-and-language pairs came back with a distractor
    rewritten into a character-identical copy of the correct answer, and
    about a dozen more had a name swapped for the right one. Those
    questions cannot be answered by anybody. The Russian source has no
    duplicate options anywhere in 128 questions; every one of them was
    introduced in translation.

    So the question is passed for grammar, and the model is told twice
    that a wrong answer is wrong on purpose.
    """
    question = _question_text_for_option(db, option, entity_type="quiz_question")
    if not question:
        # The stem could not be fetched, so all that is left is the
        # course — which is enough to say what the subject is, and is
        # what every other entity's context line says. It used to read
        # "Answer option for a Bible-study quiz question", which is a
        # claim about the subject rather than a report of it: on a
        # module about church finance it is simply false, and the model
        # is entitled to believe it.
        title = getattr(course, "title", None) if course is not None else None
        return (
            f"Answer option for a quiz question in the course «{title}»"
            if title
            else "Answer option for a quiz question."
        )
    return (
        "This is one answer option to the question below. The question is "
        "here for GRAMMAR ONLY: make the option agree with it — the case, "
        "preposition and sentence shape it requires.\n"
        "Most options are wrong answers on purpose. Translate what this "
        "option says, however wrong it is. Do not correct it, do not make "
        "it agree with the facts, and never let it drift towards the "
        "right answer: a quiz whose wrong answers have been fixed cannot "
        "be answered at all.\n"
        "Do not translate the question itself.\n"
        f"Question: {question}"
    )


def _daily_challenge_option_context(db: Session, option: Any, _course: Course | None) -> str | None:
    question = _question_text_for_option(db, option, entity_type="daily_challenge_question")
    if not question:
        return "Answer option for a daily Bible question."
    return (
        "This is one answer option to the question below. The question is "
        "here for GRAMMAR ONLY: make the option agree with it.\n"
        "Most options are wrong answers on purpose. Translate what this "
        "option says, however wrong it is — do not correct it and never "
        "let it drift towards the right answer.\n"
        "Do not translate the question itself.\n"
        f"Question: {question}"
    )


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
        build_context_with_db=_block_context,
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
        build_context_with_db=_option_context,
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
        build_context_with_db=_daily_challenge_option_context,
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


def _is_blank(value: object) -> bool:
    """No text here — whether that is ``None``, ``""`` or three spaces.

    One predicate rather than three spellings, because the difference
    between ``None`` and ``""`` on a translatable field is an artefact of
    which read path last touched the object, and nothing this module
    should ever act on. See ``entity_field_specs``.
    """
    return value is None or not str(value).strip()


def entity_field_specs(
    db: Session,
    entity_type: EntityType,
    entity: object,
    source_locale: LocaleCode,
    authored: AuthoredTexts | None = None,
) -> list[TranslationFieldSpec]:
    """Return the translatable fields of ``entity`` with their source text
    and the language that text is actually in.

    Split out of ``reconcile_entity`` because publication needs the same
    answer for a different question. Translating asks "what do I send to
    the model"; the publication gate asks "what must exist in every
    locale before this course is servable". Both need the identical
    notion of which fields count and what language each one is in — a
    second implementation would be a second implementation that drifts.

    A field with no text anywhere — not on the model, not in an active
    human ``content_versions`` row — is dropped: there is nothing to
    translate and nothing to wait for. That is what makes "a required
    (field, locale) pair whose source does not exist" impossible to
    construct: the requirement and the plan are both built from what this
    function returns, so a field with no source produces neither.

    The answer must not depend on whether the caller hydrated the entity
    first. See the note on blankness below — that dependency is exactly
    how the two callers came to disagree.
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
    #
    # Asked for EVERY field, not only the ones whose model attribute
    # happens to be ``None`` — and that "happens to be" is the whole
    # story of 2026-08-20.
    #
    # ``populate_spine_texts`` resolves ``course.title`` for display at
    # ONE locale and writes the answer onto the instance. Whether a walk
    # sees a column, a display resolution, or nothing at all is therefore
    # a property of the *caller*, not of the entity: ``plan_course_tasks``
    # walks a course fetched through ``get_course``, which hydrates;
    # ``course_translation_completeness`` walks the one the sweep selected
    # itself, which does not. Two callers, two answers, same field — and a
    # disagreement between the plan and the check is a gap nothing can
    # close, because the check demands what the plan never produces.
    #
    # It bit twice in the same course, in opposite directions:
    #
    # * No row at ``ru`` at all, so the hydration wrote ``""``. The
    #   un-hydrated check read the author's English row and required
    #   de/ru/uk; the hydrated plan read ``""`` as "the author wrote
    #   nothing" and produced no task. Measured: 645 jobs, one every two
    #   minutes for a day, every one finishing ``done`` with nothing
    #   written — and since the sweep's queue was never empty, the
    #   idle-tick Daily Challenge sweep never ran once. 2,988 of its rows
    #   sat at pipeline generation 2 while the course tree reached 10.
    # * Then, the moment a Russian translation of that English title
    #   existed, the hydration resolved ``title`` to the machine's own
    #   Russian and handed it back as the source. The plan would have
    #   re-translated the pipeline's output and filed it under a hash the
    #   check does not expect — the same loop again, one generation
    #   further from the author every pass.
    #
    # So the author's text is read from the author's rows, always, and
    # the model attribute is the fallback rather than the other way
    # round. The answer is then a function of the database alone, which
    # is the only way two callers can be relied on to agree.
    #
    # The model attribute still answers for an entity that has a column
    # and no cv row yet — a just-created row inside the same transaction,
    # a fixture, a Daily Challenge question. It costs one indexed query
    # per entity, which is what the majority of entity types already paid
    # here: their columns were dropped in Phase 5e/5f (cohort,
    # chapter_block, assignment, course_event, announcement, quiz,
    # quiz_question, quiz_option) and in Phase 5g (course, module).
    # One statement for a walk, one for a single entity.
    #
    # Reading the author's rows for every field is what makes this
    # function's answer a property of the database rather than of who
    # hydrated the entity — and that is not negotiable, it is what stops
    # the check and the plan disagreeing. But it is one round trip per
    # entity, and ``course_translation_completeness`` walks every entity
    # of a course on every idle worker tick.
    #
    # Measured against production, 2026-08-20: three live courses took
    # 95.6 s to check, against a 180 s tick that reserves 96 s for one
    # in-flight model call. Nothing was left. The Daily Challenge pool
    # sweep runs after the course sweep on the same budget, so it could
    # not afford a single call, and 2,983 of its rows stayed at pipeline
    # generation 2 while the course tree finished at 10 — a third of the
    # corpus frozen by a check that had spent the minute it needed.
    #
    # (The language detector was the other suspect and was measured out:
    # 0.05 ms per field, 0.1 s for the whole walk. It is round trips.)
    #
    # So a caller that is about to walk many entities reads them all in
    # one statement and passes the result down. A caller with one entity
    # passes nothing and gets exactly the query it got before — saving a
    # single edited block must not read a whole course.
    cv_source_texts: dict[str, tuple[str, LocaleCode] | None]
    if authored is not None:
        prefetched = authored.get((entity_type, str(entity.id)))  # type: ignore[attr-defined]
        cv_source_texts = dict(prefetched) if prefetched is not None else {}
    else:
        cv_source_texts = _authored_texts(
            db,
            entity_type=entity_type,
            entity_id=str(entity.id),  # type: ignore[attr-defined]
            fields=[fs.name for fs in reg.fields],
            preferred_locale=declared,
        )

    fields: list[TranslationFieldSpec] = []
    for fs in reg.fields:
        # The author's row first, the model attribute second. Blank on
        # either side counts as absent: the difference between ``None``,
        # ``""`` and three spaces is an artefact of which read path last
        # touched the object, never a statement about the text.
        authored_locale: LocaleCode | None = None
        text: Any | None
        found = cv_source_texts.get(fs.name)
        if found is not None:
            text, authored_locale = found
        else:
            text = getattr(entity, fs.attr, None)
        if _is_blank(text):
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


#: Tags stripped when a neighbouring block is quoted as context — the
#: model is being shown what the lesson is talking about, not asked to
#: reproduce its markup.
_PLAIN_TEXT: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")


#: How many entity ids go into one ``IN (…)``. A course tree fits in
#: one; the bound is here so a platform-wide walk cannot build a
#: statement with ten thousand parameters.
_AUTHORED_CHUNK: Final[int] = 500


#: What a walk hands down: every entity's author rows, read once.
#: Keyed ``(entity_type, entity_id)``, valued exactly as
#: ``_authored_texts`` returns.
AuthoredTexts = dict[tuple[str, str], dict[str, tuple[str, "LocaleCode"] | None]]


def authored_texts_for_entities(
    db: Session,
    entities: Sequence[tuple[str, str]],
    *,
    preferred_locale: LocaleCode,
) -> AuthoredTexts:
    """``_authored_texts`` for many entities, in one statement.

    Same answer, same tie-breaks, same shape — the only difference is
    how many round trips it costs. A walk that used to spend one per
    entity now spends one per walk; a caller with a single entity has no
    reason to come here and keeps using ``_authored_texts`` directly.

    Chunked, because ``entity_id IN (…)`` with several thousand
    parameters is its own kind of slow, and a course tree is comfortably
    inside one chunk.
    """
    from app.models.content_version import ContentVersion, ContentVersionStatus

    result: AuthoredTexts = {}
    if not entities:
        return result

    by_type: dict[str, list[str]] = {}
    for entity_type, entity_id in entities:
        by_type.setdefault(entity_type, []).append(entity_id)

    for entity_type, ids in by_type.items():
        if entity_type not in REGISTRY:
            continue
        reg = REGISTRY[entity_type]
        field_names = [fs.name for fs in reg.fields]
        rows: list[Any] = []
        for start in range(0, len(ids), _AUTHORED_CHUNK):
            chunk = ids[start : start + _AUTHORED_CHUNK]
            rows.extend(
                db.query(
                    ContentVersion.entity_id,
                    ContentVersion.field,
                    ContentVersion.locale,
                    ContentVersion.text,
                    ContentVersion.created_at,
                )
                .filter(
                    ContentVersion.entity_type == entity_type,
                    ContentVersion.entity_id.in_(chunk),
                    ContentVersion.field.in_(field_names),
                    ContentVersion.origin == "human",
                    ContentVersion.status == ContentVersionStatus.OK,
                    ContentVersion.superseded_by.is_(None),
                )
                .all()
            )

        best: dict[tuple[str, str], tuple[str, LocaleCode]] = {}
        ranked: dict[tuple[str, str], tuple[int, datetime]] = {}
        for entity_id, field, locale, text, created_at in rows:
            if not text or not str(text).strip():
                continue
            key = (entity_id, field)
            rank = (0 if locale == preferred_locale else 1, created_at)
            if key not in ranked or rank < ranked[key]:
                ranked[key] = rank
                best[key] = (text, normalize_locale(locale))

        for entity_id in ids:
            result[(entity_type, entity_id)] = {name: best.get((entity_id, name)) for name in field_names}
    return result


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
    if reg.build_context_with_db is not None:
        context = reg.build_context_with_db(db, entity, course)
    elif reg.build_context is not None:
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
