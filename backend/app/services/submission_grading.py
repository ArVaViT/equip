"""Applying a mark to a submission — the one path, whatever produced the number.

A grade can now arrive two ways: a teacher typing a number, or a rubric adding
up the levels they chose. What happens *after* the number exists must not
depend on which: the same validation against the maximum, the same fields
written, the same notification to the student, the same audit row.

Two paths that each grade a submission drift the week after they are written,
and the drift is invisible — one of them quietly stops notifying, or stops
recording who marked it, and nobody notices until a student asks why they were
never told.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import status as http_status

from app.core.errors import ErrorCode, equip_error
from app.core.i18n import t
from app.services.audit_service import log_action
from app.services.notification_service import create_notification, notification_text
from app.services.translation.resolve_for_display import fetch_cv_entity_texts_with_fallback
from app.services.user_locale import preferred_locale_of

if TYPE_CHECKING:
    from uuid import UUID

    from fastapi import Request
    from sqlalchemy.orm import Session

    from app.models.assignment import Assignment, AssignmentSubmission


def apply_grade(
    db: Session,
    *,
    submission: AssignmentSubmission,
    assignment: Assignment,
    grade: int,
    feedback: str | None,
    new_status: str,
    teacher_id: UUID,
    source_locale: str | None,
    request: Request | None = None,
    source: str = "manual",
) -> None:
    """Write the mark, tell the student, record who did it.

    ``source`` distinguishes a typed number from one a rubric produced. It goes
    into the audit rather than into the grade — the mark is the same mark; how
    it was arrived at is a fact about the marking, and the grade history is
    where somebody asks that question six months later.
    """
    if grade > assignment.max_score:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            message=f"Grade ({grade}) cannot exceed max score ({assignment.max_score})",
            context={
                "resource_type": "submission",
                "submission_id": str(submission.id),
                "grade": grade,
                "max_score": assignment.max_score,
            },
        )

    submission.grade = grade
    submission.feedback = feedback
    submission.status = new_status
    submission.graded_by = teacher_id
    submission.graded_at = datetime.now(UTC)

    # The notification goes to the student, so it is written in the
    # student's language — not the course's. Those differ by design: the
    # whole point of the platform is that a German writes the course and
    # a Ukrainian takes it.
    reader_locale = preferred_locale_of(db, submission.student_id)
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="assignment",
        entity_ids=[str(assignment.id)],
        fields=["title"],
        display_locale=reader_locale,
        source_locale=source_locale or reader_locale,
    )
    title = texts.get((str(assignment.id), "title")) or t(reader_locale, "fallback.your_assignment")
    create_notification(
        db,
        user_id=submission.student_id,
        type="assignment_graded",
        title=t(reader_locale, "notif.assignment_graded.title"),
        message=t(
            reader_locale,
            "notif.assignment_graded.body",
            title=title,
            grade=str(grade),
            max_score=str(assignment.max_score),
        ),
        # …and the recipe, so the row can be read in another language
        # later. The assignment title is captured as it read at the
        # moment of grading; re-resolving it per request would be a
        # query per notification on the bell.
        i18n=notification_text(
            "notif.assignment_graded",
            title=title,
            grade=str(grade),
            max_score=str(assignment.max_score),
        ),
        link=None,
        metadata={"assignment_id": str(assignment.id), "submission_id": str(submission.id)},
    )

    db.commit()
    db.refresh(submission)
    log_action(
        db,
        teacher_id,
        "grade",
        "assignment_submission",
        str(submission.id),
        details={"grade": grade, "status": new_status, "source": source},
        request=request,
    )
