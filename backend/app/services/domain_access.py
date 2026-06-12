"""Pure domain access checks that don't depend on FastAPI's dependency
injection wiring.

The two helpers here used to live in ``app.api.dependencies``, which
made every service that wanted to assert "this course belongs to this
teacher" or "what's the course id for this chapter" import from the
api layer. That backwards arrow (service → api) violates the layer
hierarchy (api → service → model) and made the services harder to
unit-test in isolation.

Both functions are pure read paths (one in-memory check, one
single-query lookup). Neither is registered with FastAPI's
``Depends(...)`` — they're called as regular functions from inside
services and routes. Living in ``services/`` is the right home.

``app.api.dependencies`` re-exports both names so the existing route
code keeps working without churn; the canonical import path is now
``app.services.domain_access``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import status

from app.core.errors import ErrorCode, equip_error
from app.models.course import Chapter, Course, Module
from app.models.user import User, UserRole

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def assert_course_owner(
    course: Course,
    user: User,
    *,
    allow_admin: bool = True,
    detail: str = "You do not own this course",
) -> None:
    """Raise 403 unless ``user`` owns ``course`` (or is admin and allowed).

    Callers can override ``detail`` to return a more specific 403 message
    (e.g. "You can only approve certificates for your own courses"), which
    avoids wrapping this call in a ``try/except HTTPException`` block.

    For the non-raising form (predicate that returns ``bool``), use
    ``app.api.dependencies.is_owner_or_admin``.
    """
    if str(course.created_by) == str(user.id):
        return
    if allow_admin and user.role == UserRole.ADMIN.value:
        return
    raise equip_error(
        ErrorCode.AUTH_FORBIDDEN,
        status_code=status.HTTP_403_FORBIDDEN,
        message=detail,
    )


def resolve_chapter_course_id(db: Session, chapter_id: str) -> str:
    """Return the course_id for a chapter (single joined query). Raises 404.

    Used by services that take a ``chapter_id`` from a route param and
    need to look up the owning course to authorise — keeps the join
    inline so callers don't accidentally do it themselves and create an
    N+1 across the request.
    """
    row = (
        db.query(Module.course_id)
        .join(Chapter, Chapter.module_id == Module.id)
        .join(Course, Module.course_id == Course.id)
        .filter(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
            Module.deleted_at.is_(None),
            Course.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Chapter not found",
            context={"resource_type": "chapter", "resource_id": chapter_id},
        )
    return row[0]
