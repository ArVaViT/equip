from uuid import UUID

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.constants import GRADABLE_CHAPTER_TYPES
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.org_settings import OrgSettings
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt
from app.models.student_grade import StudentGrade
from app.models.user import User
from app.schemas.grade import GradeBreakdown
from app.services.grading_scheme import effective_bands, get_org_settings, score_to_symbol

#: Fallback letter scale, used only when no database session is at hand.
#: The live bands come from ``org_settings`` via :mod:`app.services.grading_scheme`
#: — a school can move them, and these constants must never overrule that.
LETTER_GRADES = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]


def score_to_letter(score: float) -> str:
    """Legacy helper: the shipped letter scale, ignoring institutional bands.

    Kept for callers that have no session. Anything computing a grade a
    student will see must go through :func:`resolve_symbol` instead, or a
    school that edits its bands will find the change has no effect.
    """
    for threshold, letter in LETTER_GRADES:
        if score >= threshold:
            return letter
    return "F"


def resolve_symbol(score: float, course: Course, settings: OrgSettings) -> str:
    """The grade symbol for *score* under this course's scheme.

    This is what makes ``org_settings`` real rather than decorative. Until it
    was wired in, a school could edit its band boundaries and nothing moved:
    the calculator applied hardcoded 90/80/70/60 to every course on the
    platform regardless of the scheme the course claimed to use.

    * ``letter`` / ``five_point`` — the symbol whose band the score falls in,
      read from the institution's own table;
    * ``percent`` — no symbol; the number *is* the result;
    * ``pass_fail`` — no symbol here either. Its rule is completion-native
      (D2): «зачёт» means every chapter done and every assignment accepted, not
      a weighted average clearing a line. Deriving a pass from a percentage
      would be exactly the hidden-average behaviour the design removed, so this
      returns nothing until that rule lands. The scheme is not selectable in
      the UI yet, and every production course is ``letter``.
    """
    # A course with no scheme of its own falls back to the school default
    # rather than to no symbol at all: an unset column must never silently
    # strip a student's grade of its letter.
    scheme = course.grading_scheme or settings.default_grading_scheme
    bands = effective_bands(settings, scheme)
    if not bands:
        return ""
    return score_to_symbol(score, scheme, bands) or ""


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


def category_is_live(db: Session, *, quiz_ids: list[UUID], assignment_ids: list[UUID]) -> tuple[bool, bool]:
    """Whether each category actually carries graded work yet, course-wide.

    A category counts once **anyone in the course** has a graded piece of work
    in it — a completed quiz attempt, or a submission a teacher has marked. Not
    when the item merely exists.

    That distinction is the whole point, and getting it wrong is worse than the
    bug it replaces. Gating on existence means the moment a teacher creates the
    first assignment — due in two weeks, nobody has submitted anything — the
    assignment category snaps back to its configured weight while its average
    is still zero. On course 1f3c4803 that would drop all thirteen students
    from 100% to 40% in the same instant: A to F, no warning, no submission
    missed, purely because their teacher planned ahead. An empty category and a
    category nobody has been graded in yet are arithmetically identical, so
    they must behave identically.

    Course-wide rather than per-student on purpose: two students in one class
    must never have their grades computed from different weights. One number,
    one meaning, both roles (Принцип 3).

    The flip is still automatic — the first marked submission brings the
    teacher's configured split back — but it happens when there is something
    real to weigh.
    """
    has_quiz_work = False
    if quiz_ids:
        # A finished attempt is not necessarily a graded one. Open-ended
        # answers carry ``graded_at IS NULL`` until a teacher reviews them, so
        # an essay-style quiz can be submitted and sit unmarked for a week.
        # Counting it as live would put the course into `graded` with a 0%
        # average built from answers nobody has read — the same "graded 0"
        # this module exists to prevent, arriving through the quiz door.
        pending_answer = (
            db.query(QuizAnswer.id)
            .filter(QuizAnswer.attempt_id == QuizAttempt.id, QuizAnswer.graded_at.is_(None))
            .exists()
        )
        has_quiz_work = (
            db.query(QuizAttempt.id)
            .filter(
                QuizAttempt.quiz_id.in_(quiz_ids),
                QuizAttempt.completed_at.isnot(None),
                ~pending_answer,
            )
            .first()
            is not None
        )

    has_assignment_work = False
    if assignment_ids:
        has_assignment_work = (
            db.query(AssignmentSubmission.id)
            .filter(
                AssignmentSubmission.assignment_id.in_(assignment_ids),
                AssignmentSubmission.grade.isnot(None),
            )
            .first()
            is not None
        )

    return has_quiz_work, has_assignment_work


def effective_weights(course: Course, *, has_quizzes: bool, has_assignments: bool) -> tuple[int, int]:
    """Weights after inactive categories drop out (D4).

    A category with nothing graded in it contributes zero, so leaving it
    weighted silently caps the achievable score. The largest production course
    — 4 quizzes, 0 assignments, 13 students — was capped at the quiz weight
    alone: a student answering every question perfectly still landed on a
    failing letter, and no amount of work could move it.

    The flags come from :func:`category_is_live`, which asks whether the
    category carries graded work rather than whether items exist — see there
    for why the difference matters.

    Returns ``(0, 0)`` when neither category is live — the vacuous case, where
    there is nothing to redistribute *to*. See ``_build_breakdown``.
    """
    if has_quizzes and has_assignments:
        return course.quiz_weight, course.assignment_weight
    # A category the teacher set to zero must never inherit the whole grade.
    # Consider a course where quizzes are practice self-checks at weight 0 and
    # the essay carries everything: handing the quizzes 100% while the essay
    # waits to be marked would grade the student on work their teacher
    # declared worthless. Redistribution answers "which category is carrying
    # the grade", never "which one is left".
    if has_quizzes and course.quiz_weight > 0:
        return 100, 0
    if has_assignments and course.assignment_weight > 0:
        return 0, 100
    return 0, 0


def _build_breakdown(
    course: Course,
    quiz_avg: float,
    assignment_avg: float,
    participation_pct: float,
    *,
    has_quiz_items: bool,
    has_assignment_items: bool,
    has_quizzes: bool,
    has_assignments: bool,
    settings: OrgSettings,
    has_gradable_chapters: bool = False,
) -> GradeBreakdown:
    """Assemble one student's breakdown.

    Two different facts arrive here and must not be confused — conflating them
    is exactly the regression an adversarial review caught:

    * ``has_*_items`` — does the course *contain* quizzes / assignments. A fact
      about the course syllabus.
    * ``has_quizzes`` / ``has_assignments`` — has anything actually been graded
      in that category yet (see :func:`category_is_live`). A fact about work
      done so far, and the only thing weight redistribution may depend on.

    Telling a teacher "this course has no quizzes" while four quizzes sit in it
    is a lie; showing 0%/F to a class nobody has marked yet is a different lie.
    They get different states.
    """
    eff_quiz, eff_assignment = effective_weights(course, has_quizzes=has_quizzes, has_assignments=has_assignments)

    def _no_number(state: str) -> GradeBreakdown:
        return GradeBreakdown(
            quiz_avg=0.0,
            quiz_weighted=0.0,
            assignment_avg=0.0,
            assignment_weighted=0.0,
            participation_pct=round(participation_pct, 2),
            participation_weighted=0.0,
            final_score=0.0,
            letter_grade="",
            effective_quiz_weight=0,
            effective_assignment_weight=0,
            has_quiz_items=has_quiz_items,
            has_assignment_items=has_assignment_items,
            has_gradable_chapters=has_gradable_chapters,
            weights_redistributed=False,
            result_state=state,  # type: ignore[arg-type]
        )

    # Vacuous course: nothing gradable exists, so there is no number to
    # compute. Reporting 0% here would read as "failed everything" for a
    # student who has nothing to fail — most of the certificates issued so far
    # came from exactly this shape of course. The official result is
    # completion-based; the certificate gate reduces to progress == 100.
    #
    # Note this says nothing about whether *this* student passed — that is
    # still a question about their progress, and the UI must not present it as
    # a pass on its own.
    if not has_quiz_items and not has_assignment_items:
        return _no_number("completion_pass")

    # The course has gradable items but nothing has been graded in any category
    # yet: first week of term, or a fresh cohort. There is no honest number to
    # show — a weighted mean over zero live categories is 0%, which reads as
    # failure for a class that simply has not been marked.
    if not has_quizzes and not has_assignments:
        return _no_number("not_graded_yet")

    # Everything live is weighted zero — the graded work so far carries no
    # value by the teacher's own configuration, so there is nothing to compute.
    # Falling through would produce 0.0% and a failing symbol built entirely
    # out of work that was never meant to count.
    #
    # This is NOT "nothing has been graded yet": quizzes have been taken and
    # their average is real. Saying otherwise would tell a teacher that
    # percentages appear once someone takes a quiz — an event that has already
    # happened and will never produce the promised effect. The averages are
    # kept so the gradebook can show the marks that do exist.
    if eff_quiz == 0 and eff_assignment == 0:
        return GradeBreakdown(
            quiz_avg=round(quiz_avg, 2),
            quiz_weighted=0.0,
            assignment_avg=round(assignment_avg, 2),
            assignment_weighted=0.0,
            participation_pct=round(participation_pct, 2),
            participation_weighted=0.0,
            final_score=0.0,
            letter_grade="",
            effective_quiz_weight=0,
            effective_assignment_weight=0,
            has_quiz_items=has_quiz_items,
            has_assignment_items=has_assignment_items,
            has_gradable_chapters=has_gradable_chapters,
            weights_redistributed=False,
            result_state="zero_weighted",
        )

    quiz_weighted = quiz_avg * eff_quiz / 100.0
    assignment_weighted = assignment_avg * eff_assignment / 100.0
    final_score = round(quiz_weighted + assignment_weighted, 2)
    return GradeBreakdown(
        quiz_avg=round(quiz_avg, 2),
        quiz_weighted=round(quiz_weighted, 2),
        assignment_avg=round(assignment_avg, 2),
        assignment_weighted=round(assignment_weighted, 2),
        participation_pct=round(participation_pct, 2),
        # Retired as a weighted category (D5); reported for wire compatibility
        # only, and pinned to zero so it cannot influence a score again.
        participation_weighted=0.0,
        final_score=final_score,
        # The institution's own bands when a session resolved them; the shipped
        # scale only as a fallback for callers without one.
        letter_grade=resolve_symbol(final_score, course, settings),
        effective_quiz_weight=eff_quiz,
        effective_assignment_weight=eff_assignment,
        has_quiz_items=has_quiz_items,
        has_assignment_items=has_assignment_items,
        has_gradable_chapters=has_gradable_chapters,
        weights_redistributed=(eff_quiz, eff_assignment) != (course.quiz_weight, course.assignment_weight),
        result_state="graded",
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

    live_quizzes, live_assignments = category_is_live(db, quiz_ids=quiz_ids, assignment_ids=assignment_ids)
    return _build_breakdown(
        course,
        quiz_avg,
        assignment_avg,
        participation_pct,
        has_quiz_items=bool(quiz_ids),
        has_assignment_items=bool(assignment_ids),
        has_quizzes=live_quizzes,
        has_assignments=live_assignments,
        settings=get_org_settings(db),
        has_gradable_chapters=bool(chapter_ids),
    )


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
        # Exclude deactivated (soft-deleted) students so the gradebook,
        # class average, and CSV match the analytics roster — they must not
        # count ghosts (mirrors analytics.py + cohort_capacity.py).
        .filter(Enrollment.course_id == course.id, User.deactivated_at.is_(None))
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
    # Resolved once for the whole course: every student in a class must be
    # graded on the same weights.
    live_quizzes, live_assignments = category_is_live(db, quiz_ids=quiz_ids, assignment_ids=assignment_ids)
    settings = get_org_settings(db)
    results = []
    for user_id, full_name, email in enrollments:
        sid = str(user_id)
        qs = quiz_scores.get(sid, [])
        quiz_avg = sum(qs) / total_quizzes if total_quizzes > 0 else 0.0
        asgs = asgn_scores.get(sid, [])
        assignment_avg = sum(asgs) / total_assignments if total_assignments > 0 else 0.0
        comp = completion_counts.get(sid, 0)
        participation_pct = (comp / total_chapters * 100.0) if total_chapters else 0.0

        breakdown = _build_breakdown(
            course,
            quiz_avg,
            assignment_avg,
            participation_pct,
            has_quiz_items=bool(quiz_ids),
            has_assignment_items=bool(assignment_ids),
            has_quizzes=live_quizzes,
            has_assignments=live_assignments,
            settings=settings,
            has_gradable_chapters=bool(chapter_ids),
        )
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
