from uuid import UUID

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.constants import GRADABLE_CHAPTER_TYPES
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAttempt
from app.models.student_grade import StudentGrade
from app.models.user import User
from app.schemas.grade import GradeBreakdown

LETTER_GRADES = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]


def score_to_letter(score: float) -> str:
    for threshold, letter in LETTER_GRADES:
        if score >= threshold:
            return letter
    return "F"


def _get_course_chapter_ids(db: Session, course_id: str) -> list[str]:
    """Get chapter IDs for gradable chapters (quiz/exam/assignment) in a course, excluding soft-deleted."""
    rows = (
        db.query(Chapter.id)
        .join(Module, Module.id == Chapter.module_id)
        .filter(
            Module.course_id == course_id,
            Chapter.chapter_type.in_(GRADABLE_CHAPTER_TYPES),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .all()
    )
    return [r[0] for r in rows]


def _get_quiz_ids_for_chapters(db: Session, chapter_ids: list[str]) -> list[UUID]:
    if not chapter_ids:
        return []
    rows = db.query(Quiz.id).filter(Quiz.chapter_id.in_(chapter_ids)).all()
    return [r[0] for r in rows]


def _get_assignment_ids_for_chapters(db: Session, chapter_ids: list[str]) -> list[UUID]:
    if not chapter_ids:
        return []
    rows = db.query(Assignment.id).filter(Assignment.chapter_id.in_(chapter_ids)).all()
    return [r[0] for r in rows]


def _build_breakdown(
    course: Course,
    quiz_avg: float,
    assignment_avg: float,
    participation_pct: float,
) -> GradeBreakdown:
    quiz_weighted = quiz_avg * course.quiz_weight / 100.0
    assignment_weighted = assignment_avg * course.assignment_weight / 100.0
    participation_weighted = participation_pct * course.participation_weight / 100.0
    final_score = round(quiz_weighted + assignment_weighted + participation_weighted, 2)
    return GradeBreakdown(
        quiz_avg=round(quiz_avg, 2),
        quiz_weighted=round(quiz_weighted, 2),
        assignment_avg=round(assignment_avg, 2),
        assignment_weighted=round(assignment_weighted, 2),
        participation_pct=round(participation_pct, 2),
        participation_weighted=round(participation_weighted, 2),
        final_score=final_score,
        letter_grade=score_to_letter(final_score),
    )


def calculate_student_grade_for_course(
    db: Session,
    course: Course,
    student_id: UUID,
) -> GradeBreakdown:
    """Calculate a single student's weighted grade breakdown.

    Thin convenience wrapper that resolves the course's gradable chapter /
    quiz / assignment ids once and delegates to :func:`calculate_student_grade`.
    """
    chapter_ids = _get_course_chapter_ids(db, course.id)
    quiz_ids = _get_quiz_ids_for_chapters(db, chapter_ids)
    assignment_ids = _get_assignment_ids_for_chapters(db, chapter_ids)
    return calculate_student_grade(db, course, student_id, chapter_ids, quiz_ids, assignment_ids)


def calculate_student_grade(
    db: Session,
    course: Course,
    student_id: UUID,
    chapter_ids: list[str],
    quiz_ids: list[UUID],
    assignment_ids: list[UUID],
) -> GradeBreakdown:
    """Calculate a single student's weighted grade breakdown.

    Lower-level entry point when chapter / quiz / assignment ids are already
    in hand (e.g. inside :func:`calculate_all_student_grades`). Callers that
    only have a course should use :func:`calculate_student_grade_for_course`.
    """
    quiz_avg = 0.0
    if quiz_ids:
        rows = (
            db.query(
                QuizAttempt.quiz_id,
                sqlfunc.max(QuizAttempt.score * 100.0 / sqlfunc.nullif(QuizAttempt.max_score, 0)).label("best"),
            )
            .filter(
                QuizAttempt.quiz_id.in_(quiz_ids),
                QuizAttempt.user_id == student_id,
                QuizAttempt.completed_at.isnot(None),
            )
            .group_by(QuizAttempt.quiz_id)
            .all()
        )
        best_scores = [float(r.best) for r in rows if r.best is not None]
        total_quizzes = len(quiz_ids)
        quiz_avg = sum(best_scores) / total_quizzes if total_quizzes > 0 else 0.0

    assignment_avg = 0.0
    if assignment_ids:
        best_per_assignment = (
            db.query(
                AssignmentSubmission.assignment_id,
                sqlfunc.max(AssignmentSubmission.grade).label("best_grade"),
                Assignment.max_score,
            )
            .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
            .filter(
                AssignmentSubmission.assignment_id.in_(assignment_ids),
                AssignmentSubmission.student_id == student_id,
                AssignmentSubmission.grade.isnot(None),
            )
            .group_by(AssignmentSubmission.assignment_id, Assignment.max_score)
            .all()
        )
        total_assignments = len(assignment_ids)
        if total_assignments > 0:
            # Clamp at 100% defensively — assignment_submissions.grade
            # is capped at ``assignment.max_score`` going forward (per the
            # grade-submission route), but any pre-cap historical row
            # with ``grade > max_score`` would inflate the average above
            # 100% and distort the final course grade. ``min(100.0, ...)``
            # is the cheap fix; the underlying CHECK constraint would be
            # the durable one (separate PR).
            graded_pcts = [
                min(100.0, row.best_grade / row.max_score * 100.0) if row.max_score else 0.0
                for row in best_per_assignment
            ]
            assignment_avg = sum(graded_pcts) / total_assignments

    total_chapters = len(chapter_ids)
    participation_pct = 0.0
    if total_chapters > 0:
        completed_count = (
            db.query(sqlfunc.count(ChapterProgress.id))
            .filter(
                ChapterProgress.user_id == student_id,
                ChapterProgress.chapter_id.in_(chapter_ids),
                ChapterProgress.completed.is_(True),
            )
            .scalar()
        ) or 0
        participation_pct = (completed_count / total_chapters) * 100.0

    return _build_breakdown(course, quiz_avg, assignment_avg, participation_pct)


def calculate_all_student_grades(db: Session, course: Course):
    """
    Calculate grades for all enrolled students using batch queries.
    Uses 6 queries total regardless of student count.
    """
    chapter_ids = _get_course_chapter_ids(db, course.id)
    quiz_ids = _get_quiz_ids_for_chapters(db, chapter_ids)
    assignment_ids = _get_assignment_ids_for_chapters(db, chapter_ids)

    enrollments = (
        db.query(Enrollment.user_id, User.full_name, User.email)
        .join(User, User.id == Enrollment.user_id)
        .filter(Enrollment.course_id == course.id)
        .all()
    )
    if not enrollments:
        return []

    student_ids = [e.user_id for e in enrollments]

    # Batch: best quiz scores per student per quiz
    quiz_scores: dict[str, list[float]] = {str(sid): [] for sid in student_ids}
    if quiz_ids:
        quiz_rows = (
            db.query(
                QuizAttempt.user_id,
                QuizAttempt.quiz_id,
                sqlfunc.max(QuizAttempt.score * 100.0 / sqlfunc.nullif(QuizAttempt.max_score, 0)).label("best"),
            )
            .filter(
                QuizAttempt.quiz_id.in_(quiz_ids),
                QuizAttempt.user_id.in_(student_ids),
                QuizAttempt.completed_at.isnot(None),
            )
            .group_by(QuizAttempt.user_id, QuizAttempt.quiz_id)
            .all()
        )
        for qr in quiz_rows:
            if qr.best is not None:
                quiz_scores.setdefault(str(qr.user_id), []).append(float(qr.best))

    # Batch: best assignment grade per student per assignment
    asgn_scores: dict[str, list[float]] = {str(sid): [] for sid in student_ids}
    if assignment_ids:
        asgn_rows = (
            db.query(
                AssignmentSubmission.student_id,
                AssignmentSubmission.assignment_id,
                sqlfunc.max(AssignmentSubmission.grade).label("best_grade"),
                Assignment.max_score,
            )
            .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
            .filter(
                AssignmentSubmission.assignment_id.in_(assignment_ids),
                AssignmentSubmission.student_id.in_(student_ids),
                AssignmentSubmission.grade.isnot(None),
            )
            .group_by(
                AssignmentSubmission.student_id,
                AssignmentSubmission.assignment_id,
                Assignment.max_score,
            )
            .all()
        )
        for ar in asgn_rows:
            # See same-named single-student site above — clamp at 100%
            # so a historical over-cap grade doesn't distort the batch.
            pct = min(100.0, float(ar.best_grade) / ar.max_score * 100.0) if ar.max_score else 0.0
            asgn_scores.setdefault(str(ar.student_id), []).append(pct)

    # Batch: chapter completion counts per student
    completion_counts: dict[str, int] = {}
    if chapter_ids:
        comp_rows = (
            db.query(ChapterProgress.user_id, sqlfunc.count(ChapterProgress.id))
            .filter(
                ChapterProgress.user_id.in_(student_ids),
                ChapterProgress.chapter_id.in_(chapter_ids),
                ChapterProgress.completed.is_(True),
            )
            .group_by(ChapterProgress.user_id)
            .all()
        )
        for uid, cnt in comp_rows:
            completion_counts[str(uid)] = cnt

    # Manual grades
    manual_grades_map: dict[str, str | None] = {}
    manual_rows = (
        db.query(StudentGrade.student_id, StudentGrade.grade).filter(StudentGrade.course_id == course.id).all()
    )
    for row in manual_rows:
        manual_grades_map[str(row.student_id)] = row.grade

    total_chapters = len(chapter_ids)
    total_quizzes = len(quiz_ids)
    total_assignments = len(assignment_ids)
    results = []
    for user_id, full_name, email in enrollments:
        sid = str(user_id)
        qs = quiz_scores.get(sid, [])
        quiz_avg = sum(qs) / total_quizzes if total_quizzes > 0 else 0.0
        asgs = asgn_scores.get(sid, [])
        assignment_avg = sum(asgs) / total_assignments if total_assignments > 0 else 0.0
        comp = completion_counts.get(sid, 0)
        participation_pct = (comp / total_chapters * 100.0) if total_chapters else 0.0

        breakdown = _build_breakdown(course, quiz_avg, assignment_avg, participation_pct)
        results.append(
            {
                "student_id": sid,
                "student_name": full_name,
                "student_email": email,
                "breakdown": breakdown,
                "manual_grade": manual_grades_map.get(sid),
            }
        )

    return results
