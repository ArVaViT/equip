"""Teacher-facing student progress aggregation.

Builds the payload served by ``GET /progress/course/{course_id}/students``:
for every enrolled student, a rollup of chapter completion, best quiz
attempt per chapter, and latest assignment submission per chapter.

The heavy lifting is isolated here so the router module stays thin and
the aggregation math can be unit-tested independently.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func

from app.constants import GRADABLE_CHAPTER_TYPES
from app.core.ids import as_uuids
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt
from app.models.user import User
from app.schemas.locale import normalize_locale
from app.services.grade_calculator import calculate_all_student_grades
from app.services.translation.resolve_for_display import populate_module_texts, populate_spine_texts

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.schemas.grade import GradeBreakdown


def _load_course_structure(
    db: Session, course_id: str
) -> tuple[list[Chapter], dict[str, dict[str, Any]], dict[str, str]]:
    """Return (chapters, module_summary_map, chapter_title_map).

    Kept as a helper because both the aggregation pass and the per-student
    render pass need the same structural lookups.
    """
    modules = (
        db.query(Module)
        .filter(Module.course_id == course_id, Module.deleted_at.is_(None))
        .order_by(Module.order_index)
        .all()
    )
    if modules:
        src = db.query(Course.source_locale).filter(Course.id == course_id).scalar() or "en"
        populate_module_texts(db, modules, source_locale=normalize_locale(src))
    module_map = {m.id: {"id": m.id, "title": m.title, "order_index": m.order_index} for m in modules}

    chapters = (
        db.query(Chapter)
        .join(Module, Chapter.module_id == Module.id)
        .filter(
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .order_by(Module.order_index, Chapter.order_index)
        .all()
    )
    chapter_title_map = {c.id: c.title for c in chapters}
    return chapters, module_map, chapter_title_map


def _load_chapter_quizzes_and_assignments(
    db: Session, chapter_ids: list[str]
) -> tuple[dict[str, list[Quiz]], dict[str, list[Assignment]]]:
    """Group quizzes and assignments by ``chapter_id`` with a single query each."""
    quiz_map: dict[str, list[Quiz]] = {}
    assignment_map: dict[str, list[Assignment]] = {}
    if not chapter_ids:
        return quiz_map, assignment_map

    for q in db.query(Quiz).filter(Quiz.chapter_id.in_(chapter_ids)).all():
        quiz_map.setdefault(q.chapter_id, []).append(q)
    for a in db.query(Assignment).filter(Assignment.chapter_id.in_(chapter_ids)).all():
        assignment_map.setdefault(a.chapter_id, []).append(a)
    return quiz_map, assignment_map


def _aggregate_quiz_results(
    db: Session,
    quiz_map: dict[str, list[Quiz]],
    user_ids: list[str] | None = None,
) -> tuple[
    dict[tuple[str, str], dict[str, Any]],
    dict[tuple[str, str], int],
    dict[str, datetime],
]:
    """Return (best_by_user_chapter, attempts_by_user_chapter, latest_quiz_by_user).

    Aggregates best-score / pass-any / attempt-count per (user, quiz) in
    SQL instead of pulling every attempt row. Then collapses quiz rollups
    into (user, chapter) so the caller only needs a small dictionary.
    """
    best_by_user_chapter: dict[tuple[str, str], dict[str, Any]] = {}
    attempts_by_user_chapter: dict[tuple[str, str], int] = {}
    latest_quiz_by_user: dict[str, datetime] = {}

    all_quiz_ids = [q.id for qs in quiz_map.values() for q in qs]
    if not all_quiz_ids:
        return best_by_user_chapter, attempts_by_user_chapter, latest_quiz_by_user

    quiz_to_chapter: dict[Any, str] = {}
    for ch_id, qs in quiz_map.items():
        for q in qs:
            quiz_to_chapter[q.id] = ch_id

    # The "best" attempt per (user, quiz) must come from a SINGLE row:
    # independent MAX(score) + MAX(max_score) aggregates could combine a
    # high score from one attempt with a high max_score from another and
    # report a percentage that never happened (e.g. 8/10 + 5/20 -> "8/20").
    # Rank attempts by PERCENTAGE (coalescing a 0 max_score to -1 so it
    # sorts last, dialect-safe) and take rn=1; the per-group aggregates
    # (passed_any / attempts / last_completed) ride along as window funcs
    # so it's still one query. Window functions work on both Postgres and
    # the SQLite test backend.
    partition = (QuizAttempt.user_id, QuizAttempt.quiz_id)
    pct_order = func.coalesce(QuizAttempt.score * 1.0 / func.nullif(QuizAttempt.max_score, 0), -1.0)
    # ``user_ids`` scopes the aggregation to a single student (the per-student
    # detail endpoint) or a page of students, so the window functions don't
    # churn over the whole roster when only one row's worth is needed.
    attempt_filters = [QuizAttempt.quiz_id.in_(all_quiz_ids), QuizAttempt.completed_at.isnot(None)]
    if user_ids is not None:
        attempt_filters.append(QuizAttempt.user_id.in_(as_uuids(user_ids)))
    ranked = (
        db.query(
            QuizAttempt.user_id.label("user_id"),
            QuizAttempt.quiz_id.label("quiz_id"),
            QuizAttempt.score.label("score"),
            QuizAttempt.max_score.label("max_score"),
            func.row_number()
            .over(partition_by=partition, order_by=(pct_order.desc(), QuizAttempt.completed_at.desc()))
            .label("rn"),
            func.count().over(partition_by=partition).label("attempts"),
            func.max(case((QuizAttempt.passed.is_(True), 1), else_=0)).over(partition_by=partition).label("passed_any"),
            func.max(QuizAttempt.completed_at).over(partition_by=partition).label("last_completed"),
            # An essay or short-answer quiz is submitted long before it is
            # marked: its open answers carry `graded_at IS NULL` until a teacher
            # reads them, and until then its score is 0 out of the full total.
            # Painted as an ordinary result that is a red 0% — a failure a
            # teacher is shown for work they have not looked at yet.
            func.max(case((QuizAnswer.graded_at.is_(None), 1), else_=0))
            .over(partition_by=partition)
            .label("awaiting_grading"),
        )
        .outerjoin(QuizAnswer, QuizAnswer.attempt_id == QuizAttempt.id)
        .filter(*attempt_filters)
        .subquery()
    )
    quiz_aggs = db.query(ranked).filter(ranked.c.rn == 1).all()

    def _pct(entry: dict[str, Any]) -> float:
        mx = entry["max_score"]
        return entry["score"] / mx if mx else 0.0

    for row in quiz_aggs:
        uid = str(row.user_id)
        resolved_ch_id = quiz_to_chapter.get(row.quiz_id)
        if resolved_ch_id is None:
            continue
        ch_key = (uid, str(resolved_ch_id))
        attempts_by_user_chapter[ch_key] = attempts_by_user_chapter.get(ch_key, 0) + int(row.attempts or 0)
        entry = {
            "chapter_id": str(resolved_ch_id),
            "quiz_id": str(row.quiz_id),
            "score": int(row.score or 0),
            "max_score": int(row.max_score or 0),
            "passed": bool(row.passed_any),
            "awaiting_grading": bool(row.awaiting_grading),
        }
        prev = best_by_user_chapter.get(ch_key)
        # A chapter may hold several quizzes; the representative is the
        # quiz the student did best on by PERCENTAGE, not raw points.
        if prev is None or _pct(entry) > _pct(prev):
            best_by_user_chapter[ch_key] = entry
        if row.last_completed and (uid not in latest_quiz_by_user or row.last_completed > latest_quiz_by_user[uid]):
            latest_quiz_by_user[uid] = row.last_completed
    return best_by_user_chapter, attempts_by_user_chapter, latest_quiz_by_user


def _aggregate_assignment_submissions(
    db: Session,
    assignment_map: dict[str, list[Assignment]],
    user_ids: list[str] | None = None,
) -> tuple[
    dict[tuple[str, str], list[dict[str, Any]]],
    dict[str, Assignment],
    dict[str, datetime],
]:
    """Return (subs_by_user_chapter, assignment_by_id_str, latest_sub_by_user).

    Uses MIN/MAX aggregation to fetch only the latest submission per
    ``(student, assignment)`` instead of every historical revision.
    """
    assignment_to_chapter_str: dict[str, str] = {}
    assignment_by_id_str: dict[str, Assignment] = {}
    for ch_id, als in assignment_map.items():
        for a in als:
            assignment_to_chapter_str[str(a.id)] = str(ch_id)
            assignment_by_id_str[str(a.id)] = a

    subs_by_user_chapter: dict[tuple[str, str], list[dict[str, Any]]] = {}
    latest_sub_by_user: dict[str, datetime] = {}
    all_assignment_ids = list(assignment_by_id_str.keys())
    if not all_assignment_ids:
        return subs_by_user_chapter, assignment_by_id_str, latest_sub_by_user

    # Two-step query: compute MAX(submitted_at) per (student, assignment)
    # in a subquery, then pull the full row that matches. We tie-break on
    # ``id`` below for determinism when two rows share submitted_at.
    # ``assignment_by_id_str`` is keyed by string for the lookups further down;
    # the column is a UUID, so the filter needs the real thing.
    sub_filters = [AssignmentSubmission.assignment_id.in_(as_uuids(all_assignment_ids))]
    if user_ids is not None:
        sub_filters.append(AssignmentSubmission.student_id.in_(as_uuids(user_ids)))
    latest_ts_subq = (
        db.query(
            AssignmentSubmission.student_id.label("student_id"),
            AssignmentSubmission.assignment_id.label("assignment_id"),
            func.max(AssignmentSubmission.submitted_at).label("latest_at"),
        )
        .filter(*sub_filters)
        .group_by(AssignmentSubmission.student_id, AssignmentSubmission.assignment_id)
        .subquery()
    )
    latest_rows = (
        db.query(AssignmentSubmission)
        .join(
            latest_ts_subq,
            (AssignmentSubmission.student_id == latest_ts_subq.c.student_id)
            & (AssignmentSubmission.assignment_id == latest_ts_subq.c.assignment_id)
            & (AssignmentSubmission.submitted_at == latest_ts_subq.c.latest_at),
        )
        .all()
    )

    latest_sub_by_user_assignment: dict[tuple[str, str], dict[str, Any]] = {}
    for s in latest_rows:
        uid = str(s.student_id)
        aid = str(s.assignment_id)
        key = (uid, aid)
        existing = latest_sub_by_user_assignment.get(key)
        if existing is None or str(s.id) > existing["id"]:
            latest_sub_by_user_assignment[key] = {
                "id": str(s.id),
                "assignment_id": aid,
                "status": s.status or "submitted",
                "grade": s.grade,
                "submitted_at": s.submitted_at,
            }
        if s.submitted_at and (uid not in latest_sub_by_user or s.submitted_at > latest_sub_by_user[uid]):
            latest_sub_by_user[uid] = s.submitted_at

    for (uid, aid), sub in latest_sub_by_user_assignment.items():
        asgn_ch_id = assignment_to_chapter_str.get(aid)
        if asgn_ch_id is None:
            continue
        subs_by_user_chapter.setdefault((uid, asgn_ch_id), []).append(sub)
    return subs_by_user_chapter, assignment_by_id_str, latest_sub_by_user


def _load_completed_progress(
    db: Session, chapter_ids: list[str], user_ids: list[str] | None = None
) -> dict[str, dict[str, ChapterProgress]]:
    """Map ``user_id -> chapter_id -> ChapterProgress`` for completed rows only."""
    if not chapter_ids:
        return {}
    progress_filters = [ChapterProgress.chapter_id.in_(chapter_ids), ChapterProgress.completed == True]
    if user_ids is not None:
        progress_filters.append(ChapterProgress.user_id.in_(as_uuids(user_ids)))
    rows = db.query(ChapterProgress).filter(*progress_filters).all()
    out: dict[str, dict[str, ChapterProgress]] = defaultdict(dict)
    for p in rows:
        out[str(p.user_id)][str(p.chapter_id)] = p
    return out


def _load_assignment_titles(db: Session, course: Course, assignment_by_id_str: dict[str, Assignment]) -> dict[str, str]:
    """Phase 5e3: ``assignments.title`` column dropped — bulk-fetch the
    source-language title from cv. Any-locale fallback keeps the lookup
    defensive against missing rows (prefer showing *something* over crashing).
    """
    if not assignment_by_id_str:
        return {}
    from app.services.content_versions import fetch_cv_entity_texts_with_fallback

    source_locale = course.source_locale or "en"
    cv_titles = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="assignment",
        entity_ids=list(assignment_by_id_str.keys()),
        fields=["title"],
        display_locale=source_locale,
        source_locale=source_locale,
    )
    return {aid: (cv_titles.get((aid, "title")) or "") for aid in assignment_by_id_str}


def _build_quiz_results(
    uid: str,
    quiz_map: dict[str, list[Quiz]],
    best_by_user_chapter: dict[tuple[str, str], dict[str, Any]],
    attempts_by_user_chapter: dict[tuple[str, str], int],
    chapter_title_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Per-chapter best-quiz rollup for one student."""
    quiz_results = []
    for ch_id in quiz_map:
        ch_key = (uid, str(ch_id))
        best = best_by_user_chapter.get(ch_key)
        if best is None:
            continue
        quiz_results.append(
            {
                "chapter_title": chapter_title_map.get(str(ch_id), ""),
                "chapter_id": str(ch_id),
                "quiz_id": best["quiz_id"],
                "score": best["score"],
                "max_score": best["max_score"],
                "passed": best["passed"],
                "attempts_used": attempts_by_user_chapter.get(ch_key, 0),
            }
        )
    return quiz_results


def _build_assignment_results(
    uid: str,
    assignment_map: dict[str, list[Assignment]],
    subs_by_user_chapter: dict[tuple[str, str], list[dict[str, Any]]],
    assignment_title_by_id: dict[str, str],
    chapter_title_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Latest-submission-per-assignment rollup for one student."""
    assignment_results = []
    for ch_id, assignments in assignment_map.items():
        ch_key = (uid, str(ch_id))
        submissions = subs_by_user_chapter.get(ch_key, [])
        # Build assignment_id -> latest-submission dict once per chapter so the
        # per-assignment lookup is O(1). Submissions are already filtered to
        # the latest per assignment upstream in _aggregate_assignment_submissions.
        sub_by_assignment: dict[str, dict[str, Any]] = {s["assignment_id"]: s for s in submissions}
        for a in assignments:
            latest = sub_by_assignment.get(str(a.id))
            if latest is None:
                continue
            assignment_results.append(
                {
                    "chapter_title": chapter_title_map.get(str(ch_id), ""),
                    "chapter_id": str(ch_id),
                    "title": assignment_title_by_id.get(str(a.id), ""),
                    "status": latest["status"],
                    "grade": latest["grade"],
                    "max_score": a.max_score or 0,
                }
            )
    return assignment_results


#: States in which there is no honest percentage to show. The board renders
#: these as "—" plus the reason rather than a number, exactly as the gradebook
#: does — a 0 here reads as "failed everything" to the one person who acts on it.
_NO_NUMBER_STATES = {"completion_pass", "not_graded_yet", "zero_weighted", "not_assessed"}

#: A student the calculator returned no row for — deactivated mid-request, or an
#: enrolment race. Blank, never zero: an absent number must not read as failure.
_EMPTY_OFFICIAL: dict[str, Any] = {
    "quiz_avg": None,
    "assignment_avg": None,
    "overall_grade": None,
    "manual_grade": None,
    "result_state": "not_graded_yet",
    "letter_grade": None,
}


def _official_row(breakdown: GradeBreakdown, manual_grade: str | None) -> dict[str, Any]:
    """The progress board's numbers, taken from the canonical calculator (D14).

    This board used to do its own arithmetic, and it disagreed with the
    gradebook about the same student on three separate counts:

    * it divided by the work the student had **attempted**, not the work they
      were **set** — one quiz out of four at 100% read 100 here and 25 in the
      gradebook;
    * it took an unweighted mean of the two category averages, ignoring the
      weights the teacher had configured entirely;
    * it never consulted overrides, exemptions, institutional bands, or the
      empty-category redistribution, so none of the last four PRs reached it.

    One number, one meaning, both screens.
    """
    return {
        # A category average is a number only once something in it has been
        # marked. Nobody has read the essays yet is not the same fact as the
        # essays were bad, and 0% on a teacher's board says the second one.
        "quiz_avg": round(breakdown.quiz_avg) if breakdown.student_has_quiz_marks else None,
        "assignment_avg": round(breakdown.assignment_avg) if breakdown.student_has_assignment_marks else None,
        # Sent unrounded. Rounding here and again in the browser gave the same
        # student 86% on one screen and 87% on another (Python rounds .5 to
        # even, JavaScript rounds it up), and a rounded 89.5 printed as "90%"
        # beside the letter B, which the school's own band table calls A.
        # One formatter, on the client, from the raw number.
        "overall_grade": None if breakdown.result_state in _NO_NUMBER_STATES else breakdown.final_score,
        # The override, when present, IS the official grade (D7) — it wins for
        # the certificate, the ведомость and the student's own page, so a board
        # showing the computed number beside it would be showing the unofficial
        # one. Carried separately rather than folded in, because the pair is the
        # point: a teacher must be able to see that a grade was set by hand.
        "manual_grade": manual_grade,
        "result_state": breakdown.result_state,
        "letter_grade": breakdown.letter_grade or None,
    }


def _latest_activity_iso(enrolled_at: datetime | None, quiz_ts: datetime | None, sub_ts: datetime | None) -> str | None:
    latest = enrolled_at
    for ts in (quiz_ts, sub_ts):
        if ts and (latest is None or ts > latest):
            latest = ts
    return latest.isoformat() if latest else None


def _build_chapter_infos(
    uid: str,
    chapters: list[Chapter],
    user_progress: dict[str, ChapterProgress],
    best_by_user_chapter: dict[tuple[str, str], dict[str, Any]],
    subs_by_user_chapter: dict[tuple[str, str], list[dict[str, Any]]],
    assignment_by_id_str: dict[str, Assignment],
    quiz_map: dict[str, list[Quiz]] | None = None,
    assignment_map: dict[str, list[Assignment]] | None = None,
) -> list[dict[str, Any]]:
    """Per-chapter completion + embedded quiz/assignment result for one student.

    Shared by the row-expand detail (progress board) and the full gradebook
    matrix, which both need the per-chapter view for a student.

    ``gradable_item`` names the piece of work behind the chapter regardless of
    whether the student ever touched it — which is exactly the case where a
    teacher reaches for an exemption. The result blocks below can't stand in for
    it: they exist only once there is a submission or an attempt.
    """
    chapter_infos = []
    for ch in chapters:
        cp = user_progress.get(str(ch.id))
        ch_key = (uid, str(ch.id))
        best = best_by_user_chapter.get(ch_key)
        quiz_data = None
        if best is not None:
            quiz_data = {
                "score": best["score"],
                "max_score": best["max_score"],
                "passed": best["passed"],
                "awaiting_grading": best.get("awaiting_grading", False),
            }
        ch_subs = subs_by_user_chapter.get(ch_key, [])
        asgn_data = None
        if ch_subs:
            latest_sub = max(ch_subs, key=lambda s: s["submitted_at"] or datetime.min)
            asgn = assignment_by_id_str.get(latest_sub["assignment_id"])
            max_score = asgn.max_score if asgn is not None else 100
            asgn_data = {"status": latest_sub["status"], "grade": latest_sub["grade"], "max_score": max_score}
        gradable_item = None
        chapter_quizzes = (quiz_map or {}).get(str(ch.id)) or []
        chapter_assignments = (assignment_map or {}).get(str(ch.id)) or []
        if chapter_quizzes:
            gradable_item = {"type": "quiz", "id": str(chapter_quizzes[0].id)}
        elif chapter_assignments:
            gradable_item = {"type": "assignment", "id": str(chapter_assignments[0].id)}

        chapter_infos.append(
            {
                "id": str(ch.id),
                "title": ch.title,
                "module_id": str(ch.module_id),
                "chapter_type": ch.chapter_type or "reading",
                "requires_completion": bool(ch.requires_completion),
                "completed": cp is not None,
                "completed_by": cp.completion_type if cp else None,
                "quiz_result": quiz_data,
                "assignment_result": asgn_data,
                "gradable_item": gradable_item,
            }
        )
    return chapter_infos


def _latest_activity_by_user(db: Session, course_id: str) -> tuple[dict[str, datetime], dict[str, datetime]]:
    """Last completed quiz attempt and last submission per student, two queries.

    "Last seen" is all the board wants from these tables; deriving it from the
    full per-chapter rollups meant running window functions over every attempt
    in the course to read one MAX out of each.
    """
    quiz_rows = (
        db.query(QuizAttempt.user_id, func.max(QuizAttempt.completed_at))
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Chapter, Chapter.id == Quiz.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .filter(
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            QuizAttempt.completed_at.isnot(None),
        )
        .group_by(QuizAttempt.user_id)
        .all()
    )
    sub_rows = (
        db.query(AssignmentSubmission.student_id, func.max(AssignmentSubmission.submitted_at))
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .join(Chapter, Chapter.id == Assignment.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .filter(
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .group_by(AssignmentSubmission.student_id)
        .all()
    )
    return (
        {str(uid): ts for uid, ts in quiz_rows if ts is not None},
        {str(uid): ts for uid, ts in sub_rows if ts is not None},
    )


def build_course_student_progress(db: Session, course: Course, course_id: str) -> dict[str, Any]:
    """Teacher progress-board LIST payload: one lightweight summary row per
    enrolled student — scalars plus server-computed quiz/assignment/overall
    averages. The heavy per-chapter breakdown (``chapters``) and the full
    quiz/assignment result arrays are NOT included here; they're fetched
    per-student on row expand via :func:`build_student_chapter_detail`.

    This keeps the list response O(students) instead of O(students x chapters):
    a 250-student x 240-chapter course used to emit ~60k chapter objects in one
    response. The grades come from the canonical calculator (D14) in one batch
    call, so this board can no longer disagree with the gradebook about the same
    student.
    """
    populate_spine_texts(db, [course])
    chapters, module_map, _chapter_titles = _load_course_structure(db, course_id)
    gradable_chapter_ids = [c.id for c in chapters if c.chapter_type in GRADABLE_CHAPTER_TYPES]

    # Only two timestamps are needed from the result tables now — "last seen".
    # This used to run the full per-chapter quiz and submission rollups (window
    # functions over every attempt in the course, plus a title lookup) purely to
    # feed averages this board no longer computes for itself.
    latest_quiz_by_user, latest_sub_by_user = _latest_activity_by_user(db, course_id)
    progress_by_user = _load_completed_progress(db, gradable_chapter_ids)

    enrollments = (
        db.query(Enrollment, User)
        .join(User, Enrollment.user_id == User.id)
        # Exclude deactivated (soft-deleted) students so the teacher progress
        # board + total_students match the analytics roster (mirrors
        # analytics.py / cohort_capacity.py).
        .filter(Enrollment.course_id == course_id, User.deactivated_at.is_(None))
        .all()
    )

    # One batch call for the whole roster — the same one the gradebook makes,
    # so the two screens cannot drift apart again.
    official_by_student = {
        row["student_id"]: _official_row(row["breakdown"], row["manual_grade"])
        for row in calculate_all_student_grades(db, course)
    }

    student_progress = []
    for enrollment, user in enrollments:
        uid = str(user.id)
        user_progress = progress_by_user.get(uid, {})
        chapters_completed = sum(1 for cid in gradable_chapter_ids if cid in user_progress)

        student_progress.append(
            {
                "id": uid,
                "full_name": user.full_name or user.email,
                "email": user.email,
                "enrolled_at": enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
                "progress": enrollment.progress,
                "chapters_completed": chapters_completed,
                "total_chapters": len(gradable_chapter_ids),
                **official_by_student.get(uid, _EMPTY_OFFICIAL),
                "last_activity": _latest_activity_iso(
                    enrollment.enrolled_at, latest_quiz_by_user.get(uid), latest_sub_by_user.get(uid)
                ),
            }
        )

    return {
        "course_id": course_id,
        "course_title": course.title,
        "total_chapters": len(gradable_chapter_ids),
        "total_students": len(enrollments),
        "modules": list(module_map.values()),
        "students": student_progress,
    }


def build_student_chapter_detail(db: Session, course: Course, course_id: str, student_id: str) -> dict[str, Any]:
    """Per-student detail for the progress-board row expansion: the full
    per-chapter breakdown plus the quiz/assignment result arrays for ONE
    student. Every aggregation is scoped to ``student_id`` so this stays cheap
    regardless of roster size.
    """
    populate_spine_texts(db, [course])
    chapters, _module_map, chapter_title_map = _load_course_structure(db, course_id)
    chapter_ids = [c.id for c in chapters]

    quiz_map, assignment_map = _load_chapter_quizzes_and_assignments(db, chapter_ids)
    best_by_user_chapter, attempts_by_user_chapter, _latest_quiz = _aggregate_quiz_results(
        db, quiz_map, user_ids=[student_id]
    )
    subs_by_user_chapter, assignment_by_id_str, _latest_sub = _aggregate_assignment_submissions(
        db, assignment_map, user_ids=[student_id]
    )
    assignment_title_by_id = _load_assignment_titles(db, course, assignment_by_id_str)
    progress_by_user = _load_completed_progress(db, chapter_ids, user_ids=[student_id])
    user_progress = progress_by_user.get(student_id, {})

    quiz_results = _build_quiz_results(
        student_id, quiz_map, best_by_user_chapter, attempts_by_user_chapter, chapter_title_map
    )
    assignment_results = _build_assignment_results(
        student_id, assignment_map, subs_by_user_chapter, assignment_title_by_id, chapter_title_map
    )

    chapter_infos = _build_chapter_infos(
        student_id,
        chapters,
        user_progress,
        best_by_user_chapter,
        subs_by_user_chapter,
        assignment_by_id_str,
        quiz_map,
        assignment_map,
    )

    return {
        "student_id": student_id,
        "chapters": chapter_infos,
        "quiz_results": quiz_results,
        "assignment_results": assignment_results,
    }


def build_course_gradebook_matrix(db: Session, course: Course, course_id: str) -> dict[str, Any]:
    """Full students x chapters matrix for the teacher GRADEBOOK.

    Unlike the progress-board list (which is a per-student summary), the
    gradebook renders an always-visible spreadsheet of every student against
    every chapter, so it genuinely needs the per-chapter breakdown for the
    whole roster. The top-level quiz/assignment result arrays the board's
    detail carries are omitted — the gradebook reads only the per-chapter
    ``quiz_result`` / ``assignment_result`` embedded in each chapter cell.
    """
    populate_spine_texts(db, [course])
    chapters, module_map, _chapter_title_map = _load_course_structure(db, course_id)
    chapter_ids = [c.id for c in chapters]
    gradable_chapter_ids = [c.id for c in chapters if c.chapter_type in GRADABLE_CHAPTER_TYPES]

    quiz_map, assignment_map = _load_chapter_quizzes_and_assignments(db, chapter_ids)
    best_by_user_chapter, _attempts, _latest_quiz = _aggregate_quiz_results(db, quiz_map)
    subs_by_user_chapter, assignment_by_id_str, _latest_sub = _aggregate_assignment_submissions(db, assignment_map)
    # The matrix renders a completion cell for EVERY chapter (reading/video/
    # audio included), so load progress for all of them — the gradable subset
    # is only the denominator of the chapters_completed/total_chapters counts.
    # (Loading just gradable_chapter_ids here made every completed
    # non-gradable chapter render as not-completed and undercount totals.)
    progress_by_user = _load_completed_progress(db, chapter_ids)

    enrollments = (
        db.query(Enrollment, User)
        .join(User, Enrollment.user_id == User.id)
        # Mirror the board/analytics roster: deactivated students are excluded.
        .filter(Enrollment.course_id == course_id, User.deactivated_at.is_(None))
        .all()
    )

    students = []
    for enrollment, user in enrollments:
        uid = str(user.id)
        user_progress = progress_by_user.get(uid, {})
        students.append(
            {
                "id": uid,
                "full_name": user.full_name or user.email,
                "email": user.email,
                "progress": enrollment.progress,
                "chapters_completed": sum(1 for cid in gradable_chapter_ids if cid in user_progress),
                "total_chapters": len(gradable_chapter_ids),
                "chapters": _build_chapter_infos(
                    uid,
                    chapters,
                    user_progress,
                    best_by_user_chapter,
                    subs_by_user_chapter,
                    assignment_by_id_str,
                    quiz_map,
                    assignment_map,
                ),
            }
        )

    return {
        "course_id": course_id,
        "course_title": course.title,
        "total_chapters": len(gradable_chapter_ids),
        "total_students": len(enrollments),
        "modules": list(module_map.values()),
        "students": students,
    }
