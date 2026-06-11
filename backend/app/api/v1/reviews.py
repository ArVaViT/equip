from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_live_course_or_404
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.metrics import gauge
from app.models.certificate import Certificate
from app.models.course import CourseStatus
from app.models.review import CourseReview
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewResponse

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/course/{course_id}", response_model=list[ReviewResponse])
def list_course_reviews(
    course_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    # ``get_live_course_or_404`` raises the canonical 404 for a missing /
    # soft-deleted course; an unpublished course is masked behind the same
    # 404 here so its existence does not leak to anonymous callers.
    course = get_live_course_or_404(db, course_id)
    if course.status != CourseStatus.PUBLISHED:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Course not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    return (
        db.query(CourseReview)
        .filter(CourseReview.course_id == course_id)
        .order_by(CourseReview.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("/course/{course_id}", response_model=ReviewResponse)
def create_or_update_review(
    course_id: str,
    data: ReviewCreate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cert = (
        db.query(Certificate)
        .filter(
            Certificate.user_id == current_user.id,
            Certificate.course_id == course_id,
            Certificate.status == "approved",
        )
        .first()
    )
    if not cert:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="You must complete the course and receive a certificate before reviewing",
            context={"resource_type": "review", "course_id": course_id},
        )

    existing = (
        db.query(CourseReview)
        .filter(CourseReview.user_id == current_user.id, CourseReview.course_id == course_id)
        .first()
    )

    if existing:
        existing.rating = data.rating
        existing.comment = data.comment
        db.commit()
        db.refresh(existing)
        # equip.reviews.rating_latest gauges the most recent rating
        # per (user, course). Datadog aggregates by ``avg`` per course
        # to drive the Course Engagement dashboard's rating tile.
        gauge(
            "equip.reviews.rating_latest",
            float(data.rating),
            course_id=str(course_id),
        )
        response.status_code = status.HTTP_200_OK
        return existing

    review = CourseReview(
        user_id=current_user.id,
        course_id=course_id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(CourseReview)
            .filter(CourseReview.user_id == current_user.id, CourseReview.course_id == course_id)
            .first()
        )
        if existing:
            existing.rating = data.rating
            existing.comment = data.comment
            db.commit()
            db.refresh(existing)
            gauge(
                "equip.reviews.rating_latest",
                float(data.rating),
                course_id=str(course_id),
            )
            response.status_code = status.HTTP_200_OK
            return existing
        # Concurrent delete between the duplicate insert and this read, or a
        # different constraint fired. Return a clean 409 instead of leaking the
        # raw IntegrityError to the generic DB handler (which would report 503).
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message="Review could not be saved due to a conflict; please retry.",
            context={"resource_type": "review", "course_id": course_id},
        ) from None
    db.refresh(review)
    gauge(
        "equip.reviews.rating_latest",
        float(data.rating),
        course_id=str(course_id),
    )
    response.status_code = status.HTTP_201_CREATED
    return review


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = db.query(CourseReview).filter(CourseReview.id == review_id).first()
    if not review:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Review not found",
            context={"resource_type": "review", "resource_id": str(review_id)},
        )
    if review.user_id != current_user.id:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="You can only delete your own reviews",
            context={"resource_type": "review", "resource_id": str(review_id)},
        )
    db.delete(review)
    db.commit()
