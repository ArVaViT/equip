"""Chapter write endpoints nested under ``/courses/{id}/modules/{id}``."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_teacher, verify_course_owner
from app.core.database import get_db
from app.core.sanitize import sanitize_string
from app.models.course import Chapter
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
    verify_course_owner(db, course_id, teacher.id, allow_admin=False)
    module = get_module(db, course_id, module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_id}' not found in course '{course_id}'",
        )
    if data.title:
        data.title = sanitize_string(data.title)
    created = create_chapter(db, module_id, data)
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
    verify_course_owner(db, course_id, teacher.id, allow_admin=False)
    chapter = get_chapter(db, course_id, module_id, chapter_id)
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter '{chapter_id}' not found in module '{module_id}'",
        )
    if data.title:
        data.title = sanitize_string(data.title)
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
    verify_course_owner(db, course_id, teacher.id, allow_admin=False)
    chapter = get_chapter(db, course_id, module_id, chapter_id)
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter '{chapter_id}' not found in module '{module_id}'",
        )
    delete_chapter(db, chapter)
