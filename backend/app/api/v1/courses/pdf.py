"""PDF export endpoint for a single course.

Returns a printable PDF rendering of the course outline + chapter
text content. Owner-or-admin OR enrolled-student gets through; anyone
else sees 403 (same gate as the existing teacher/student detail
views). The PDF is generated on demand — no caching layer yet, since
courses change frequently enough that a stale PDF would be
embarrassing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, Header, Response
from fastapi.responses import Response as RawResponse

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.chapter_block import ChapterBlock
from app.models.course import Course, CourseStatus
from app.models.enrollment import Enrollment
from app.models.user import UserRole
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.course_pdf import render_course_pdf
from app.services.course_service import get_course
from app.services.translation.resolve_for_display import (
    localize_chapter_block_rows,
    populate_spine_texts,
)

from ._router import router

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


def _attach_localized_blocks(db: Session, course: Course, *, display_locale: LocaleCode) -> None:
    """Give every chapter in the tree a ``blocks`` list the renderer can read.

    Two things were wrong here at once. ``Chapter`` has no ``blocks``
    relationship, so the renderer's ``getattr(chapter, "blocks", None)
    or []`` was always empty — the export had never contained a line of
    lesson text, in any language. And ``chapter_blocks.content`` was
    dropped in Phase 5e2, so even with the rows in hand the content has
    to come from ``content_versions``.

    One query for the blocks, one bulk resolve for their text, at the
    reader's language. A block with nothing in this language gets ``""``
    and the renderer prints nothing for it.
    """
    chapters = [chapter for module in course.modules for chapter in module.chapters]
    if not chapters:
        return
    rows = (
        db.query(ChapterBlock)
        .filter(ChapterBlock.chapter_id.in_([str(c.id) for c in chapters]))
        .order_by(ChapterBlock.order_index)
        .all()
    )
    resolved = localize_chapter_block_rows(
        db,
        rows,
        display_locale=display_locale,
        source_locale=normalize_locale(course.source_locale),
    )
    content_by_id = {str(row.id): (row.content or "") for row in resolved}
    by_chapter: dict[str, list[ChapterBlock]] = {}
    for block in rows:
        block.content = content_by_id.get(str(block.id), "")  # type: ignore[attr-defined]
        by_chapter.setdefault(str(block.chapter_id), []).append(block)
    for chapter in chapters:
        chapter.blocks = by_chapter.get(str(chapter.id), [])  # type: ignore[attr-defined]


@router.get(
    "/{course_id}/export.pdf",
    summary="Download the course as a printable PDF",
    response_class=RawResponse,
    responses={
        200: {
            "description": "PDF stream of the course (title + outline + chapter text).",
            "content": {"application/pdf": {}},
        },
        403: {"description": "Caller is not the owner, an admin, or an enrolled student."},
        404: {"description": "Course not found or soft-deleted."},
    },
)
def export_course_pdf(
    course_id: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RawResponse:
    course = get_course(db, course_id)
    if course is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            message="Course not found",
            context={"resource_type": "course", "resource_id": course_id},
        )

    # Visibility: owner, admin, OR enrolled student. Anyone else sees
    # 403 — the export is not a public catalog read.
    is_owner = str(course.created_by) == str(current_user.id)
    is_admin = current_user.role == UserRole.ADMIN.value
    is_enrolled = (
        db.query(Enrollment)
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_id == course_id,
        )
        .first()
        is not None
    )
    if not (is_owner or is_admin or is_enrolled):
        # Mirror the catalog detail's unpublished-course leak guard:
        # unpublished courses 404 to non-owner non-admin so the export
        # endpoint doesn't tell an attacker the course exists.
        if course.status != CourseStatus.PUBLISHED:
            raise equip_error(
                ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                message="Course not found",
                context={"resource_type": "course", "resource_id": course_id},
            )
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=403,
            message="You must be enrolled to export this course",
            context={"resource_type": "course", "resource_id": course_id},
        )

    # The renderer is locale-blind: it reads ``course.title``,
    # ``module.title``, ``chapter.title`` and ``block.content`` straight
    # off the ORM objects. Everything locale-aware has to happen here.
    display_locale: LocaleCode = normalize_locale(accept_language)

    # Titles, at the reader's language rather than the author's. This
    # used to hydrate at the course's source locale and then call
    # ``build_localized_course_response_with_tree`` for its "side
    # effects" — but that function builds fresh Pydantic objects and
    # deliberately never writes back to the ORM, so the export came out
    # in the author's language whoever asked for it.
    populate_spine_texts(db, [course], display_locale=display_locale)

    # Lesson bodies. ``chapter_blocks.content`` was dropped in Phase
    # 5e2, so ``getattr(block, "content", None)`` — which is what the
    # renderer does — was ``None`` for every block: the export had been
    # shipping with no lesson text in it at all, in any language.
    _attach_localized_blocks(db, course, display_locale=display_locale)

    pdf_bytes = render_course_pdf(course)

    safe_title = "".join(c for c in (course.title or "") if c.isascii() and (c.isalnum() or c in " -_"))[:50].strip()
    if not safe_title:
        safe_title = str(course_id)[:8]
    filename = f"{safe_title}.pdf"

    return RawResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "Vary": "Accept-Language",
        },
    )
