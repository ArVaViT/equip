"""Module write endpoints nested under a course."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_teacher, verify_course_owner
from app.core.database import get_db
from app.models.course import Module
from app.models.user import User
from app.schemas.course import ModuleCreate, ModuleResponse, ModuleUpdate
from app.services.course_service import (
    create_module,
    delete_module,
    get_module,
    update_module,
)
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published

from ._router import router


@router.post(
    "/{course_id}/modules",
    response_model=ModuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_module(
    course_id: str,
    data: ModuleCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Module:
    verify_course_owner(db, course_id, teacher.id, allow_admin=False)
    created = create_module(db, course_id, data)
    reconcile_entity_if_course_published(db, "module", created)
    return created


@router.put("/{course_id}/modules/{module_id}", response_model=ModuleResponse)
def update_existing_module(
    course_id: str,
    module_id: str,
    data: ModuleUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Module:
    verify_course_owner(db, course_id, teacher.id, allow_admin=False)
    module = get_module(db, course_id, module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_id}' not found in course '{course_id}'",
        )
    updated = update_module(db, module, data)
    reconcile_entity_if_course_published(db, "module", updated)
    return updated


@router.delete("/{course_id}/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_module(
    course_id: str,
    module_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    verify_course_owner(db, course_id, teacher.id, allow_admin=False)
    module = get_module(db, course_id, module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_id}' not found in course '{course_id}'",
        )
    delete_module(db, module)
