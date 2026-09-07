"""Chapter endpoints under ``/courses/{id}`` — with a module, or without one.

Two families of route reach the same rows.

``/courses/{c}/modules/{m}/chapters/...`` is the original shape, from
when a chapter could only exist inside a module. It still works, and the
web app still uses it; it will be retired once the editor moves.

``/courses/{c}/chapters/...`` is the shape the model now has: a chapter
belongs to its course, and a module is an optional heading over some of
them. This is what lets a teacher with four lessons write four lessons,
instead of inventing a module to put them in — which is what the first
teacher on production did, twice, before deleting the lessons.

Both families are owner-or-admin only. ``GET`` on a single chapter is
new: until now the web app fetched the whole module to read one chapter
out of it, because there was no way to ask for the chapter.
"""

from fastapi import Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_teacher, verify_course_owner
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.sanitize import sanitize_plain_text
from app.models.course import Chapter, Module
from app.models.user import User
from app.schemas.course import ChapterCreate, ChapterResponse, ChapterUpdate
from app.services.course_service import (
    create_chapter,
    delete_chapter,
    get_chapter,
    get_module,
    update_chapter,
)
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published

from ._router import router


def _module_of_course(db: Session, course_id: str, module_id: str) -> Module:
    """The live module ``module_id`` of ``course_id``, or 404.

    The course in the path is the whole check. A module id belonging to
    another course is not found *here*, and the answer says so without
    confirming that it exists somewhere else.
    """
    module = get_module(db, course_id, module_id)
    if not module:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Module '{module_id}' not found in course '{course_id}'",
            context={"resource_type": "module", "module_id": module_id, "course_id": course_id},
        )
    return module


def _chapter_or_404(db: Session, course_id: str, chapter_id: str, *, module_id: str | None = None) -> Chapter:
    chapter = get_chapter(db, course_id, chapter_id, module_id=module_id)
    if not chapter:
        where = f"module '{module_id}'" if module_id is not None else f"course '{course_id}'"
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Chapter '{chapter_id}' not found in {where}",
            context={
                "resource_type": "chapter",
                "chapter_id": chapter_id,
                "module_id": module_id,
                "course_id": course_id,
            },
        )
    return chapter


def _verify_regrouping(db: Session, course_id: str, data: ChapterUpdate) -> None:
    """Check the module a patch wants to move this chapter under.

    Only runs when the body actually carries ``module_id`` — an omitted
    key leaves the grouping alone, and ``null`` means "no group", which
    needs no target to exist.

    A module of another course is refused. This route is exactly where a
    teacher goes to fix a structure they got wrong, and a mistyped or
    stale id there would otherwise hand one of their lessons to a course
    they may not even own — a chapter whose ``module.course_id`` and own
    ``course_id`` disagree, which is the invariant every read now leans
    on. 404, like every other module lookup on these routes, rather than
    a validation error: the module is not in this course, and whether it
    is anywhere else is not this answer's business.
    """
    if "module_id" not in data.model_fields_set or data.module_id is None:
        return
    _module_of_course(db, course_id, data.module_id)


# ---------------------------------------------------------------------------
# The chapter's own course — no module in the path
# ---------------------------------------------------------------------------


@router.post(
    "/{course_id}/chapters",
    response_model=ChapterResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chapter_in_course(
    course_id: str,
    data: ChapterCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Chapter:
    """Create a lesson directly in the course, grouped by no module.

    ``order_index`` is course-global: omit it and the lesson lands after
    everything the course already has, modules included.
    """
    verify_course_owner(db, course_id, teacher.id)
    if data.title:
        data.title = sanitize_plain_text(data.title)
    created = create_chapter(db, None, data, course_id=course_id)
    reconcile_entity_if_course_published(db, "chapter", created)
    return created


@router.get("/{course_id}/chapters/{chapter_id}", response_model=ChapterResponse)
def get_chapter_of_course(
    course_id: str,
    chapter_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Chapter:
    """One chapter of the course, by id, whether or not a module groups it.

    There was no such endpoint before, so the web app fetched the whole
    module and picked the chapter out of it (``getModuleForEdit`` doing
    duty as "get chapter") — which cannot work for a chapter that has no
    module.

    An authoring read, owner or admin only, and it returns the teacher's
    own source text: ``chapters.title`` is the source-locale column, and
    the editor must see what it will be saving over rather than a
    translation of it. No ``Accept-Language`` overlay, deliberately —
    the reader-facing tree comes from ``GET /courses/{id}``.
    """
    verify_course_owner(db, course_id, teacher.id)
    return _chapter_or_404(db, course_id, chapter_id)


@router.put("/{course_id}/chapters/{chapter_id}", response_model=ChapterResponse)
def update_chapter_of_course(
    course_id: str,
    chapter_id: str,
    data: ChapterUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Chapter:
    """Edit a chapter, and move it between groups.

    ``{"module_id": null}`` takes the lesson out of its module and
    leaves it in the course; ``{"module_id": "<id>"}`` puts it under
    that heading. The module must be one of this course's.
    """
    verify_course_owner(db, course_id, teacher.id)
    chapter = _chapter_or_404(db, course_id, chapter_id)
    _verify_regrouping(db, course_id, data)
    if data.title:
        data.title = sanitize_plain_text(data.title)
    updated = update_chapter(db, chapter, data)
    reconcile_entity_if_course_published(db, "chapter", updated)
    return updated


@router.delete("/{course_id}/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_chapter_of_course(
    course_id: str,
    chapter_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    verify_course_owner(db, course_id, teacher.id)
    delete_chapter(db, _chapter_or_404(db, course_id, chapter_id))


# ---------------------------------------------------------------------------
# Through the module — the original shape, still served
# ---------------------------------------------------------------------------


@router.post(
    "/{course_id}/modules/{module_id}/chapters",
    response_model=ChapterResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_chapter(
    course_id: str,
    module_id: str,
    data: ChapterCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Chapter:
    verify_course_owner(db, course_id, teacher.id)
    _module_of_course(db, course_id, module_id)
    if data.title:
        data.title = sanitize_plain_text(data.title)
    created = create_chapter(db, module_id, data, course_id=course_id)
    reconcile_entity_if_course_published(db, "chapter", created)
    return created


@router.put(
    "/{course_id}/modules/{module_id}/chapters/{chapter_id}",
    response_model=ChapterResponse,
)
def update_existing_chapter(
    course_id: str,
    module_id: str,
    chapter_id: str,
    data: ChapterUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Chapter:
    verify_course_owner(db, course_id, teacher.id)
    chapter = _chapter_or_404(db, course_id, chapter_id, module_id=module_id)
    _verify_regrouping(db, course_id, data)
    if data.title:
        data.title = sanitize_plain_text(data.title)
    updated = update_chapter(db, chapter, data)
    reconcile_entity_if_course_published(db, "chapter", updated)
    return updated


@router.delete(
    "/{course_id}/modules/{module_id}/chapters/{chapter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_chapter(
    course_id: str,
    module_id: str,
    chapter_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    verify_course_owner(db, course_id, teacher.id)
    delete_chapter(db, _chapter_or_404(db, course_id, chapter_id, module_id=module_id))
