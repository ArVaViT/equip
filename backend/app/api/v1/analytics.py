from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import require_teacher, verify_course_owner
from app.core.database import get_db
from app.models.enrollment import Enrollment
from app.models.user import User
from app.schemas.locale import normalize_locale
from app.services.translation.resolve_for_display import populate_spine_texts

router = APIRouter(prefix="/analytics", tags=["analytics"])


class CourseAnalyticsStudentRow(BaseModel):
    """One enrollment row in the analytics student list. Typed so the
    response is validated on the way out — this payload carries PII
    (email + name), so a silent shape drift shouldn't ship unnoticed."""

    enrollment_id: str
    user_id: str
    full_name: str
    email: str
    progress: int
    enrolled_at: str | None = None


class CourseAnalyticsResponse(BaseModel):
    course_id: str
    course_title: str
    total_students: int
    avg_progress: float
    completion_count: int
    enrollments: list[CourseAnalyticsStudentRow]


@router.get(
    "/course/{course_id}",
    response_model=CourseAnalyticsResponse,
    summary="Course-level analytics for the teacher dashboard",
    responses={
        200: {"description": "Course title + aggregate stats + paginated enrollment list"},
        403: {"description": "Caller is not the course owner (or admin)"},
        404: {"description": "Course not found"},
    },
)
def get_course_analytics(
    course_id: str,
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Return aggregates + a paginated student list for one course.

    Used by the Teacher Analytics page. The aggregate (``total_students``,
    ``avg_progress``, ``completion_count``) is one SQL ``count``/``avg``
    round-trip so a course with thousands of students still loads in
    milliseconds; only the paginated ``enrollments`` slice fans out into
    rows. ``skip`` / ``limit`` follow the same convention as the rest of
    the API.
    """
    course = verify_course_owner(db, course_id, teacher)
    # courses.title moved to cv — hydrate before serialising.
    # Respect Accept-Language so a Russian teacher viewing an
    # EN-source course sees the localized title (matching the editor
    # overlay) instead of always the source. Tier order:
    # display_locale → source_locale → any-locale.
    populate_spine_texts(db, [course], display_locale=normalize_locale(accept_language))
    # Course title is locale-resolved via populate_spine_texts; downstream
    # caches must not conflate the EN and RU variants of the same payload.
    response.headers["Vary"] = "Accept-Language"

    # Aggregates in one round-trip instead of loading everything into Python.
    # Deactivated (soft-deleted) accounts are excluded so the teacher sees the
    # live class, not historical ghosts — mirrors the cohort-capacity count.
    agg = (
        db.query(
            func.count(Enrollment.id).label("total"),
            func.coalesce(func.avg(Enrollment.progress), 0.0).label("avg_progress"),
            func.count(Enrollment.id).filter(Enrollment.progress >= 100).label("completed"),
        )
        .join(User, Enrollment.user_id == User.id)
        .filter(Enrollment.course_id == course_id, User.deactivated_at.is_(None))
        .one()
    )

    enrollments = (
        db.query(Enrollment, User)
        .join(User, Enrollment.user_id == User.id)
        .filter(Enrollment.course_id == course_id, User.deactivated_at.is_(None))
        .order_by(Enrollment.enrolled_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    student_list = [
        {
            "enrollment_id": enrollment.id,
            "user_id": str(enrollment.user_id),
            "full_name": user.full_name or user.email,
            "email": user.email,
            "progress": enrollment.progress,
            "enrolled_at": enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
        }
        for enrollment, user in enrollments
    ]

    return {
        "course_id": course_id,
        "course_title": course.title,
        "total_students": int(agg.total or 0),
        "avg_progress": round(float(agg.avg_progress or 0.0), 1),
        "completion_count": int(agg.completed or 0),
        "enrollments": student_list,
    }
