"""A student's own standing in one course (D10).

Everything here already existed — the weighted pair, the per-item results, the
excused list — and all of it was behind ``require_teacher``. A student could
see a progress bar, individual quiz scores, and, if a teacher had hand-set one,
a bare letter on their dashboard. They could not see their course grade.

That is the wrong way round for the thing this phase is building toward: the
certificate pass-gate goes live at the end of Phase 2, and the design's first
rule is that enforcement never ships before the visibility that explains it. A
student refused a certificate must already know why, and have known for weeks.

Assembled from the same builders the teacher's screens use, deliberately. Two
readers of one calculation cannot drift; two calculations of one number always
do, and this rebuild spent four PRs proving it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.grade_calculator import calculate_student_grade_for_course
from app.services.grade_exemption_service import excused_item_ids
from app.services.grade_override import resolve_official_row
from app.services.student_progress_service import build_student_chapter_detail

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.models.course import Course
    from app.models.enrollment import Enrollment

#: States where no honest number exists, so the student is told the reason
#: instead of being shown a zero. Same vocabulary as every teacher surface.
_NO_NUMBER_STATES = {"completion_pass", "not_graded_yet", "zero_weighted", "not_assessed"}

#: Its rule is completion-native (D2) and not implemented yet, so the weighted
#: percentage is not this course's result and must not be presented as one.
_COMPLETION_NATIVE_SCHEMES = {"pass_fail"}


def _quiz_items(detail: dict[str, Any], excused_quiz_ids: set) -> list[dict[str, Any]]:
    items = []
    for result in detail["quiz_results"]:
        chapter = next((c for c in detail["chapters"] if c["id"] == result["chapter_id"]), None)
        excused = _is_excused(chapter, result.get("quiz_id"), excused_quiz_ids)
        quiz_result = (chapter or {}).get("quiz_result") or {}
        awaiting = bool(quiz_result.get("awaiting_grading"))
        if excused:
            status, score = "excused", None
        elif awaiting:
            # Submitted, unread. Its score is a running total, and showing that
            # to the person waiting on it is how a student concludes they failed
            # an essay nobody has opened.
            status, score = "pending_review", None
        else:
            status = "graded"
            score = round(result["score"] / result["max_score"] * 100, 1) if result["max_score"] else 0.0
        items.append(
            {
                "chapter_id": result["chapter_id"],
                "title": result["chapter_title"],
                "kind": "quiz",
                "status": status,
                "score": score,
            }
        )
    return items


def _is_excused(chapter: dict[str, Any] | None, item_id: Any, excused_ids: set) -> bool:
    if item_id is not None and _as_uuid(item_id) in excused_ids:
        return True
    # An exemption also marks the chapter, which is the only signal left when
    # the item itself has since been deleted.
    return bool(chapter and chapter.get("completed_by") == "excused")


def _as_uuid(value: Any) -> Any:
    from uuid import UUID as _UUID

    try:
        return _UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return value


def _assignment_items(detail: dict[str, Any], excused_assignment_ids: set) -> list[dict[str, Any]]:
    items = []
    for result in detail["assignment_results"]:
        chapter = next((c for c in detail["chapters"] if c["id"] == result["chapter_id"]), None)
        gradable = (chapter or {}).get("gradable_item") or {}
        item_id = gradable.get("id") if gradable.get("type") == "assignment" else None
        if _is_excused(chapter, item_id, excused_assignment_ids):
            status, score = "excused", None
        elif result["grade"] is None:
            # Handed in and waiting, or returned for revision — either way there
            # is no mark yet, and inventing one would be the same lie as above.
            status, score = ("pending_review", None) if result["status"] != "not_submitted" else ("not_submitted", None)
        else:
            status = "graded"
            score = round(result["grade"] / result["max_score"] * 100, 1) if result["max_score"] else 0.0
        items.append(
            {
                "chapter_id": result["chapter_id"],
                "title": result["title"] or result["chapter_title"],
                "kind": "assignment",
                "status": status,
                "score": score,
            }
        )
    return items


def _missing_items(detail: dict[str, Any], listed_chapters: set[str], excused: tuple[set, set]) -> list[dict[str, Any]]:
    """Work the student owes and has not started.

    The result arrays only carry items with a submission or an attempt, so
    without this the list silently omits everything untouched — which is
    precisely the work a student needs to see.
    """
    excused_quizzes, excused_assignments = excused
    items = []
    for chapter in detail["chapters"]:
        if chapter["id"] in listed_chapters:
            continue
        gradable = chapter.get("gradable_item")
        if not gradable:
            continue
        excused_here = (
            _as_uuid(gradable["id"]) in (excused_quizzes if gradable["type"] == "quiz" else excused_assignments)
            or chapter.get("completed_by") == "excused"
        )
        items.append(
            {
                "chapter_id": chapter["id"],
                "title": chapter["title"],
                "kind": gradable["type"],
                "status": "excused" if excused_here else "not_submitted",
                "score": None,
            }
        )
    return items


def build_my_course_grade(db: Session, course: Course, enrollment: Enrollment, student_id: UUID) -> dict[str, Any]:
    """The student's own view of one course. Never anyone else's."""
    breakdown = calculate_student_grade_for_course(db, course, student_id)
    detail = build_student_chapter_detail(db, course, course.id, str(student_id))
    excused = excused_item_ids(db, student_id=student_id, course_id=course.id)

    items = _quiz_items(detail, excused[0]) + _assignment_items(detail, excused[1])
    listed = {item["chapter_id"] for item in items}
    items += _missing_items(detail, listed, excused)

    scheme = course.grading_scheme
    withheld = scheme in _COMPLETION_NATIVE_SCHEMES
    no_number = breakdown.result_state in _NO_NUMBER_STATES or withheld

    official_row = resolve_official_row(db, student_id=student_id, course_id=course.id)
    official_grade = None
    if official_row is not None:
        if official_row.override_code is not None:
            official_grade = official_row.override_code
        elif official_row.override_score is not None:
            official_grade = f"{official_row.override_score:.2f}"

    return {
        "course_id": course.id,
        "grading_scheme": scheme,
        "pass_threshold": course.pass_threshold,
        "progress": enrollment.progress,
        "current_score": None if no_number else breakdown.current_score,
        "current_symbol": breakdown.current_letter_grade or None if not no_number else None,
        "final_score": None if no_number else breakdown.final_score,
        "final_symbol": breakdown.letter_grade or None if not no_number else None,
        "scores_differ": False if no_number else breakdown.scores_differ,
        "result_state": breakdown.result_state,
        "scores_withheld": withheld,
        "official_grade": official_grade,
        # The note written TO the student. `reason` — the note about them,
        # written for the institution — is never read here (D7).
        "comment": official_row.comment if official_row is not None else None,
        "items": sorted(items, key=lambda i: (i["kind"], i["title"])),
    }
