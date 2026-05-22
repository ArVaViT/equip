from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import require_teacher, verify_course_owner
from app.core.database import get_db
from app.models.enrollment import Enrollment
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/course/{course_id}",
    summary="Course-level analytics for the teacher dashboard",
    responses={
        200: {"description": "Course title + aggregate stats + paginated enrollment list"},
        403: {"description": "Caller is not the course owner (or admin)"},
        404: {"description": "Course not found"},
    },
)
def get_course_analytics(
    course_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
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

    # Aggregates in one round-trip instead of loading everything into Python.
    agg = (
        db.query(
            func.count(Enrollment.id).label("total"),
            func.coalesce(func.avg(Enrollment.progress), 0.0).label("avg_progress"),
            func.count(Enrollment.id).filter(Enrollment.progress >= 100).label("completed"),
        )
        .filter(Enrollment.course_id == course_id)
        .one()
    )

    enrollments = (
        db.query(Enrollment, User)
        .join(User, Enrollment.user_id == User.id)
        .filter(Enrollment.course_id == course_id)
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
