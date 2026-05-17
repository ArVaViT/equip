"""Read-only readiness report for a course.

Lives under ``GET /courses/{course_id}/readiness``. Same authorization
rule as the rest of the course-edit surface: only the course owner or
an admin can request the report — readiness exposes structural hints
(e.g. "Chapter X is missing content") that a stranger shouldn't see.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session  # noqa: TC002  (used at runtime by Depends)

from app.api.dependencies import assert_course_owner, require_teacher
from app.core.database import get_db
from app.models.user import User  # noqa: TC001  (used at runtime by Depends)
from app.schemas.course_readiness import (
    ReadinessAction,
    ReadinessCheck,
    ReadinessReport,
    ReadinessSubject,
)
from app.services.course_readiness import compute_readiness
from app.services.course_service import get_course

from ._router import router

logger = logging.getLogger(__name__)


@router.get("/{course_id}/readiness", response_model=ReadinessReport)
def read_course_readiness(
    course_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ReadinessReport:
    """Return the readiness checklist for one course."""
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course '{course_id}' not found",
        )
    # Reuse the existing owner-or-admin gate. The flag is named
    # ``allow_admin`` but the helper actually permits both owners and
    # admins by default; we pass ``True`` explicitly for clarity.
    assert_course_owner(course, teacher, allow_admin=True)

    report = compute_readiness(db, course)

    # Translate dataclasses → Pydantic. Direct field mapping; no
    # ``from_attributes`` magic since the names align 1:1.
    return ReadinessReport(
        course_id=report.course_id,
        total=report.total,
        passing=report.passing,
        critical_failing=report.critical_failing,
        score=report.score,
        checks=[
            ReadinessCheck(
                id=c.id,
                severity=c.severity,
                passed=c.passed,
                message_key=c.message_key,
                subject=(
                    ReadinessSubject(type=c.subject.type, id=c.subject.id, title=c.subject.title)
                    if c.subject is not None
                    else None
                ),
                action=(ReadinessAction(type=c.action.type, params=c.action.params) if c.action is not None else None),
            )
            for c in report.checks
        ],
    )
