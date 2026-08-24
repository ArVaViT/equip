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

from fastapi import Depends, status

from app.api.dependencies import assert_course_owner, require_teacher
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.schemas.course import (
    CourseTranslationProgress,
    CourseTranslationResponse,
    TranslationGapSummary,
)
from app.services.course_service import get_course
from app.services.staged_edits import staged_status_for_course
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.course_pipeline import translate_course_content
from app.services.translation.queue import enqueue_course_translation
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

    **Visibility decision:** kept public. The response surface
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
    """Translate a course now — the "prepare for publication" action.

    This is what a teacher presses on a draft before sending it out. The
    pipeline does not touch drafts on its own (nobody is reading them, and
    translating text that is still being rewritten spends money on
    wording that will not survive), so a big course would otherwise do all
    of its work at the moment of publication and sit in ``publishing``
    for as long as that takes. Pressed here, ahead of time, publication
    becomes immediate.

    Authorization mirrors the rest of the course write surface — the owner
    or an admin can trigger it; everyone else gets a 404.

    With the queue enabled this hands the work to the worker and returns
    at once: a course of any size is hundreds of provider round trips, and
    a request that waits for them is a request that ends in 504 with the
    work half done and no way for the caller to tell. Poll
    ``GET /courses/{id}/translation-progress`` for the rest.
    """
    course = get_course(db, course_id)
    if not course:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    assert_course_owner(course, teacher, allow_admin=True)

    if not is_translation_enabled():
        # Surface the disabled state explicitly so the UI can render a
        # "translation provider not configured" hint instead of a
        # silent no-op.
        return CourseTranslationResponse(enabled=False)

    if settings.TRANSLATION_QUEUE_ENABLED:
        enqueue_course_translation(db, str(course.id), requested_by=teacher.id)
        return CourseTranslationResponse(enabled=True, queued=True)

    report = translate_course_content(db, course)
    return CourseTranslationResponse(
        translated=report.translated,
        skipped=report.skipped,
        failed=report.failed,
        enabled=True,
    )


@router.get("/{course_id}/translation-progress", response_model=CourseTranslationProgress)
def read_translation_progress(
    course_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> CourseTranslationProgress:
    """How much of this course exists in every language, and what is stuck.

    Answers two questions with one call, because a teacher asks them
    together:

    * *Can this go out?* — the same completeness the publication gate
      computes, so the button and the gate can never disagree.
    * *Where is my edit?* — for a course that is already live, the edits
      being held until their translations land, and how many of those
      will not resolve without a person looking at them.
    """
    course = get_course(db, course_id)
    if not course:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    assert_course_owner(course, teacher, allow_admin=True)

    completeness = course_translation_completeness(db, course)
    held = staged_status_for_course(db, course)

    return CourseTranslationProgress(
        course_id=str(course.id),
        status=str(course.status),
        required=completeness.required,
        present=completeness.present,
        is_complete=completeness.is_complete,
        by_locale=completeness.by_locale(),
        gaps=TranslationGapSummary(
            missing=len(completeness.by_reason("missing")),
            needs_review=len(completeness.by_reason("needs_review")),
            # Both failure reasons, because the teacher's question is
            # "what is stuck", and a row that has spent its retries is
            # the most stuck thing on the panel. Splitting the count
            # here would silently subtract those from a number the
            # frontend already renders.
            failed=len(completeness.by_reason("failed")) + len(completeness.by_reason("failed_permanent")),
        ),
        held_edits=len(held),
        blocked_edits=sum(1 for item in held if item.state == "blocked"),
        enabled=is_translation_enabled(),
    )
