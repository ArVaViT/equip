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
from app.models.course import Chapter, Course
from app.models.enrollment import Enrollment

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any
    from uuid import UUID

    from sqlalchemy.orm import Session


def enroll_user_in_course(
    db: Session,
    user_id: str | UUID,
    course_id: str,
    cohort_id: str | None = None,
    *,
    commit: bool = True,
) -> Enrollment:
    """Put a person on a course, idempotently.

    ``commit=False`` keeps the row inside the caller's transaction. It
    exists for accepting an invitation, where the enrolment is one of
    four writes that have to land together or not at all — committing
    here would leave a half-accepted invitation reachable if a later
    statement failed. The uniqueness race is then caught on a SAVEPOINT
    instead of a rollback, because rolling the whole transaction back
    would discard the caller's work along with ours.
    """
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
        if commit:
            db.commit()
        else:
            # SAVEPOINT: a collision here must not take the caller's
            # other writes with it.
            with db.begin_nested():
                db.flush()
    except IntegrityError:
        # A concurrent write for the same (user, course, cohort) just
        # landed. Return the winner row instead of propagating the 500.
        if commit:
            db.rollback()
        existing = (
            db.query(Enrollment)
            .filter(Enrollment.user_id == user_id, Enrollment.course_id == course_id, cohort_match)
            .first()
        )
        if existing:
            return existing
        raise
    if commit:
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
    # One rule for one student and for a whole course: ``fresh_progress``.
    # The SQL-only version of this counted gradable chapters alone and gave
    # a course with none 0% — so deleting a course's only quiz stranded
    # everybody who had read it all at 0, with no action left that would move
    # them (2026-10-03). Computed set-based here — two totals and two grouped
    # counts, whatever the enrolment — because this runs on every lesson
    # added, removed or retyped.
    fresh_for = _course_progress_rule(db, course_id)
    rows = db.query(Enrollment.id, Enrollment.user_id, Enrollment.progress).filter(Enrollment.course_id == course_id)
    stale: dict[int, list] = {}
    for enrollment_id, user_id, progress in rows:
        value = fresh_for(str(user_id))
        if progress != value:
            stale.setdefault(value, []).append(enrollment_id)
    # Counted first, then written: the number returned is rows that were
    # wrong, not rows looked at.
    changed = sum(len(ids) for ids in stale.values())
    for value, ids in stale.items():
        db.query(Enrollment).filter(Enrollment.id.in_(ids)).update(
            {Enrollment.progress: value}, synchronize_session=False
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
            Chapter.course_id.label("course_id"),
            func.count(Chapter.id).label("to_read"),
            func.count(ChapterProgress.id).filter(ChapterProgress.completed.is_(True)).label("read"),
        )
        .select_from(Chapter)
        .outerjoin(
            ChapterProgress,
            (ChapterProgress.chapter_id == Chapter.id) & (ChapterProgress.user_id == user_id),
        )
        .filter(
            Chapter.course_id.in_(course_ids),
            # Everything that is not assessed. Written as the complement of
            # GRADABLE_CHAPTER_TYPES rather than `== "reading"` so a chapter
            # type added later (a video lesson, say) counts as something to
            # work through instead of silently vanishing from both numbers.
            Chapter.chapter_type.notin_(GRADABLE_CHAPTER_TYPES),
            Chapter.deleted_at.is_(None),
        )
        .group_by(Chapter.course_id)
        .all()
    )
    return {str(row.course_id): (int(row.read or 0), int(row.to_read or 0)) for row in rows}


def fresh_progress(db: Session, user_id: str | UUID, course_id: str | UUID) -> int:
    """What this student's ``enrollment.progress`` should read now.

    The share of the course's live gradable chapters they have completed —
    assessment, by design. On a course with nothing to assess, reading is the
    work: the share of its live chapters they have read. The certificate gate
    for such a course is «progress == 100» (``completion_pass`` in
    grade_calculator); counting assessed chapters alone gave it 0% however
    much was read, so a reading-only course could never be finished.
    """
    gradable = (
        db.query(
            func.count(Chapter.id),
            func.count(ChapterProgress.id).filter(ChapterProgress.completed.is_(True)),
        )
        .select_from(Chapter)
        .outerjoin(
            ChapterProgress,
            (ChapterProgress.chapter_id == Chapter.id) & (ChapterProgress.user_id == user_id),
        )
        .filter(
            Chapter.course_id == course_id,
            Chapter.chapter_type.in_(GRADABLE_CHAPTER_TYPES),
            Chapter.deleted_at.is_(None),
        )
        .one()
    )
    total, done = int(gradable[0] or 0), int(gradable[1] or 0)
    if total:
        return round(done / total * 100)
    reading = (
        db.query(
            func.count(Chapter.id),
            func.count(ChapterProgress.id).filter(ChapterProgress.completed.is_(True)),
        )
        .select_from(Chapter)
        .outerjoin(
            ChapterProgress,
            (ChapterProgress.chapter_id == Chapter.id) & (ChapterProgress.user_id == user_id),
        )
        .filter(Chapter.course_id == course_id, Chapter.deleted_at.is_(None))
        .one()
    )
    to_read, read = int(reading[0] or 0), int(reading[1] or 0)
    return round(read / to_read * 100) if to_read else 0


def _course_progress_rule(db: Session, course_id: str | UUID) -> Callable[[str], int]:
    """``fresh_progress`` for every student of one course, in four queries.

    The same rule — share of live gradable chapters completed, or on a course
    with none, share of live chapters read — with the per-student counts
    grouped by user instead of asked once per student.
    """

    def _done_by_user(*conditions: Any) -> dict[str, int]:
        rows = (
            db.query(ChapterProgress.user_id, func.count(ChapterProgress.id))
            .join(Chapter, Chapter.id == ChapterProgress.chapter_id)
            .filter(
                Chapter.course_id == course_id,
                Chapter.deleted_at.is_(None),
                ChapterProgress.completed.is_(True),
                *conditions,
            )
            .group_by(ChapterProgress.user_id)
            .all()
        )
        return {str(user_id): int(count) for user_id, count in rows}

    def _total(*conditions: Any) -> int:
        return int(
            db.query(func.count(Chapter.id))
            .filter(Chapter.course_id == course_id, Chapter.deleted_at.is_(None), *conditions)
            .scalar()
            or 0
        )

    gradable = Chapter.chapter_type.in_(GRADABLE_CHAPTER_TYPES)
    total = _total(gradable)
    if total:
        done = _done_by_user(gradable)
        return lambda user_id: round(done.get(user_id, 0) / total * 100)
    to_read = _total()
    if not to_read:
        return lambda _user_id: 0
    read = _done_by_user()
    return lambda user_id: round(read.get(user_id, 0) / to_read * 100)


def sync_enrollment_progress(db: Session, user_id: str | UUID, course_id: str | UUID) -> Enrollment | None:
    """Recompute ``enrollment.progress`` from completed gradable chapters —
    or, on a course with none, from the chapters read.

    Called from submission/quiz-grading flows after a pass-state flip.
    Uses a single aggregated query so this stays cheap even on courses
    with hundreds of chapters.
    """
    db.flush()
    # Every enrolment this student holds on the course: a retake or a second
    # cohort is a second row, and ``.first()`` with no order updated one of
    # them at random while the grade view and the certificate gate read the
    # latest (2026-10-03). The fraction is the student's, so all rows agree.
    enrollments = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user_id, Enrollment.course_id == course_id)
        .order_by(Enrollment.enrolled_at.desc().nullslast(), Enrollment.id.desc())
        .all()
    )
    if not enrollments:
        return None
    value = fresh_progress(db, user_id, course_id)
    for enrollment in enrollments:
        enrollment.progress = value
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
            float(value),
            course_id=str(course_id),
        )
    except Exception:
        pass

    return enrollments[0]
