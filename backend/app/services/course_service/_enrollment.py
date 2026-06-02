"""Enrollment create/read + progress synchronization."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.constants import GRADABLE_CHAPTER_TYPES
from app.core.metrics import increment
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment

from ._queries import _COURSE_TREE

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


def enroll_user_in_course(
    db: Session,
    user_id: str | UUID,
    course_id: str,
    cohort_id: str | None = None,
) -> Enrollment:
    existing = db.query(Enrollment).filter(Enrollment.user_id == user_id, Enrollment.course_id == course_id).first()
    if existing:
        return existing

    enrollment = Enrollment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        course_id=course_id,
        cohort_id=cohort_id,
        progress=0,
    )
    db.add(enrollment)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent POST for the same (user, course) just committed.
        # Return the winner row instead of propagating the 500.
        db.rollback()
        existing = db.query(Enrollment).filter(Enrollment.user_id == user_id, Enrollment.course_id == course_id).first()
        if existing:
            return existing
        raise
    db.refresh(enrollment)
    # equip.enrollments.created_total feeds the Course Engagement
    # dashboard's enrollment-rate tile + the dropoff_count derived
    # metric (denominator = sum(enrollments.created_total) - sum(
    # chapter_completed_total{first_chapter}) over the same window).
    # Counter fires once per *new* enrollment — the existing-row early
    # return above guarantees idempotency for re-enroll attempts.
    increment(
        "equip.enrollments.created_total",
        course_id=str(course_id),
        cohort_id=str(cohort_id) if cohort_id else "",
    )
    return enrollment


def get_user_courses(
    db: Session,
    user_id: str | UUID,
    *,
    skip: int = 0,
    limit: int | None = None,
) -> list[Enrollment]:
    query = (
        db.query(Enrollment)
        .join(Course, Course.id == Enrollment.course_id)
        .options(joinedload(Enrollment.course).options(*_COURSE_TREE))
        .filter(Enrollment.user_id == user_id, Course.deleted_at.is_(None))
        .order_by(Enrollment.enrolled_at.desc())
    )
    if skip:
        query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def sync_enrollment_progress(db: Session, user_id: str | UUID, course_id: str | UUID) -> Enrollment | None:
    """Recompute ``enrollment.progress`` from completed gradable chapters.

    Called from submission/quiz-grading flows after a pass-state flip.
    Uses a single aggregated query so this stays cheap even on courses
    with hundreds of chapters.
    """
    db.flush()
    enrollment = db.query(Enrollment).filter(Enrollment.user_id == user_id, Enrollment.course_id == course_id).first()
    if not enrollment:
        return None

    # Single round-trip: count gradable chapters and the subset that this user
    # has completed via a LEFT JOIN + COUNT FILTER.
    row = (
        db.query(
            func.count(Chapter.id).label("total_gradable"),
            func.count(ChapterProgress.id).filter(ChapterProgress.completed.is_(True)).label("completed_gradable"),
        )
        .select_from(Chapter)
        .join(Module, Chapter.module_id == Module.id)
        .outerjoin(
            ChapterProgress,
            (ChapterProgress.chapter_id == Chapter.id) & (ChapterProgress.user_id == user_id),
        )
        .filter(
            Module.course_id == course_id,
            Chapter.chapter_type.in_(GRADABLE_CHAPTER_TYPES),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .one()
    )
    total_gradable = row.total_gradable or 0
    completed_gradable = row.completed_gradable or 0

    if total_gradable == 0:
        enrollment.progress = 0
    else:
        enrollment.progress = round((completed_gradable / total_gradable) * 100)
    db.flush()

    # ``equip.completion.course_avg_pct`` is read by the Course
    # Engagement dashboard. We emit one event per progress recompute;
    # Datadog rolls them up to course-wide averages on the chart side.
    # Wrapped in try/except so a metric failure cannot break the
    # progress recompute itself.
    try:
        from app.core.metrics import gauge

        gauge(
            "equip.completion.course_avg_pct",
            float(enrollment.progress),
            course_id=str(course_id),
        )
    except Exception:
        pass

    return enrollment
