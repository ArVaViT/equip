"""Enrollment create/read + progress synchronization."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.constants import GRADABLE_CHAPTER_TYPES
from app.core.metrics import increment
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


def enroll_user_in_course(
    db: Session,
    user_id: str | UUID,
    course_id: str,
    cohort_id: str | None = None,
) -> Enrollment:
    # Existence is scoped to (user, course, cohort) — matching the DB unique
    # index `(user_id, course_id, COALESCE(cohort_id, sentinel))`. A student
    # who took the course solo (or in cohort A) may re-enrol via cohort B and
    # get a NEW row, which is the intended multi-cohort-retake behaviour. A
    # plain (user, course) check would wrongly return the old row and silently
    # block the retake the index was designed to permit.
    cohort_match = Enrollment.cohort_id.is_(None) if cohort_id is None else Enrollment.cohort_id == cohort_id
    existing = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user_id, Enrollment.course_id == course_id, cohort_match)
        .first()
    )
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
        # A concurrent POST for the same (user, course, cohort) just committed.
        # Return the winner row instead of propagating the 500.
        db.rollback()
        existing = (
            db.query(Enrollment)
            .filter(Enrollment.user_id == user_id, Enrollment.course_id == course_id, cohort_match)
            .first()
        )
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
    # Dashboard list view: load the enrollment + its course SCALARS only — no
    # module/chapter tree. ``/users/me/courses`` is the highest-traffic screen
    # and serialises ``EnrollmentSummaryResponse`` whose embedded
    # ``CourseDashboardSummary`` carries only id/title/progress-relevant scalar
    # fields (no ``modules``). The old loader eager-loaded the full
    # ``_COURSE_TREE`` (240+ chapters on a fat course) only for Pydantic to
    # discard them; a modules-only loader would instead lazy-load chapters
    # per module during serialisation (N+1). Dropping the tree entirely means
    # the slim schema never touches the relationship, so neither happens.
    query = (
        db.query(Enrollment)
        .join(Course, Course.id == Enrollment.course_id)
        .options(joinedload(Enrollment.course))
        .filter(Enrollment.user_id == user_id, Course.deleted_at.is_(None))
        .order_by(Enrollment.enrolled_at.desc())
    )
    if skip:
        query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def resync_course_progress(db: Session, course_id: str | UUID) -> int:
    """Recompute ``enrollment.progress`` for everybody on this course.

    ``sync_enrollment_progress`` runs when one student's pass-state flips.
    Nothing ran when the *course* changed shape — and the percentage is a
    fraction of the course's gradable chapters, so deleting a quiz, adding
    one, or changing a chapter's type moves the denominator for every
    student at once.

    The visible consequence, on production 2026-08-31: four enrolments
    stored 100% while the same screen counted "0/5 chapters" beside them.
    Those students had passed a quiz that was later deleted; the stored
    percentage was never touched again, so the teacher's board showed two
    numbers that contradicted each other and no way to tell which was true.

    One UPDATE for the whole course rather than a loop: this runs inside
    chapter and module deletes, where a course with hundreds of enrolments
    would otherwise mean hundreds of round trips.

    Returns the number of rows updated, for the caller's audit line.
    """
    gradable = (
        select(Chapter.id)
        .join(Module, Chapter.module_id == Module.id)
        .where(
            Module.course_id == course_id,
            Chapter.chapter_type.in_(GRADABLE_CHAPTER_TYPES),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    total = (
        select(func.count())
        .select_from(Chapter)
        .join(Module, Chapter.module_id == Module.id)
        .where(
            Module.course_id == course_id,
            Chapter.chapter_type.in_(GRADABLE_CHAPTER_TYPES),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    completed = (
        select(func.count())
        .select_from(ChapterProgress)
        .where(
            ChapterProgress.user_id == Enrollment.user_id,
            ChapterProgress.chapter_id.in_(gradable),
            ChapterProgress.completed.is_(True),
        )
        .scalar_subquery()
    )
    # A course with nothing gradable is 0%, not a division by zero — the same
    # answer ``sync_enrollment_progress`` gives.
    fresh = case(
        (total == 0, 0),
        else_=func.round(completed * 100.0 / func.nullif(total, 0)),
    )

    # Counted first, then written. Doing both in one statement means relying
    # on the UPDATE's row count, which is "rows I looked at" — every enrolment
    # on the course — and that reads as "rows that were wrong" to whoever
    # pressed the button. Two statements, one honest number.
    # The stale rows are selected, not counted in SQL. Wrapping the predicate
    # in ``count()`` — directly or through a subquery — drops the correlation
    # to ``Enrollment`` that ``completed`` depends on, and the answer comes
    # back 0: the resync then reports "nothing to fix" on a course that is
    # entirely wrong. A course's enrolment list is small enough to hold.
    stale_ids = [
        row[0]
        for row in db.query(Enrollment.id).filter(
            Enrollment.course_id == course_id,
            Enrollment.progress.is_distinct_from(fresh),
        )
    ]
    changed = len(stale_ids)
    if stale_ids:
        db.query(Enrollment).filter(Enrollment.id.in_(stale_ids)).update(
            {Enrollment.progress: fresh}, synchronize_session=False
        )
    db.commit()
    return int(changed)


def reading_progress_by_course(
    db: Session,
    user_id: str | UUID,
    course_ids: list[str],
) -> dict[str, tuple[int, int]]:
    """``{course_id: (chapters_read, chapters_to_read)}`` for one student.

    Reading is counted separately from `enrollment.progress` on purpose.
    That percentage is deliberately assessment-only — see the note in
    ``frontend/src/pages/Course/moduleProgress.ts``: a lesson you have read
    is not an assessment you have passed, and one number for both would
    blur the distinction the percentage rests on.

    But the dashboard showed *only* that percentage, and the live courses
    are 11-16 reading chapters against 4-6 gradable ones. So somebody could
    read every lesson in a course and be told 0%. Two people did exactly
    that in August 2026 — one on the 24th, one on the 30th — and both rows
    still read `progress = 0`. This is the second number, so the dashboard
    can say what actually happened without lying about assessment.

    One grouped query for the whole dashboard: the callers hand in every
    course on the page at once, so this cannot become an N+1.
    """
    if not course_ids:
        return {}

    rows = (
        db.query(
            Module.course_id.label("course_id"),
            func.count(Chapter.id).label("to_read"),
            func.count(ChapterProgress.id).filter(ChapterProgress.completed.is_(True)).label("read"),
        )
        .select_from(Chapter)
        .join(Module, Chapter.module_id == Module.id)
        .outerjoin(
            ChapterProgress,
            (ChapterProgress.chapter_id == Chapter.id) & (ChapterProgress.user_id == user_id),
        )
        .filter(
            Module.course_id.in_(course_ids),
            # Everything that is not assessed. Written as the complement of
            # GRADABLE_CHAPTER_TYPES rather than `== "reading"` so a chapter
            # type added later (a video lesson, say) counts as something to
            # work through instead of silently vanishing from both numbers.
            Chapter.chapter_type.notin_(GRADABLE_CHAPTER_TYPES),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .group_by(Module.course_id)
        .all()
    )
    return {str(row.course_id): (int(row.read or 0), int(row.to_read or 0)) for row in rows}


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
