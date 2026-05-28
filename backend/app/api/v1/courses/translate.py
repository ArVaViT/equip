"""Manual translation backfill for already-published courses.

The publish/update hooks in ``crud.py`` and nested write endpoints already run
``translate_course_content`` when Gemini is configured. This endpoint lets a
teacher force a full pass (same logic as the hooks).

Safe to call repeatedly: unchanged sources short-circuit via ``source_hash``
(zero Gemini calls).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status

from app.api.dependencies import assert_course_owner, require_teacher
from app.core.database import get_db
from app.schemas.course import CourseTranslationResponse
from app.services.course_service import get_course
from app.services.translation.course_pipeline import translate_course_content
from app.services.translation.service import is_translation_enabled

from ._router import router

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User

logger = logging.getLogger(__name__)


@router.get("/_diag/translation-status")
def translation_status() -> dict:
    """Anonymous diagnostic: is the translation provider configured?

    Returns ``{"enabled": true/false, "provider": "gemini"}``. Doesn't
    expose the API key or any other secrets — only the boolean result of
    the env-var check that gates every translation entry point. Used to
    confirm prod has the env wired correctly after a deploy without
    having to authenticate as a teacher and POST against a real course.

    **Visibility decision (Phase 5t):** kept public. The response surface
    is two static keys; an authenticated teacher can already infer the
    same boolean from the ``enabled`` field of any ``POST /translate``
    response, so gating this would not actually reduce information
    disclosure and would only break the post-deploy smoke-test workflow
    (``curl api.equipbible.com/...`` from any laptop).
    """
    return {"enabled": is_translation_enabled(), "provider": "gemini"}


@router.post("/{course_id}/translate", response_model=CourseTranslationResponse)
def trigger_course_translation(
    course_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> CourseTranslationResponse:
    """Run the translation pipeline against an existing course.

    Authorization mirrors the rest of the course write surface — the owner
    or an admin can trigger it; everyone else gets a 404. The body returns
    a counter so the UI can render a "translated 2 fields" toast.
    """
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course '{course_id}' not found",
        )
    assert_course_owner(course, teacher, allow_admin=True)

    if not is_translation_enabled():
        # Surface the disabled state explicitly so the UI can render a
        # "translation provider not configured" hint instead of a
        # silent no-op.
        return CourseTranslationResponse(enabled=False)

    report = translate_course_content(db, course)
    return CourseTranslationResponse(
        translated=report.translated,
        skipped=report.skipped,
        failed=report.failed,
        enabled=True,
    )
