"""Enrollment endpoints: status probe + enroll."""

from datetime import UTC, datetime

from fastapi import Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.cohort import Cohort, CohortCourse
from app.models.course import Course, CourseAccessMode, CourseStatus
from app.models.enrollment import Enrollment
from app.models.user import User
from app.schemas.course import EnrollmentResponse
from app.services.audit_service import log_action
from app.services.cohort_capacity import assert_cohort_has_capacity
from app.services.course_service import enroll_user_in_course
from app.services.translation.resolve_for_display import populate_spine_texts

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


def _enforce_cohort_gates(db: Session, course_id: str, cohort_id: str, user_id: str, now: datetime) -> None:
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
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Cohort not found",
            context={"resource_type": "cohort", "resource_id": cohort_id},
        )
    junction = (
        db.query(CohortCourse).filter(CohortCourse.cohort_id == cohort.id, CohortCourse.course_id == course_id).first()
    )
    if junction is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Cohort does not include this course",
            context={"resource_type": "cohort_course", "cohort_id": cohort_id, "course_id": course_id},
        )
    if cohort.status != "active":
        raise equip_error(
            ErrorCode.COURSE_ENROLMENT_CLOSED,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Cohort is not active",
            context={"resource_type": "cohort", "cohort_id": cohort_id, "current_status": cohort.status},
        )
    if cohort.enrollment_start and now < cohort.enrollment_start:
        raise equip_error(
            ErrorCode.COURSE_ENROLMENT_CLOSED,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Cohort enrollment has not started yet",
            context={
                "resource_type": "cohort",
                "cohort_id": cohort_id,
                "enrollment_start": cohort.enrollment_start.isoformat(),
            },
        )
    if cohort.enrollment_end and now > cohort.enrollment_end:
        raise equip_error(
            ErrorCode.COURSE_ENROLMENT_CLOSED,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Cohort enrollment period has ended",
            context={
                "resource_type": "cohort",
                "cohort_id": cohort_id,
                "enrollment_end": cohort.enrollment_end.isoformat(),
            },
        )
    # Capacity gate — shared with the admin add-student path so the
    # already-seated exemption + error code stay identical. Runs under the
    # with_for_update() lock taken above.
    assert_cohort_has_capacity(db, cohort, user_id)


@router.post("/{course_id}/enroll", response_model=EnrollmentResponse)
def enroll_course(
    course_id: str,
    request: Request,
    body: EnrollRequest = EnrollRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Enrollment:
    # Narrow probe — enrollment policy only reads four columns, no need
    # to pull the full module + chapter tree for a yes/no check.
    course_row = (
        db.query(
            Course.status,
            Course.access_mode,
            Course.enrollment_start,
            Course.enrollment_end,
        )
        .filter(Course.id == course_id, Course.deleted_at.is_(None))
        .first()
    )
    if course_row is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    course_status, access_mode, enrollment_start, enrollment_end = course_row
    if course_status != CourseStatus.PUBLISHED:
        raise equip_error(
            ErrorCode.COURSE_NOT_PUBLISHED,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Cannot enroll in an unpublished course",
            context={"resource_type": "course", "course_id": course_id, "current_status": course_status},
        )
    now = datetime.now(UTC)

    cohort_id: str | None = None
    if body.cohort_id:
        # Cohort-route self-enrollment works for either access mode —
        # joining the cohort is the director's intent regardless of
        # whether the course is institute or public.
        _enforce_cohort_gates(db, course_id, body.cohort_id, str(current_user.id), now)
        cohort_id = body.cohort_id
    else:
        # Solo (no-cohort) enrollment. Institute courses block this path
        # entirely (ADR-010): admin must add the student directly via
        # the cohort endpoints or the admin-direct enrollment endpoint.
        if access_mode == CourseAccessMode.INSTITUTE:
            raise equip_error(
                ErrorCode.COURSE_ENROLMENT_CLOSED,
                status_code=status.HTTP_403_FORBIDDEN,
                message="This course is available only by invitation from the institute",
                context={"resource_type": "course", "course_id": course_id, "access_mode": "institute"},
            )
        # Public courses are gated by the course-level enrollment window.
        if enrollment_start and now < enrollment_start:
            raise equip_error(
                ErrorCode.COURSE_ENROLMENT_CLOSED,
                status_code=status.HTTP_403_FORBIDDEN,
                message="Enrollment has not started yet",
                context={
                    "resource_type": "course",
                    "course_id": course_id,
                    "enrollment_start": enrollment_start.isoformat(),
                },
            )
        if enrollment_end and now > enrollment_end:
            raise equip_error(
                ErrorCode.COURSE_ENROLMENT_CLOSED,
                status_code=status.HTTP_403_FORBIDDEN,
                message="Enrollment period has ended",
                context={
                    "resource_type": "course",
                    "course_id": course_id,
                    "enrollment_end": enrollment_end.isoformat(),
                },
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
    # Phase 5g: hydrate the lazy-loaded course relationship so the
    # response serializer sees title/description (no longer columns).
    if enrollment.course is not None:
        populate_spine_texts(db, [enrollment.course])
    return enrollment
