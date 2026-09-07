"""Pure domain access checks that don't depend on FastAPI's dependency
injection wiring.

The first two helpers here used to live in ``app.api.dependencies``,
which made every service that wanted to assert "this course belongs to
this teacher" or "what's the course id for this chapter" import from
the api layer. That backwards arrow (service → api) violates the layer
hierarchy (api → service → model) and made the services harder to
unit-test in isolation.

Everything here is a pure read path (an in-memory check, single-query
lookups, one filter expression). Nothing is registered with FastAPI's
``Depends(...)`` — they're called as regular functions from inside
services and routes. Living in ``services/`` is the right home.

``app.api.dependencies`` re-exports ``resolve_chapter_course_id`` so
the existing route code keeps working without churn; the canonical
import path is ``app.services.domain_access``. The chapter lookups
read ``chapters.course_id`` directly: a chapter belongs to its course,
and the module is an optional grouping it may or may not name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import status
from sqlalchemy import or_

from app.core.errors import ErrorCode, equip_error
from app.models.course import Chapter, Course, Module
from app.models.user import User, UserRole

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.sql import ColumnElement


def chapter_module_is_live_or_absent() -> ColumnElement[bool]:
    """The module's say over its chapters' visibility, kept explicit.

    While every chapter reached its course through ``INNER JOIN modules
    ... WHERE modules.deleted_at IS NULL``, soft-deleting a module hid
    all of its chapters on every chapter-scoped route (blocks, quizzes,
    assignments, progress). The chapter now joins its course directly
    and the module is an ``OUTER JOIN`` — which would have silently
    dropped that rule along with the inner join. This predicate carries
    it on purpose: a chapter that names a module is visible only while
    that module is live; a chapter that names none has no module to be
    hidden by.

    Use after ``.outerjoin(Module, Chapter.module_id == Module.id)``.
    Whether a deleted module should keep hiding its chapters once the
    module is optional is a product decision for the step that makes it
    optional, not a side effect of this one.
    """
    return or_(Chapter.module_id.is_(None), Module.deleted_at.is_(None))


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
    """Return the course_id for a chapter (single query). Raises 404.

    Used by services that take a ``chapter_id`` from a route param and
    need to look up the owning course to authorise — keeps the lookup
    inline so callers don't accidentally do it themselves and create an
    N+1 across the request.

    The answer is ``chapters.course_id`` itself; the course is joined
    only to hide chapters of soft-deleted courses, the module only for
    ``chapter_module_is_live_or_absent``.
    """
    row = (
        db.query(Chapter.course_id)
        .join(Course, Chapter.course_id == Course.id)
        .outerjoin(Module, Chapter.module_id == Module.id)
        .filter(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
            chapter_module_is_live_or_absent(),
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


def course_source_locale_for_chapter(db: Session, chapter_id: str) -> str | None:
    """The language the chapter's course was written in, or ``None`` for
    an unknown chapter.

    Two kinds of caller need it: the editors (blocks, assignments,
    quizzes), as the dual-write fallback when a short field cannot be
    classified by the detector, and the grading queue, which must be
    able to show a teacher text that exists in no other language than
    the author's. Soft-deleted rows are not filtered here — the callers
    have already passed the access gate for the chapter, and the fallback
    locale of a course does not change when it is binned.
    """
    return (
        db.query(Course.source_locale)
        .join(Chapter, Chapter.course_id == Course.id)
        .filter(Chapter.id == chapter_id)
        .scalar()
    )
