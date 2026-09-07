"""A chapter outside any module still counts.

Step 2 of the chapter→course move (the first is
``test_a_chapter_belongs_to_its_course``): every course-level read that used
to walk ``Chapter → Module → Course`` now reads ``Chapter.course_id``. The
reads in question are the ones where a lost chapter does not raise — it
*disappears*: the percentage is a fraction of fewer chapters, the final grade
is over fewer items, the certificate is issued for part of a course, an essay
never reaches the teacher's queue, a binned course keeps a live chapter, a
clone leaves one behind, a purge leaves its translations orphaned.

Two halves:

* **The module walk and the direct read agree.** Every chapter in production
  has a module, so on a course built the old way the two ways of gathering
  chapters must return the same set. Each denominator is compared against the
  exact predicate it replaced, spelled out here as ``_module_walk``.
* **A chapter without a module is counted.** The model's ``module_id`` is
  nullable ahead of the database (step 3 lifts the NOT NULL) so the tests can
  build the course the change is for and prove the chapter is in every
  denominator, in the queue, in the cascades and in the clone.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from app.api.v1.grades import _quizzes_off_the_course_line
from app.constants import GRADABLE_CHAPTER_TYPES
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.schemas.course import ChapterUpdate
from app.services import zachet
from app.services.calendar_service import build_calendar_events
from app.services.content_versions import record_human_version
from app.services.course_service import (
    clone_course,
    delete_chapter,
    delete_course,
    get_course,
    permanently_delete_course,
    reading_progress_by_course,
    restore_course,
    resync_course_progress,
    sync_enrollment_progress,
    update_chapter,
)
from app.services.gradable_items import course_items
from app.services.grade_calculator import _get_course_chapter_ids
from app.services.grade_exemption_service import chapter_for_item
from app.services.grading_queue import assignment_work, pending_by_course, waiting_groups
from app.services.student_progress_service import _latest_activity_by_user, _load_course_structure
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

pytestmark = pytest.mark.usefixtures("teacher", "student")

COURSE = "c-main"
OTHER = "c-other"
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _chapter(
    db: Session,
    *,
    chapter_id: str,
    course_id: str,
    module_id: str | None,
    chapter_type: str = "reading",
    order_index: int = 0,
    deleted_at: datetime | None = None,
) -> Chapter:
    chapter = Chapter(
        id=chapter_id,
        course_id=course_id,
        module_id=module_id,
        title=chapter_id,
        chapter_type=chapter_type,
        order_index=order_index,
        deleted_at=deleted_at,
    )
    db.add(chapter)
    db.flush()
    return chapter


def _quiz(db: Session, chapter_id: str, *, passing_score: int = 70) -> Quiz:
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter_id, passing_score=passing_score)
    db.add(quiz)
    db.flush()
    return quiz


def _assignment(db: Session, chapter_id: str, *, due_date: datetime | None = None) -> Assignment:
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter_id, max_score=100, due_date=due_date)
    db.add(assignment)
    db.flush()
    return assignment


def _scene(db: Session, *, loose: bool) -> dict[str, Any]:
    """One course built the old way, with a second course beside it as noise.

    ``c-main``: module 1 holds a quiz and a lesson, module 2 an assignment and a
    second quiz; a binned quiz chapter (with a quiz and an assignment in it) sits
    under module 1 and a binned lesson under module 2. With ``loose`` the
    course also holds — under no module — a quiz, an assignment and a lesson.
    ``c-other`` is the same teacher's other course with one quiz, so a read
    that forgets to filter by course shows up as a wrong number here.
    """
    db.add(Course(id=COURSE, status="published", created_by=TEACHER_ID, source_locale="ru"))
    db.add(Course(id=OTHER, status="published", created_by=TEACHER_ID, source_locale="ru"))
    db.add(Module(id="m1", course_id=COURSE, order_index=0, title="Module 1"))
    db.add(Module(id="m2", course_id=COURSE, order_index=1, title="Module 2"))
    db.add(Module(id="m-other", course_id=OTHER, order_index=0, title="Other module"))
    db.flush()

    s: dict[str, Any] = {}
    _chapter(db, chapter_id="q1", course_id=COURSE, module_id="m1", chapter_type="quiz", order_index=0)
    _chapter(db, chapter_id="r1", course_id=COURSE, module_id="m1", order_index=1)
    _chapter(db, chapter_id="a1", course_id=COURSE, module_id="m2", chapter_type="assignment", order_index=0)
    _chapter(db, chapter_id="q2", course_id=COURSE, module_id="m2", chapter_type="quiz", order_index=1)
    _chapter(
        db,
        chapter_id="gone",
        course_id=COURSE,
        module_id="m1",
        chapter_type="quiz",
        order_index=9,
        deleted_at=NOW - timedelta(days=30),
    )
    _chapter(
        db,
        chapter_id="gone-r",
        course_id=COURSE,
        module_id="m2",
        order_index=9,
        deleted_at=NOW - timedelta(days=30),
    )
    _chapter(db, chapter_id="o-q", course_id=OTHER, module_id="m-other", chapter_type="quiz")
    s["quiz_q1"] = _quiz(db, "q1")
    s["quiz_q2"] = _quiz(db, "q2", passing_score=60)
    s["quiz_gone"] = _quiz(db, "gone", passing_score=10)
    s["quiz_other"] = _quiz(db, "o-q", passing_score=55)
    s["assignment_a1"] = _assignment(db, "a1", due_date=NOW + timedelta(days=7))
    s["assignment_gone"] = _assignment(db, "gone", due_date=NOW + timedelta(days=3))
    s["modular"] = {"q1", "r1", "a1", "q2"}
    s["modular_gradable"] = {"q1", "a1", "q2"}

    if loose:
        _chapter(db, chapter_id="loose-q", course_id=COURSE, module_id=None, chapter_type="quiz", order_index=5)
        _chapter(db, chapter_id="loose-a", course_id=COURSE, module_id=None, chapter_type="assignment", order_index=6)
        _chapter(db, chapter_id="loose-r", course_id=COURSE, module_id=None, order_index=7)
        s["quiz_loose"] = _quiz(db, "loose-q", passing_score=50)
        s["assignment_loose"] = _assignment(db, "loose-a", due_date=NOW + timedelta(days=9))

    db.add(Enrollment(id="enr-main", user_id=STUDENT_ID, course_id=COURSE, progress=0))
    db.commit()
    return s


def _complete(db: Session, chapter_id: str) -> None:
    db.add(ChapterProgress(id=uuid.uuid4(), user_id=STUDENT_ID, chapter_id=chapter_id, completed=True))
    db.commit()


def _unread_essay(db: Session, quiz: Quiz, *, completed_at: datetime = NOW) -> None:
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=10, order_index=0)
    db.add(question)
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=0,
        max_score=10,
        passed=False,
        completed_at=completed_at,
    )
    db.add(attempt)
    db.flush()
    db.add(
        QuizAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            question_id=question.id,
            text_answer="Ответ",
            points_earned=0,
            graded_at=None,
        )
    )
    db.commit()


def _unmarked_submission(db: Session, assignment: Assignment, *, submitted_at: datetime = NOW) -> AssignmentSubmission:
    submission = AssignmentSubmission(
        id=uuid.uuid4(),
        assignment_id=assignment.id,
        student_id=STUDENT_ID,
        status="submitted",
        grade=None,
        submitted_at=submitted_at,
    )
    db.add(submission)
    db.commit()
    return submission


def _progress(db: Session) -> int:
    row = db.query(Enrollment).filter(Enrollment.id == "enr-main").one()
    db.refresh(row)
    return row.progress


# ---------------------------------------------------------------------------
# The predicate every read used to have
# ---------------------------------------------------------------------------


def _module_walk(db: Session, course_id: str, *, gradable_only: bool = False) -> set[str]:
    """Live chapters of a course, gathered the way every read gathered them
    before this step: through the module, live modules only."""
    query = (
        db.query(Chapter.id)
        .join(Module, Module.id == Chapter.module_id)
        .filter(
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
    )
    if gradable_only:
        query = query.filter(Chapter.chapter_type.in_(GRADABLE_CHAPTER_TYPES))
    return {row[0] for row in query}


def _module_walk_in_order(db: Session, course_id: str) -> list[str]:
    """The board's old ordering: ``(Module.order_index, Chapter.order_index)``."""
    return [
        row[0]
        for row in db.query(Chapter.id)
        .join(Module, Module.id == Chapter.module_id)
        .filter(Module.course_id == course_id, Module.deleted_at.is_(None), Chapter.deleted_at.is_(None))
        .order_by(Module.order_index, Chapter.order_index)
    ]


# ===========================================================================
# I. On a course built the old way, the module walk and the direct read agree
# ===========================================================================


def test_the_scene_has_something_for_the_walk_to_miss(db: Session):
    s = _scene(db, loose=False)
    walk = _module_walk(db, COURSE)
    assert walk == s["modular"]
    # The binned chapter and the other course are outside the walk, so a read
    # that stopped filtering on either would disagree with it below.
    assert {"gone", "gone-r", "o-q"}.isdisjoint(walk)


def test_the_grade_denominator_is_the_module_walk(db: Session):
    _scene(db, loose=False)
    assert set(_get_course_chapter_ids(db, COURSE)) == _module_walk(db, COURSE, gradable_only=True)


def test_the_gradable_items_are_the_module_walk(db: Session):
    s = _scene(db, loose=False)
    quizzes, assignments = course_items(db, COURSE)
    assert {row.chapter_id for row in quizzes} | {row.chapter_id for row in assignments} == _module_walk(
        db, COURSE, gradable_only=True
    )
    assert {row[0] for row in quizzes} == {s["quiz_q1"].id, s["quiz_q2"].id}


def test_the_zachet_items_are_the_module_walk(db: Session):
    _scene(db, loose=False)
    walk = _module_walk(db, COURSE)
    expected_quizzes = {q.id for q in db.query(Quiz).filter(Quiz.chapter_id.in_(walk))}
    expected_assignments = {a.id for a in db.query(Assignment).filter(Assignment.chapter_id.in_(walk))}
    assert {row[0] for row in zachet.course_quiz_rows(db, COURSE)} == expected_quizzes
    assert {row.id for row in zachet.assignments_in_course(db, COURSE)} == expected_assignments


def test_the_exemption_scope_is_the_module_walk(db: Session):
    s = _scene(db, loose=False)
    walk = _module_walk(db, COURSE)
    for quiz in (s["quiz_q1"], s["quiz_q2"], s["quiz_gone"], s["quiz_other"]):
        old_way = quiz.chapter_id if quiz.chapter_id in walk else None
        assert chapter_for_item(db, item_type="quiz", item_id=quiz.id, course_id=COURSE) == old_way
    assert chapter_for_item(db, item_type="assignment", item_id=s["assignment_a1"].id, course_id=COURSE) == "a1"


def test_the_percentage_is_a_fraction_of_the_module_walk(db: Session):
    _scene(db, loose=False)
    _complete(db, "q1")
    _complete(db, "gone")  # a pass on a binned chapter counts for nothing
    gradable = _module_walk(db, COURSE, gradable_only=True)
    passed = {"q1", "gone"} & gradable
    old_way = round(len(passed) / len(gradable) * 100)

    enrollment = sync_enrollment_progress(db, STUDENT_ID, COURSE)
    assert enrollment is not None and enrollment.progress == old_way == 33

    enrollment.progress = 100
    db.commit()
    assert resync_course_progress(db, COURSE) == 1
    assert _progress(db) == old_way


def test_the_reading_count_is_the_module_walk(db: Session):
    _scene(db, loose=False)
    _complete(db, "r1")
    walk = _module_walk(db, COURSE)
    to_read = {c for c in walk if c not in _module_walk(db, COURSE, gradable_only=True)}
    assert reading_progress_by_course(db, STUDENT_ID, [COURSE]) == {COURSE: (len({"r1"} & to_read), len(to_read))}


def test_the_queue_is_the_module_walk(db: Session):
    s = _scene(db, loose=False)
    _unread_essay(db, s["quiz_q1"])
    _unread_essay(db, s["quiz_gone"])  # binned: not waiting on anybody
    _unread_essay(db, s["quiz_other"])
    submission = _unmarked_submission(db, s["assignment_a1"])
    _unmarked_submission(db, s["assignment_gone"])  # binned as well
    walk = _module_walk(db, COURSE)

    unread_in_walk = (
        db.query(QuizAnswer)
        .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .filter(Quiz.chapter_id.in_(walk), QuizAnswer.graded_at.is_(None))
        .count()
    )
    submitted_in_walk = (
        db.query(AssignmentSubmission)
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .filter(Assignment.chapter_id.in_(walk), AssignmentSubmission.grade.is_(None))
        .count()
    )
    assert pending_by_course(db, TEACHER_ID) == {COURSE: unread_in_walk + submitted_in_walk, OTHER: 1}
    assert pending_by_course(db, TEACHER_ID)[COURSE] == 2

    groups = waiting_groups(db, TEACHER_ID)
    assert {g["chapter_id"] for g in groups if g["course_id"] == COURSE} == {"q1", "a1"} == walk & {"q1", "a1", "gone"}
    assert [w["submission_id"] for w in assignment_work(db, TEACHER_ID, s["assignment_a1"].id)] == [str(submission.id)]


def test_the_threshold_audit_is_the_module_walk(db: Session):
    _scene(db, loose=False)
    walk = _module_walk(db, COURSE)
    old_way = {str(q.id) for q in db.query(Quiz).filter(Quiz.chapter_id.in_(walk), Quiz.passing_score != 70)}
    reported = {row["quiz_id"] for row in _quizzes_off_the_course_line(db, COURSE, Decimal("70"))}
    assert reported == old_way
    assert len(reported) == 1  # q2 at 60; the binned one at 10 and the other course's at 55 are not the course's


def test_my_progress_is_the_module_walk(db: Session, student_client: TestClient):
    _scene(db, loose=False)
    _complete(db, "q1")
    _complete(db, "gone")
    walk = _module_walk(db, COURSE)

    body = student_client.get(f"/api/v1/progress/course/{COURSE}/my-progress").json()

    assert set(body) == {"q1", "gone"} & walk == {"q1"}


def test_the_board_walks_the_course_in_the_old_order(db: Session):
    _scene(db, loose=False)
    chapters, module_map, titles = _load_course_structure(db, COURSE)
    assert [c.id for c in chapters] == _module_walk_in_order(db, COURSE) == ["q1", "r1", "a1", "q2"]
    assert set(titles) == _module_walk(db, COURSE)
    assert set(module_map) == {"m1", "m2"}


def test_last_activity_is_the_module_walk(db: Session):
    s = _scene(db, loose=False)
    _unread_essay(db, s["quiz_q1"], completed_at=NOW - timedelta(days=2))
    _unread_essay(db, s["quiz_gone"], completed_at=NOW)  # later, but binned
    _unmarked_submission(db, s["assignment_a1"], submitted_at=NOW - timedelta(days=1))
    _unmarked_submission(db, s["assignment_gone"], submitted_at=NOW)  # later, but binned

    quiz_seen, submission_seen = _latest_activity_by_user(db, COURSE)

    assert quiz_seen[str(STUDENT_ID)].replace(tzinfo=UTC) == NOW - timedelta(days=2)
    assert submission_seen[str(STUDENT_ID)].replace(tzinfo=UTC) == NOW - timedelta(days=1)


def test_the_calendar_shows_the_module_walks_deadlines(db: Session, student: User):
    s = _scene(db, loose=False)
    walk = _module_walk(db, COURSE)
    old_way = {
        f"assignment-{a.id}"
        for a in db.query(Assignment).filter(Assignment.chapter_id.in_(walk), Assignment.due_date.isnot(None))
    }

    events = build_calendar_events(db, user=student, display_locale="ru")

    deadlines = {e.id for e in events if e.source == "assignment_deadline"}
    assert deadlines == old_way == {f"assignment-{s['assignment_a1'].id}"}
    assert f"assignment-{s['assignment_gone'].id}" not in deadlines


def test_the_bin_takes_the_module_walk_and_gives_it_back(db: Session):
    _scene(db, loose=False)
    walk = _module_walk(db, COURSE)
    course = db.get(Course, COURSE)
    assert course is not None

    delete_course(db, course)

    tombstone = course.deleted_at
    binned = {c.id for c in db.query(Chapter).filter(Chapter.deleted_at == tombstone)}
    assert binned == walk
    assert db.get(Chapter, "o-q").deleted_at is None  # type: ignore[union-attr]

    restore_course(db, course)

    assert {c.id for c in db.query(Chapter).filter(Chapter.deleted_at.is_(None))} == walk | {"o-q"}
    assert db.get(Chapter, "gone").deleted_at is not None  # type: ignore[union-attr]


# ===========================================================================
# II. A chapter without a module is counted
# ===========================================================================


def test_a_loose_chapter_is_in_the_grade_denominator(db: Session):
    s = _scene(db, loose=True)
    assert set(_get_course_chapter_ids(db, COURSE)) == s["modular_gradable"] | {"loose-q", "loose-a"}


def test_a_loose_quiz_dilutes_the_percentage(db: Session):
    _scene(db, loose=True)
    for chapter_id in ("q1", "a1", "q2"):
        _complete(db, chapter_id)

    enrollment = sync_enrollment_progress(db, STUDENT_ID, COURSE)

    # Three of five, not three of three: the two loose chapters are owed.
    assert enrollment is not None and enrollment.progress == 60
    enrollment.progress = 100
    db.commit()
    resync_course_progress(db, COURSE)
    assert _progress(db) == 60

    # And a pass on a loose chapter counts, in both recomputations: the
    # numerator reaches it as well as the denominator.
    _complete(db, "loose-q")
    assert resync_course_progress(db, COURSE) == 1
    assert _progress(db) == 80
    enrollment = sync_enrollment_progress(db, STUDENT_ID, COURSE)
    assert enrollment is not None and enrollment.progress == 80


def test_a_loose_lesson_is_something_to_read(db: Session):
    _scene(db, loose=True)
    _complete(db, "loose-r")
    assert reading_progress_by_course(db, STUDENT_ID, [COURSE]) == {COURSE: (1, 2)}


def test_a_loose_chapters_work_is_owed_for_zachet(db: Session):
    s = _scene(db, loose=True)
    quizzes, assignments = course_items(db, COURSE)
    assert s["quiz_loose"].id in {row[0] for row in quizzes}
    assert s["assignment_loose"].id in {row[0] for row in assignments}
    assert str(s["quiz_loose"].id) in zachet.unpassed_quizzes(db, student_id=STUDENT_ID, course_id=COURSE)
    assert str(s["assignment_loose"].id) in zachet.unaccepted_assignments(db, student_id=STUDENT_ID, course_id=COURSE)


def test_an_exemption_reaches_a_loose_chapter(db: Session):
    s = _scene(db, loose=True)
    assert chapter_for_item(db, item_type="quiz", item_id=s["quiz_loose"].id, course_id=COURSE) == "loose-q"
    assert chapter_for_item(db, item_type="assignment", item_id=s["assignment_loose"].id, course_id=COURSE) == "loose-a"


def test_a_loose_essay_waits_in_the_queue(db: Session):
    s = _scene(db, loose=True)
    _unread_essay(db, s["quiz_loose"])
    submission = _unmarked_submission(db, s["assignment_loose"])

    assert pending_by_course(db, TEACHER_ID) == {COURSE: 2}
    assert {g["chapter_id"] for g in waiting_groups(db, TEACHER_ID)} == {"loose-q", "loose-a"}
    assert [w["submission_id"] for w in assignment_work(db, TEACHER_ID, s["assignment_loose"].id)] == [
        str(submission.id)
    ]


def test_the_threshold_audit_sees_a_loose_quiz(db: Session):
    s = _scene(db, loose=True)
    reported = {row["quiz_id"] for row in _quizzes_off_the_course_line(db, COURSE, Decimal("70"))}
    assert reported == {str(s["quiz_q2"].id), str(s["quiz_loose"].id)}


def test_my_progress_lists_a_loose_chapter(db: Session, student_client: TestClient):
    _scene(db, loose=True)
    _complete(db, "loose-q")
    assert student_client.get(f"/api/v1/progress/course/{COURSE}/my-progress").json() == ["loose-q"]


def test_the_board_lists_a_loose_chapter(db: Session):
    s = _scene(db, loose=True)
    _unread_essay(db, s["quiz_loose"], completed_at=NOW)
    _unmarked_submission(db, s["assignment_loose"], submitted_at=NOW)

    chapters, _modules, _titles = _load_course_structure(db, COURSE)
    quiz_seen, submission_seen = _latest_activity_by_user(db, COURSE)

    # Modular chapters keep their order; the loose ones are in the list —
    # ahead of the modules for now, a placement step 3 revisits.
    assert [c.id for c in chapters] == ["loose-q", "loose-a", "loose-r", "q1", "r1", "a1", "q2"]
    assert quiz_seen[str(STUDENT_ID)].replace(tzinfo=UTC) == NOW
    assert submission_seen[str(STUDENT_ID)].replace(tzinfo=UTC) == NOW


def test_the_calendar_shows_a_loose_deadline(db: Session, student: User):
    s = _scene(db, loose=True)
    events = build_calendar_events(db, user=student, display_locale="ru")
    assert f"assignment-{s['assignment_loose'].id}" in {e.id for e in events if e.source == "assignment_deadline"}


def test_deleting_a_loose_quiz_moves_the_denominator(db: Session):
    _scene(db, loose=True)
    for chapter_id in ("q1", "a1", "q2"):
        _complete(db, chapter_id)
    sync_enrollment_progress(db, STUDENT_ID, COURSE)
    assert _progress(db) == 60

    loose = db.get(Chapter, "loose-q")
    assert loose is not None
    delete_chapter(db, loose)

    # Three of four now. The resync found the course through the chapter
    # itself; there is no module to ask.
    assert _progress(db) == 75


def test_renaming_a_loose_chapter_finds_its_courses_language(db: Session):
    _scene(db, loose=True)
    loose = db.get(Chapter, "loose-r")
    assert loose is not None

    update_chapter(db, loose, ChapterUpdate(title="Урок"))

    row = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "chapter",
            ContentVersion.entity_id == "loose-r",
            ContentVersion.field == "title",
            ContentVersion.superseded_by.is_(None),
        )
        .one()
    )
    # The title is short enough that detection alone cannot place it; the
    # course's language is the fallback, reached without a module.
    assert (row.text, row.locale) == ("Урок", "ru")


def test_the_bin_takes_a_loose_chapter_and_gives_it_back(db: Session):
    _scene(db, loose=True)
    course = db.get(Course, COURSE)
    assert course is not None

    delete_course(db, course)

    loose_ids = ["loose-q", "loose-a", "loose-r"]
    assert all(db.get(Chapter, cid).deleted_at == course.deleted_at for cid in loose_ids)  # type: ignore[union-attr]

    restore_course(db, course)

    assert all(db.get(Chapter, cid).deleted_at is None for cid in loose_ids)  # type: ignore[union-attr]


# --- purge -------------------------------------------------------------------


def _forget_course_tree(db: Session) -> None:
    """Detach the tree so the purge reloads it through the bin's eager loader,
    the way a request does (see ``test_admin_bulk_trash_and_csv``)."""
    for obj in list(db.identity_map.values()):
        if isinstance(obj, (Course, Module, Chapter)):
            db.expunge(obj)


@contextmanager
def _without_sqlite_fk_cascade(db: Session):
    """Postgres cascades the entity rows itself; SQLite would fail the delete
    on a foreign key before the sweep under test gets to run."""
    db.execute(text("PRAGMA foreign_keys = OFF"))
    try:
        yield
    finally:
        db.execute(text("PRAGMA foreign_keys = ON"))


def test_purging_a_course_leaves_no_orphan_behind_a_loose_chapter(db: Session):
    """``content_versions`` has no foreign key to anything; the sweep in
    ``permanently_delete_course`` is what removes a chapter's translations.
    Gathering chapters through the modules would skip a loose one — and its
    block and quiz — leaving exactly the orphans production had 787 of."""
    from tests._cv_helpers import make_chapter_block_with_content, make_quiz_with_text

    _scene(db, loose=True)
    record_human_version(db, entity_type="chapter", entity_id="loose-q", field="title", locale="ru", text="Тест")
    block = make_chapter_block_with_content(db, chapter_id="loose-q", content="<p>Вопросы</p>")
    quiz = make_quiz_with_text(db, chapter_id="loose-q", title="Итоговый тест")
    db.commit()
    ids = {
        "chapter": ["loose-q"],
        "chapter_block": [str(block.id)],
        "quiz": [str(quiz.id)],
    }

    def _counts() -> dict[str, int]:
        return {
            kind: db.query(ContentVersion)
            .filter(ContentVersion.entity_type == kind, ContentVersion.entity_id.in_(values))
            .count()
            for kind, values in ids.items()
        }

    assert _counts() == {"chapter": 1, "chapter_block": 1, "quiz": 1}

    course = db.get(Course, COURSE)
    assert course is not None
    delete_course(db, course)
    _forget_course_tree(db)
    reloaded = get_course(db, COURSE, include_deleted=True)
    assert reloaded is not None
    with _without_sqlite_fk_cascade(db):
        permanently_delete_course(db, reloaded)

    assert _counts() == {"chapter": 0, "chapter_block": 0, "quiz": 0}


# --- clone -------------------------------------------------------------------


@pytest.mark.usefixtures("chapters_name_their_own_course")
def test_a_clone_copies_a_loose_chapter(db: Session):
    from tests._cv_helpers import make_chapter_block_with_content

    s = _scene(db, loose=True)
    make_chapter_block_with_content(db, chapter_id="loose-q", content="<p>Вопросы</p>")
    db.commit()

    clone = clone_course(db, COURSE, TEACHER_ID)

    assert clone is not None
    by_title = {c.title: c for c in clone.chapters}
    assert set(by_title) == s["modular"] | {"loose-q", "loose-a", "loose-r"}
    # Modular chapters keep a module — the copied one, under the copied course.
    assert {by_title[t].module.course_id for t in s["modular"]} == {clone.id}
    # Loose chapters stay loose, and belong to the copy.
    loose_copy = by_title["loose-q"]
    assert loose_copy.module_id is None and loose_copy.course_id == clone.id
    assert db.query(Quiz).filter(Quiz.chapter_id == loose_copy.id).count() == 1
    assert db.query(Assignment).filter(Assignment.chapter_id == by_title["loose-a"].id).count() == 1
    from app.models.chapter_block import ChapterBlock

    assert db.query(ChapterBlock).filter(ChapterBlock.chapter_id == loose_copy.id).count() == 1
    # Nothing of the original moved.
    assert db.get(Chapter, "loose-q").course_id == COURSE  # type: ignore[union-attr]
