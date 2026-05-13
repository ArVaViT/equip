"""Enrollment endpoints: status probe + enroll."""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.cohort import Cohort, CohortCourse
from app.models.enrollment import Enrollment
from app.models.user import User
from app.schemas.course import EnrollmentResponse
from app.services.audit_service import log_action
from app.services.course_service import enroll_user_in_course, get_course

from ._router import router


class EnrollRequest(BaseModel):
    cohort_id: str | None = None


@router.get("/{course_id}/enrollment-status")
def get_enrollment_status(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Lightweight yes/no endpoint used by CourseDetail so the page does not have
    # to load the full ``/users/me/courses`` payload just to check whether the
    # viewer is enrolled. One indexed PK lookup on (user_id, course_id).
    enrollment = (
        db.query(Enrollment).filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id).first()
    )
    if not enrollment:
        return {"enrolled": False, "enrollment": None}
    return {
        "enrolled": True,
        "enrollment": {
            "id": str(enrollment.id),
            "user_id": str(enrollment.user_id),
            "course_id": str(enrollment.course_id),
            "cohort_id": str(enrollment.cohort_id) if enrollment.cohort_id else None,
            "enrolled_at": enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
            "progress": enrollment.progress,
        },
    }


def _enforce_cohort_gates(db: Session, course_id: str, cohort_id: str, now: datetime) -> None:
    """Validate that the student can enroll into the requested cohort.

    Returns nothing on success; raises the appropriate HTTPException on
    any gate failure (cohort doesn't include this course, inactive
    status, window not open, window closed, or capacity reached).

    Cohort-course membership is checked through the ``cohort_courses``
    junction (ADR-010): a cohort is valid for this course iff there's
    a junction row tying the two.
    """
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).with_for_update().first()
    if not cohort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found",
        )
    junction = (
        db.query(CohortCourse).filter(CohortCourse.cohort_id == cohort.id, CohortCourse.course_id == course_id).first()
    )
    if junction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort does not include this course",
        )
    if cohort.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cohort is not active")
    if cohort.enrollment_start and now < cohort.enrollment_start:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cohort enrollment has not started yet",
        )
    if cohort.enrollment_end and now > cohort.enrollment_end:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cohort enrollment period has ended",
        )
    if cohort.max_students:
        current_count = (
            db.query(sa_func.count(sa_func.distinct(Enrollment.user_id)))
            .filter(Enrollment.cohort_id == cohort.id)
            .scalar()
            or 0
        )
        if current_count >= cohort.max_students:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cohort has reached maximum capacity",
            )


@router.post("/{course_id}/enroll", response_model=EnrollmentResponse)
def enroll_course(
    course_id: str,
    request: Request,
    body: EnrollRequest = EnrollRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Enrollment:
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course '{course_id}' not found",
        )
    if course.status != "published":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot enroll in an unpublished course",
        )
    now = datetime.now(UTC)

    cohort_id: str | None = None
    if body.cohort_id:
        # Cohort-route self-enrollment works for either access mode —
        # joining the cohort is the director's intent regardless of
        # whether the course is institute or public.
        _enforce_cohort_gates(db, course_id, body.cohort_id, now)
        cohort_id = body.cohort_id
    else:
        # Solo (no-cohort) enrollment. Institute courses block this path
        # entirely (ADR-010): admin must add the student directly via
        # the cohort endpoints or the admin-direct enrollment endpoint.
        if course.access_mode == "institute":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This course is available only by invitation from the institute",
            )
        # Public courses are gated by the course-level enrollment window.
        if course.enrollment_start and now < course.enrollment_start:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Enrollment has not started yet",
            )
        if course.enrollment_end and now > course.enrollment_end:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Enrollment period has ended",
            )

    enrollment = enroll_user_in_course(db, current_user.id, course_id, cohort_id=cohort_id)
    log_action(
        db,
        current_user.id,
        "enroll",
        "enrollment",
        str(enrollment.id),
        details={"course_id": course_id},
        request=request,
    )
    return enrollment
