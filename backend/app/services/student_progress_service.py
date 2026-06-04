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
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAttempt
from app.models.user import User
from app.schemas.locale import normalize_locale
from app.services.translation.resolve_for_display import populate_module_texts, populate_spine_texts

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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
        )
        .filter(
            QuizAttempt.quiz_id.in_(all_quiz_ids),
            QuizAttempt.completed_at.isnot(None),
        )
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
    latest_ts_subq = (
        db.query(
            AssignmentSubmission.student_id.label("student_id"),
            AssignmentSubmission.assignment_id.label("assignment_id"),
            func.max(AssignmentSubmission.submitted_at).label("latest_at"),
        )
        .filter(AssignmentSubmission.assignment_id.in_(all_assignment_ids))
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


def _load_completed_progress(db: Session, chapter_ids: list[str]) -> dict[str, dict[str, ChapterProgress]]:
    """Map ``user_id -> chapter_id -> ChapterProgress`` for completed rows only."""
    if not chapter_ids:
        return {}
    rows = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.chapter_id.in_(chapter_ids),
            ChapterProgress.completed == True,
        )
        .all()
    )
    out: dict[str, dict[str, ChapterProgress]] = defaultdict(dict)
    for p in rows:
        out[str(p.user_id)][str(p.chapter_id)] = p
    return out


def build_course_student_progress(db: Session, course: Course, course_id: str) -> dict[str, Any]:
    """Return the full teacher-dashboard progress payload for a course."""
    populate_spine_texts(db, [course])
    chapters, module_map, chapter_title_map = _load_course_structure(db, course_id)
    chapter_ids = [c.id for c in chapters]
    gradable_chapter_ids = [c.id for c in chapters if c.chapter_type in GRADABLE_CHAPTER_TYPES]

    quiz_map, assignment_map = _load_chapter_quizzes_and_assignments(db, chapter_ids)

    best_by_user_chapter, attempts_by_user_chapter, latest_quiz_by_user = _aggregate_quiz_results(db, quiz_map)

    subs_by_user_chapter, assignment_by_id_str, latest_sub_by_user = _aggregate_assignment_submissions(
        db, assignment_map
    )

    # Phase 5e3: assignments.title column dropped — bulk-fetch the
    # source-language title from cv for the dashboard rendering below.
    # Any-locale fallback keeps the lookup defensive against missing
    # rows (the dashboard prefers showing *something* over crashing).
    assignment_title_by_id: dict[str, str] = {}
    if assignment_by_id_str:
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
        assignment_title_by_id = {aid: (cv_titles.get((aid, "title")) or "") for aid in assignment_by_id_str}

    progress_by_user = _load_completed_progress(db, chapter_ids)

    enrollments = (
        db.query(Enrollment, User)
        .join(User, Enrollment.user_id == User.id)
        .filter(Enrollment.course_id == course_id)
        .all()
    )

    student_progress = []
    for enrollment, user in enrollments:
        uid = str(user.id)

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

        assignment_results = []
        for ch_id, assignments in assignment_map.items():
            ch_key = (uid, str(ch_id))
            submissions = subs_by_user_chapter.get(ch_key, [])
            # Build assignment_id -> latest-submission dict once per chapter
            # so the per-assignment lookup is O(1) instead of an O(M) list
            # comprehension. Submissions are already filtered to the latest
            # per assignment upstream in _aggregate_assignment_submissions.
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

        user_progress = progress_by_user.get(uid, {})
        chapters_completed = sum(1 for cid in gradable_chapter_ids if cid in user_progress)

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
                }
            ch_subs = subs_by_user_chapter.get(ch_key, [])
            asgn_data = None
            if ch_subs:
                latest_sub = max(ch_subs, key=lambda s: s["submitted_at"] or datetime.min)
                asgn = assignment_by_id_str.get(latest_sub["assignment_id"])
                max_score = asgn.max_score if asgn is not None else 100
                asgn_data = {
                    "status": latest_sub["status"],
                    "grade": latest_sub["grade"],
                    "max_score": max_score,
                }
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
                }
            )

        latest_activity = enrollment.enrolled_at
        for ts in (latest_quiz_by_user.get(uid), latest_sub_by_user.get(uid)):
            if ts and (latest_activity is None or ts > latest_activity):
                latest_activity = ts

        student_progress.append(
            {
                "id": uid,
                "full_name": user.full_name or user.email,
                "email": user.email,
                "enrolled_at": enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
                "progress": enrollment.progress,
                "chapters_completed": chapters_completed,
                "total_chapters": len(gradable_chapter_ids),
                "quiz_results": quiz_results,
                "assignment_results": assignment_results,
                "last_activity": latest_activity.isoformat() if latest_activity else None,
                "chapters": chapter_infos,
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
