"""Admin diagnostic endpoint for Phase 2 dual-read mismatches.

When a structured warning fires in production (Datadog log search
for ``cv_compare_reason:text_differs`` or similar), ops needs to
inspect what the two stores actually have for that specific entity.
This endpoint does the comparison on demand for every translatable
field of one entity across all supported locales, returning the
full ``MismatchReport`` per (field, locale).

Admin-only. Does NOT mutate. Reads from both stores.

Example query:
    GET /api/v1/dual-read-diag/course/fce3337a-231f-4d21-a977-905bd6a2cc07

Returns one block per (field, locale) showing the comparator's
verdict plus both stores' current state. Useful for triaging
``TEXT_DIFFERS``, ``LOCALE_DIVERGED``, and ``NEW_ONLY`` alerts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.core.database import get_db
from app.models.announcement import Announcement
from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.cohort import Cohort
from app.models.course import Chapter, Course, Module
from app.models.course_event import CourseEvent
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.schemas.locale import LOCALE_CODES, normalize_locale
from app.services.content_versions import compare_resolved_text
from app.services.translation.resolve_for_display import fetch_overlay_triples_bulk

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User

router = APIRouter(prefix="/dual-read-diag", tags=["admin-diagnostics"])


_EntityType = Literal[
    "course",
    "module",
    "chapter",
    "chapter_block",
    "quiz",
    "quiz_question",
    "quiz_option",
    "assignment",
    "announcement",
    "course_event",
    "cohort",
]


class FieldDiag(BaseModel):
    field: str
    display_locale: str
    reason: str
    legacy_text_preview: str | None
    new_text_preview: str | None
    new_status: str | None
    new_recorded_locale: str | None


class EntityDiag(BaseModel):
    entity_type: str
    entity_id: str
    source_locale: str | None
    base_text_per_field: dict[str, str | None]
    diagnostics: list[FieldDiag]


# Map of (entity_type, translatable_field, model_attr) tuples. Cohort
# is the one entity where the cv-field name (`title`) doesn't equal
# the attribute name (`name`).
_FIELDS_BY_TYPE: dict[str, list[tuple[str, str]]] = {
    "course": [("title", "title"), ("description", "description")],
    "module": [("title", "title"), ("description", "description")],
    "chapter": [("title", "title")],
    "chapter_block": [("content", "content")],
    "quiz": [("title", "title"), ("description", "description")],
    "quiz_question": [("question_text", "question_text")],
    "quiz_option": [("option_text", "option_text")],
    "assignment": [("title", "title"), ("description", "description")],
    "announcement": [("title", "title"), ("content", "content")],
    "course_event": [("title", "title"), ("description", "description")],
    "cohort": [("title", "name")],
}


def _load_entity_and_source_locale(db: Session, entity_type: str, entity_id: str) -> tuple[object, str | None]:
    """Load the entity row + figure out its parent course source_locale.

    Returns (entity_object, source_locale). Source locale resolution
    walks the same path the registry uses — course owns its own, every
    other entity walks up to its parent course.
    """
    model_map: dict[str, type] = {
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
    model_cls = model_map.get(entity_type)
    if model_cls is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown entity_type {entity_type!r}")
    entity = db.query(model_cls).filter(model_cls.id == entity_id).one_or_none()  # type: ignore[attr-defined]
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity {entity_type}:{entity_id} not found",
        )
    # Resolve source_locale via parent course walk.
    if entity_type == "course":
        return entity, getattr(entity, "source_locale", None)
    course_id: str | None = None
    if entity_type == "module":
        course_id = getattr(entity, "course_id", None)
    elif entity_type == "chapter":
        module = db.query(Module).filter(Module.id == entity.module_id).one_or_none()
        course_id = module.course_id if module else None
    elif entity_type in ("chapter_block", "quiz"):
        chapter = db.query(Chapter).filter(Chapter.id == entity.chapter_id).one_or_none()
        if chapter is not None:
            module = db.query(Module).filter(Module.id == chapter.module_id).one_or_none()
            course_id = module.course_id if module else None
    elif entity_type == "quiz_question":
        quiz = db.query(Quiz).filter(Quiz.id == entity.quiz_id).one_or_none()
        if quiz is not None:
            chapter = db.query(Chapter).filter(Chapter.id == quiz.chapter_id).one_or_none()
            if chapter is not None:
                module = db.query(Module).filter(Module.id == chapter.module_id).one_or_none()
                course_id = module.course_id if module else None
    elif entity_type == "quiz_option":
        question = db.query(QuizQuestion).filter(QuizQuestion.id == entity.question_id).one_or_none()
        if question is not None:
            quiz = db.query(Quiz).filter(Quiz.id == question.quiz_id).one_or_none()
            if quiz is not None:
                chapter = db.query(Chapter).filter(Chapter.id == quiz.chapter_id).one_or_none()
                if chapter is not None:
                    module = db.query(Module).filter(Module.id == chapter.module_id).one_or_none()
                    course_id = module.course_id if module else None
    elif entity_type == "assignment":
        chapter = db.query(Chapter).filter(Chapter.id == entity.chapter_id).one_or_none()
        if chapter is not None:
            module = db.query(Module).filter(Module.id == chapter.module_id).one_or_none()
            course_id = module.course_id if module else None
    elif entity_type in ("announcement", "course_event"):
        course_id = getattr(entity, "course_id", None)
    # cohort: no parent course (M2M); source_locale stays None.
    source_locale = None
    if course_id:
        source_locale = db.query(Course.source_locale).filter(Course.id == course_id).scalar()
    return entity, source_locale


def _preview(text: str | None, *, limit: int = 200) -> str | None:
    """Trim long text to a previewable size for the response payload."""
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + f"…[truncated, total {len(text)} chars]"


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=EntityDiag,
    summary="Diagnose dual-read mismatches for one entity (admin-only)",
    responses={
        200: {"description": "Per-(field, locale) comparator verdict and both stores' state"},
        403: {"description": "Caller is not an admin"},
        404: {"description": "Entity not found"},
    },
)
def diagnose_entity(
    entity_type: _EntityType,
    entity_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EntityDiag:
    """Run the dual-read comparator for every translatable field of
    one entity across every supported locale and return the verdicts.

    Use after a Datadog alert fires for an interesting mismatch:
    paste the entity_type + entity_id from the log, hit this endpoint,
    inspect what cv vs ct actually have. Helps decide whether the
    mismatch is a bug to fix or a benign edge case to allow-list.
    """
    fields = _FIELDS_BY_TYPE.get(entity_type)
    if fields is None:  # pragma: no cover — Literal type already restricts callers
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown entity_type {entity_type!r}")

    entity, source_locale = _load_entity_and_source_locale(db, entity_type, entity_id)
    base_text_per_field: dict[str, str | None] = {}
    for cv_field, model_attr in fields:
        base_text_per_field[cv_field] = getattr(entity, model_attr, None)

    # Pre-fetch the legacy overlay rows in one query per field to mirror
    # the resolver's real behaviour. The diagnostic isn't on a hot path
    # — clarity beats batching.
    diagnostics: list[FieldDiag] = []
    for cv_field, _model_attr in fields:
        base = base_text_per_field[cv_field]
        for locale in LOCALE_CODES:
            display_locale = normalize_locale(locale)
            overlay = fetch_overlay_triples_bulk(
                db,
                [(entity_type, str(entity_id), cv_field)],
                display_locale,
            )
            # Reproduce ``pick_overlay_value``'s fallback semantics
            # without re-importing it (would create a circular module
            # dep — diag → resolve_for_display → diag if anyone ever
            # imports diag from resolve).
            overlay_text = overlay.get((entity_type, str(entity_id), cv_field))
            legacy_text: str | None
            entity_source: str = source_locale or "en"
            if overlay_text is not None:
                legacy_text = overlay_text
            elif entity_source == display_locale:
                legacy_text = base
            else:
                legacy_text = base
            report = compare_resolved_text(
                db,
                entity_type=entity_type,
                entity_id=str(entity_id),
                field=cv_field,
                source_locale=entity_source,
                display_locale=display_locale,
                base_source_text=base,
                legacy_text=legacy_text,
            )
            diagnostics.append(
                FieldDiag(
                    field=cv_field,
                    display_locale=display_locale,
                    reason=report.reason.value,
                    legacy_text_preview=_preview(report.legacy_text),
                    new_text_preview=_preview(report.new_text),
                    new_status=report.new_status,
                    new_recorded_locale=report.new_recorded_locale,
                )
            )
    return EntityDiag(
        entity_type=entity_type,
        entity_id=str(entity_id),
        source_locale=source_locale,
        base_text_per_field={k: _preview(v) for k, v in base_text_per_field.items()},
        diagnostics=diagnostics,
    )
