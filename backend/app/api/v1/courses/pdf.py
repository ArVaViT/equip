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
from app.models.course import CourseStatus
from app.models.enrollment import Enrollment
from app.models.user import UserRole
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.course_pdf import render_course_pdf
from app.services.course_service import get_course
from app.services.translation.resolve_for_display import (
    build_localized_course_response_with_tree,
    populate_spine_texts,
)

from ._router import router

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


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

    # Hydrate title / description / module + chapter titles at the
    # requested locale. The PDF renderer is locale-blind — it just
    # reads ``course.title`` / ``course.description`` /
    # ``module.title`` / ``chapter.title`` directly.
    display_locale: LocaleCode = normalize_locale(accept_language)
    # populate_spine_texts already bulk-hydrates every module's
    # title/description at the course's source locale (hydrate_modules
    # defaults to True), so no per-module hydration pass is needed.
    populate_spine_texts(db, [course])
    # build_localized_course_response_with_tree applies the overlay in
    # place via .title attribute hydration on each module + chapter.
    _ = build_localized_course_response_with_tree(db, course, display_locale)

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
