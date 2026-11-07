"""What is waiting for a teacher to mark it.

An essay is submitted and then nothing happens until somebody opens the right
course, the right chapter and the right attempt. Until now the platform had no
place that said "seven pieces of work are waiting on you" — the teacher had to
already suspect it. For a school taking its first cohort, that is the gap where
student work quietly sits for a fortnight.

Two shapes of waiting, and they are counted together because the teacher's
question is "what do I owe", not "which table is it in":

* an open quiz answer nobody has read (``quiz_answers.graded_at IS NULL``);
* a submitted assignment with no mark on it.

Work the student owes — never handed in, or handed back for revision — is
deliberately **not** here. That is the student's move, and putting it in a
teacher's queue would make the number unactionable, which is how a queue stops
being read.

The counted set must match, row for row, what the teacher finds when they open
the grading page (``GET /quizzes/{id}/pending-answers`` and the assignment
submission list). A badge that says three when the page shows two is worse than
no badge: it never reaches zero, and a queue that cannot be emptied is a queue
that gets ignored. Every filter below exists because that page has it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func as sqlfunc
from sqlalchemy import select

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.models.user import User
from app.schemas.locale import LocaleCode, normalize_locale
from app.services import quiz_service
from app.services.grade_exemption_service import excused_item_ids
from app.services.late_work import first_handed_in, is_late
from app.services.zachet import latest_submissions

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


def unread_answer_filters() -> tuple:
    """What makes a quiz answer "waiting on a teacher", as one definition.

    Three surfaces ask this question — the grading page, the dashboard count,
    and the certificate explainer that tells a student their essay has not been
    read yet. Written out three times they drift, and the drift is invisible:
    the student is told one thing and the teacher's queue shows another, with
    neither number obviously wrong.
    """
    return (
        QuizAttempt.completed_at.isnot(None),
        QuizAnswer.graded_at.is_(None),
        QuizAnswer.text_answer.isnot(None),
        QuizQuestion.question_type.in_(quiz_service.MANUAL_GRADED_QUESTION_TYPES),
    )


def quizzes_awaiting_marking(db: Session, student_id: UUID, quiz_ids: list) -> set:
    """Quizzes where this student has a finished attempt with an unread answer.

    One query for the course, not one per quiz: this runs on the student's own
    course page, which is the most-loaded authenticated screen there is.
    """
    if not quiz_ids:
        return set()
    rows = (
        db.query(QuizAttempt.quiz_id)
        .join(QuizAnswer, QuizAnswer.attempt_id == QuizAttempt.id)
        .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
        .filter(
            QuizAttempt.quiz_id.in_(quiz_ids),
            QuizAttempt.user_id == student_id,
            # The same definition the teacher's queue uses. Told "your essay is
            # not marked yet" for an answer that is not on the teacher's list,
            # a student waits for something that will never arrive.
            *unread_answer_filters(),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def work_awaiting_marking(
    db: Session,
    student_id: UUID,
    *,
    course_id: str,
    quizzes: list,
    assignments: list,
    submissions: dict | None = None,
    excused: set[str] | None = None,
) -> set[str]:
    """Item ids where this student's work is waiting on a teacher.

    An unread open answer in a finished quiz attempt, or a submitted
    assignment with no mark on it — minus anything the student was excused
    from, which is not owed and so cannot be waiting. Returned work is not
    here: it has been read, and the ball is with the student.

    One definition for everything that asks "is anything of theirs unread":
    the certificate explainer that names the unmarked essay, and the
    ведомость that refuses to close over it. Written out twice they drift,
    and the drift is a student told "your essay is not marked yet" on one
    screen while a director signs a page that counted it as a zero.

    ``submissions`` and ``excused`` are taken from a caller that has already
    fetched them for its own purposes; left out, they are fetched here.
    """
    if submissions is None:
        submissions = latest_submissions(db, student_id=student_id, assignment_ids=[a.id for a in assignments])
    if excused is None:
        excused_quiz_ids, excused_assignment_ids = excused_item_ids(db, student_id=student_id, course_id=course_id)
        excused = {str(i) for i in excused_quiz_ids} | {str(i) for i in excused_assignment_ids}

    awaiting = {str(q) for q in quizzes_awaiting_marking(db, student_id, [q.id for q in quizzes])}
    for assignment in assignments:
        submission = submissions.get(assignment.id)
        if submission is not None and submission["status"] == "submitted" and submission["grade"] is None:
            awaiting.add(str(assignment.id))
    return awaiting - excused


def waiting_answers(db: Session, teacher_id: UUID):
    """Every open quiz answer waiting on this teacher, as one query to build on.

    The one definition of "an unread answer is waiting on me". The dashboard
    count, the grouped list and the marking run each select different columns
    from it, and none of them adds a filter of its own: a badge counting work
    the grading page would not show is a badge that can never reach zero.

    The question-type filter (inside ``unread_answer_filters``) has no test
    that fails without it, and that is deliberate: a CHECK constraint limits
    the column to the four known types, so the row it would exclude cannot
    exist today. It is parity with the quiz page, for the day a fifth type is
    added — and ``test_every_question_type_is_either_auto_marked_or_hand_marked``
    is what actually fires on that day.
    """
    return (
        db.query(QuizAnswer)
        .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
        .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
        .join(User, User.id == QuizAttempt.user_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Chapter, Chapter.id == Quiz.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .filter(
            Course.created_by == teacher_id,
            Course.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            *unread_answer_filters(),
            # Deactivated students drop out of the grading queue (#786), so
            # they must drop out of the count of it too.
            User.deactivated_at.is_(None),
        )
    )


def _latest_submission_ids(teacher_id: UUID):
    """The one submission per student and assignment that decides its state.

    A student who hands in a second version leaves the first in the table.
    Counted as two, the teacher was shown the stale draft first — and once the
    second was marked elsewhere, the first held the dashboard number above
    zero for good. Same ordering as ``zachet.latest_submissions`` (newest
    ``submitted_at``, then ``graded_at``, then ``id``), so the teacher's queue
    and the student's own «not marked yet» agree about which version counts.
    """
    ranked = (
        select(
            AssignmentSubmission.id.label("id"),
            sqlfunc.row_number()
            .over(
                partition_by=(AssignmentSubmission.assignment_id, AssignmentSubmission.student_id),
                order_by=(
                    AssignmentSubmission.submitted_at.desc().nulls_last(),
                    AssignmentSubmission.graded_at.desc().nulls_last(),
                    AssignmentSubmission.id.desc(),
                ),
            )
            .label("rank"),
        )
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .join(Chapter, Chapter.id == Assignment.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .where(Course.created_by == teacher_id)
        .subquery()
    )
    return select(ranked.c.id).where(ranked.c.rank == 1)


def waiting_submissions(db: Session, teacher_id: UUID):
    """Every submitted, unmarked assignment waiting on this teacher.

    The twin of ``waiting_answers``. ``returned`` is excluded: it has been
    read, and the ball is with the student. Only the latest version of each
    student's work counts — see ``_latest_submission_ids``.
    """
    return (
        db.query(AssignmentSubmission)
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .join(User, User.id == AssignmentSubmission.student_id)
        .join(Chapter, Chapter.id == Assignment.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .filter(
            Course.created_by == teacher_id,
            Course.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            AssignmentSubmission.status == "submitted",
            AssignmentSubmission.grade.is_(None),
            User.deactivated_at.is_(None),
            AssignmentSubmission.id.in_(_latest_submission_ids(teacher_id)),
        )
    )


def pending_by_course(db: Session, teacher_id: UUID) -> dict[str, int]:
    """``{course_id: count}`` of work awaiting this teacher, courses they own.

    Two queries for every course they teach, not two per course: a dashboard
    that costs a round trip per row is a dashboard that gets removed the first
    time somebody teaches twenty courses.
    """
    counts: dict[str, int] = {}
    for base, counted in (
        (waiting_answers(db, teacher_id), QuizAnswer.id),
        (waiting_submissions(db, teacher_id), AssignmentSubmission.id),
    ):
        rows = base.with_entities(Chapter.course_id, sqlfunc.count(counted)).group_by(Chapter.course_id).all()
        for course_id, count in rows:
            counts[course_id] = counts.get(course_id, 0) + int(count or 0)
    return counts


def pending_summary(db: Session, teacher_id: UUID) -> dict[str, Any]:
    """The rollup a teacher's dashboard shows: a total and a per-course map."""
    by_course = pending_by_course(db, teacher_id)
    return {"total": sum(by_course.values()), "by_course": by_course}


# ---------------------------------------------------------------------------
# The queue itself, not the count of it
# ---------------------------------------------------------------------------
#
# Grouped by item rather than by student, because that is how the marking
# actually goes: thirty answers to the same prompt in a row, the standard
# loaded once. Read across a whole paper instead and the standard drifts
# between question one and question four, which is the thing a rubric exists to
# prevent and the thing a queue can prevent for free.
#
# The teacher's own phrase for this is «что мне сегодня проверить», and the
# answer has to fit on a phone screen.


def _oldest_first(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Oldest first. A queue sorted by size buries the essay that has been
    # waiting three weeks under the assignment twelve people just handed in,
    # and the three-week-old one is the one somebody is upset about.
    return sorted(groups, key=lambda g: (g["oldest"] is None, g["oldest"]))


def waiting_groups(db: Session, teacher_id: UUID, *, display_locale: str | None = None) -> list[dict[str, Any]]:
    """Every piece of work waiting on this teacher, gathered by the item it answers.

    Two queries, one per kind. A group per course *and* item, because the same
    prompt reused in two courses is two conversations with two cohorts.
    """
    groups: list[dict[str, Any]] = []

    quiz_rows = (
        waiting_answers(db, teacher_id)
        .with_entities(
            Chapter.course_id,
            QuizQuestion.id.label("item_id"),
            Chapter.id.label("chapter_id"),
            Chapter.title.label("chapter_title"),
            sqlfunc.count(QuizAnswer.id).label("waiting"),
            sqlfunc.min(QuizAttempt.completed_at).label("oldest"),
        )
        .group_by(Chapter.course_id, QuizQuestion.id, Chapter.id, Chapter.title)
        .all()
    )
    for row in quiz_rows:
        groups.append(
            {
                "kind": "quiz_answer",
                "item_id": str(row.item_id),
                "course_id": row.course_id,
                "chapter_id": row.chapter_id,
                "title": row.chapter_title,
                "waiting": int(row.waiting or 0),
                "oldest": row.oldest,
            }
        )

    assignment_rows = (
        waiting_submissions(db, teacher_id)
        .with_entities(
            Chapter.course_id,
            Assignment.id.label("item_id"),
            Chapter.id.label("chapter_id"),
            Chapter.title.label("chapter_title"),
            Assignment.max_score,
            sqlfunc.count(AssignmentSubmission.id).label("waiting"),
            sqlfunc.min(AssignmentSubmission.submitted_at).label("oldest"),
        )
        .group_by(Chapter.course_id, Assignment.id, Assignment.max_score, Chapter.id, Chapter.title)
        .all()
    )
    for assignment_row in assignment_rows:
        groups.append(
            {
                "kind": "assignment",
                "item_id": str(assignment_row.item_id),
                "course_id": assignment_row.course_id,
                "chapter_id": assignment_row.chapter_id,
                "title": assignment_row.chapter_title,
                "waiting": int(assignment_row.waiting or 0),
                "oldest": assignment_row.oldest,
                "max_score": assignment_row.max_score,
            }
        )

    if display_locale:
        _localize_titles(db, groups, display_locale)

    return _oldest_first(groups)


#: How much of the run one request carries. A week's marking is tens of
#: pieces; a term left unmarked can be thousands, and every one carries its
#: essay. The rest is counted, not sent, and the next load picks it up.
RUN_LIMIT = 200


def waiting_work(
    db: Session, teacher_id: UUID, *, display_locale: LocaleCode, limit: int = RUN_LIMIT
) -> dict[str, Any]:
    """Every piece of work waiting on this teacher, one by one, in marking order.

    The run a teacher sits down to on a phone: open the first, mark it,
    «Дальше», and the next one is already there — across every course they
    teach. Built on the same two queries the dashboard count is, so the number
    on the button and the length of the run are the same number by
    construction; ``total`` is that number even when only the first ``limit``
    pieces are sent.

    Order: the item that has waited longest first, and inside one item the
    oldest answer first — thirty answers to the same prompt in a row, the
    standard loaded once. The groups are chosen first from the cheap
    aggregate, so only the pieces that will be sent are ever read.
    """
    groups = waiting_groups(db, teacher_id)
    total = sum(g["waiting"] for g in groups)
    chosen: list[dict[str, Any]] = []
    taken = 0
    for group in groups:
        if taken >= limit:
            break
        chosen.append(group)
        taken += group["waiting"]
    place = {(g["kind"], g["item_id"]): i for i, g in enumerate(chosen)}
    question_ids = [uuid.UUID(g["item_id"]) for g in chosen if g["kind"] == "quiz_answer"]
    assignment_ids = [uuid.UUID(g["item_id"]) for g in chosen if g["kind"] == "assignment"]

    items: list[dict[str, Any]] = []
    if question_ids:
        answer_rows = (
            waiting_answers(db, teacher_id)
            .with_entities(
                QuizAnswer.id,
                QuizAnswer.text_answer,
                QuizQuestion.id.label("question_id"),
                QuizQuestion.points,
                QuizAttempt.completed_at,
                User.full_name,
                User.email,
                User.preferred_locale,
                Chapter.id.label("chapter_id"),
                Chapter.title.label("chapter_title"),
                Chapter.course_id,
            )
            .filter(QuizQuestion.id.in_(question_ids))
            .all()
        )
        module_due = _module_due_dates(db, sorted({row.chapter_id for row in answer_rows}))
        for row in answer_rows:
            items.append(
                {
                    "kind": "quiz_answer",
                    "id": str(row.id),
                    "item_id": str(row.question_id),
                    "course_id": row.course_id,
                    "chapter_id": row.chapter_id,
                    "title": row.chapter_title,
                    "prompt": None,
                    "student_name": row.full_name or row.email,
                    "student_locale": normalize_locale(row.preferred_locale),
                    "submitted_at": row.completed_at,
                    "content": row.text_answer,
                    "max_points": int(row.points),
                    "is_late": is_late(row.completed_at, module_due.get(row.chapter_id)),
                }
            )

    if assignment_ids:
        submission_rows = (
            waiting_submissions(db, teacher_id)
            .with_entities(
                AssignmentSubmission,
                User.full_name,
                User.email,
                User.preferred_locale,
                Assignment.max_score,
                Assignment.due_date,
                Chapter.id.label("chapter_id"),
                Chapter.title.label("chapter_title"),
                Chapter.course_id,
            )
            .filter(Assignment.id.in_(assignment_ids))
            .all()
        )
        first = _first_handed_in(db, [row[0].assignment_id for row in submission_rows])
        for (
            submission,
            full_name,
            email,
            locale,
            max_score,
            due_date,
            chapter_id,
            chapter_title,
            course_id,
        ) in submission_rows:
            handed_in = first.get((submission.assignment_id, submission.student_id), submission.submitted_at)
            items.append(
                {
                    "kind": "assignment",
                    "id": str(submission.id),
                    "item_id": str(submission.assignment_id),
                    "course_id": course_id,
                    "chapter_id": chapter_id,
                    "title": chapter_title,
                    "prompt": None,
                    "student_name": full_name or email,
                    "student_locale": normalize_locale(locale),
                    "submitted_at": submission.submitted_at,
                    "content": submission.content,
                    "file_url": submission.file_url,
                    "file_bucket": submission.file_bucket,
                    "file_path": submission.file_path,
                    "file_name": submission.file_name,
                    "max_points": max_score,
                    "is_late": is_late(handed_in, due_date),
                }
            )

    items.sort(
        key=lambda i: (
            place[(i["kind"], i["item_id"])],
            i["submitted_at"] is None,
            i["submitted_at"] or 0,
            i["id"],
        )
    )
    items = items[:limit]
    if items:
        from app.services.translation.resolve_for_display import fetch_course_titles_by_id

        _localize_titles(db, items, display_locale)
        _attach_item_texts(db, items, display_locale)
        titles = fetch_course_titles_by_id(
            db, sorted({i["course_id"] for i in items}), display_locale=display_locale, fallback="source_then_any"
        )
        for item in items:
            item["course_title"] = titles.get(item["course_id"]) or ""
    return {"items": items, "total": total}


def _module_due_dates(db: Session, chapter_ids: list[str]) -> dict[str, Any]:
    """Each chapter's module deadline, in one query — the one a quiz is read
    against (see ``late_work.module_due_date_for_chapter``)."""
    if not chapter_ids:
        return {}
    rows = (
        db.query(Chapter.id, Module.due_date)
        .join(Module, Module.id == Chapter.module_id)
        .filter(Chapter.id.in_(chapter_ids), Module.deleted_at.is_(None))
        .all()
    )
    return {chapter_id: due for chapter_id, due in rows}


def _first_handed_in(db: Session, assignment_ids: list) -> dict[tuple, Any]:
    """When each student first handed each assignment in, in one query — late
    is a fact about the first hand-in (see ``late_work.first_handed_in``)."""
    if not assignment_ids:
        return {}
    rows = (
        db.query(
            AssignmentSubmission.assignment_id,
            AssignmentSubmission.student_id,
            sqlfunc.min(AssignmentSubmission.submitted_at),
        )
        .filter(AssignmentSubmission.assignment_id.in_(set(assignment_ids)))
        .group_by(AssignmentSubmission.assignment_id, AssignmentSubmission.student_id)
        .all()
    )
    return {(a, s): when for a, s, when in rows if when is not None}


def _attach_item_texts(db: Session, items: list[dict[str, Any]], display_locale: str) -> None:
    """What was asked, in the teacher's language.

    For an open answer, the question; for an assignment, its own title and
    instructions — a chapter title says where the work sits, not what the
    student was asked to do, and work read without the ask cannot be judged.
    Falls back to the author's words, never to nothing.
    """
    from app.services.content_versions.read import fetch_cv_entity_texts_with_fallback

    course_ids = sorted({i["course_id"] for i in items})
    source_of = {
        row.id: row.source_locale for row in db.query(Course.id, Course.source_locale).filter(Course.id.in_(course_ids))
    }
    wanted: dict[tuple[str, str], set[str]] = {}
    for item in items:
        entity = "quiz_question" if item["kind"] == "quiz_answer" else "assignment"
        wanted.setdefault((entity, normalize_locale(source_of.get(item["course_id"]))), set()).add(item["item_id"])
    texts: dict[tuple[str, str], str] = {}
    for (entity, source_locale), entity_ids in wanted.items():
        found = fetch_cv_entity_texts_with_fallback(
            db,
            entity_type=entity,
            entity_ids=sorted(entity_ids),
            fields=["question_text"] if entity == "quiz_question" else ["title", "description"],
            display_locale=display_locale,
            source_locale=source_locale,
            fallback="source_then_any",
        )
        texts.update({key: text for key, text in found.items() if text})
    for item in items:
        if item["kind"] == "quiz_answer":
            item["prompt"] = texts.get((item["item_id"], "question_text"))
        else:
            item["title"] = texts.get((item["item_id"], "title")) or item["title"]
            item["prompt"] = texts.get((item["item_id"], "description"))


def _localize_titles(db: Session, groups: list[dict[str, Any]], display_locale: str) -> None:
    """Lesson names in the teacher's language, like the gradebook beside it.

    ``Chapter.title`` is the author's words; in an English interface the
    queue read Russian while the progress and analytics pages read English
    (2026-09-29). Falls back to the author's words, never to nothing: the
    teacher has to know what they are marking.
    """
    from app.services.content_versions.read import fetch_cv_entity_texts_with_fallback

    course_ids = sorted({g["course_id"] for g in groups})
    if not course_ids:
        return
    source_of: dict[str, str | None] = {
        row.id: row.source_locale for row in db.query(Course.id, Course.source_locale).filter(Course.id.in_(course_ids))
    }
    by_source: dict[str, set[str]] = {}
    for g in groups:
        by_source.setdefault(normalize_locale(source_of.get(g["course_id"])), set()).add(g["chapter_id"])
    names: dict[str, str] = {}
    for source_locale, chapter_ids in by_source.items():
        texts = fetch_cv_entity_texts_with_fallback(
            db,
            entity_type="chapter",
            entity_ids=sorted(chapter_ids),
            fields=["title"],
            display_locale=display_locale,
            source_locale=source_locale,
            fallback="source_then_any",
        )
        names.update({entity_id: text for (entity_id, _field), text in texts.items() if text})
    for g in groups:
        g["title"] = names.get(g["chapter_id"], g["title"])


def assignment_work(db: Session, teacher_id: UUID, assignment_id: UUID) -> list[dict[str, Any]]:
    """The submissions waiting on one assignment, oldest first.

    Ownership is enforced by the caller; the teacher filter here is defence in
    depth rather than the only lock — a queue route that leaks is a route that
    leaks somebody's essay.
    """
    rows = (
        waiting_submissions(db, teacher_id)
        .with_entities(AssignmentSubmission, User.full_name, User.email, Assignment.due_date)
        .filter(Assignment.id == assignment_id)
        .order_by(AssignmentSubmission.submitted_at.asc(), AssignmentSubmission.id.asc())
        .all()
    )
    first = first_handed_in(db, assignment_id, list({submission.student_id for submission, *_ in rows}))
    return [
        {
            "submission_id": str(submission.id),
            "student_id": str(submission.student_id),
            "student_name": full_name or email,
            "submitted_at": submission.submitted_at,
            "content": submission.content,
            "file_url": submission.file_url,
            "file_bucket": submission.file_bucket,
            "file_path": submission.file_path,
            "file_name": submission.file_name,
            # The queue is where the teacher meets the work; it is the one
            # place «handed in late» must not be a click away (2026-10-03).
            "is_late": is_late(first.get(str(submission.student_id), submission.submitted_at), due_date),
        }
        for submission, full_name, email, due_date in rows
    ]
