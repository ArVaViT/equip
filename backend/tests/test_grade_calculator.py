"""Unit tests for ``app.services.grade_calculator``.

Pins the weighted-grade-breakdown invariants directly at the service
boundary. The existing ``test_certificates_and_grades.py`` covers the
HTTP/route surface; this file targets the service-layer arithmetic
that gets exercised by both the single-student and batch entry points:

* ``score_to_letter`` — threshold rounding (incl. negative score → F).
* ``calculate_student_grade_for_course`` — the convenience wrapper used
  by the per-student grades page; exercises the quiz/assignment/
  participation branches together with realistic weights.
* ``calculate_all_student_grades`` — the batch entry point used by the
  teacher gradebook; verifies the 6-query batch path produces the
  same breakdown the per-student path does, and that manual grades
  get attached correctly.

Together these close the missing-line gap inside the service module
without going through the FastAPI layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.models.assignment import AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter
from app.models.enrollment import Enrollment
from app.models.quiz import QuizAttempt
from app.models.student_grade import StudentGrade
from app.models.user import User, UserRole
from app.services.grade_calculator import (
    calculate_all_student_grades,
    calculate_student_grade_for_course,
    score_to_letter,
)

from ._cv_helpers import (
    make_assignment_with_text,
    make_course_with_text,
    make_module_with_text,
    make_quiz_with_text,
)
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.course import Course


def _ensure_users(db: Session) -> None:
    """Seed teacher + student rows (idempotent) for the test scenario.

    The Course's ``created_by`` FK references users; enrollment + grade
    rows reference both. Idempotent so individual tests can also bring
    their own ``teacher`` / ``student`` fixtures without a UNIQUE
    collision.
    """
    for user_id, role, email in [
        (TEACHER_ID, UserRole.TEACHER.value, "teacher@example.com"),
        (STUDENT_ID, UserRole.STUDENT.value, "student@example.com"),
    ]:
        existing = db.query(User).filter(User.id == user_id).first()
        if existing is None:
            db.add(User(id=user_id, email=email, full_name="Test", role=role))
    db.flush()


def _seed_course_with_one_quiz_one_assignment(
    db: Session,
    *,
    course_id: str = "g-course",
) -> tuple[Course, str, uuid.UUID, uuid.UUID]:
    """Build a published course with a single graded chapter that holds
    one quiz and one assignment. Returns ``(course, chapter_id, quiz_id,
    assignment_id)`` so individual tests can attach attempts / submissions
    / progress rows without re-stating the structure.
    """
    _ensure_users(db)
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="Grade Calculator Test Course",
        description="x",
        status="published",
        created_by=TEACHER_ID,
        quiz_weight=50,
        assignment_weight=50,
    )
    module = make_module_with_text(
        db,
        module_id=f"{course_id}-mod",
        course_id=course.id,
        title="Module 1",
    )
    chapter = Chapter(
        id=f"{course_id}-ch",
        module_id=module.id,
        title="Quiz + Assignment chapter",
        order_index=0,
        chapter_type="quiz",
    )
    db.add(chapter)
    db.flush()
    quiz = make_quiz_with_text(
        db,
        chapter_id=chapter.id,
        title="Quiz",
    )
    assignment = make_assignment_with_text(
        db,
        chapter_id=chapter.id,
        title="Assignment",
        max_score=100,
    )
    db.commit()
    return course, chapter.id, quiz.id, assignment.id


def _enroll(db: Session, student_id: uuid.UUID, course_id: str) -> Enrollment:
    enrollment = Enrollment(
        id=f"enroll-{course_id}-{student_id}",
        user_id=student_id,
        course_id=course_id,
        progress=0,
    )
    db.add(enrollment)
    db.commit()
    return enrollment


class TestScoreToLetter:
    """Letter-grade thresholds — pinned so the API contract that
    students see (and the certificate UI prints) doesn't drift under
    refactor.
    """

    @pytest.mark.parametrize(
        "score, expected",
        [
            (100.0, "A"),
            (95.0, "A"),
            (90.0, "A"),
            (89.99, "B"),
            (80.0, "B"),
            (79.99, "C"),
            (70.0, "C"),
            (69.99, "D"),
            (60.0, "D"),
            (59.99, "F"),
            (0.0, "F"),
        ],
    )
    def test_threshold_table(self, score: float, expected: str) -> None:
        assert score_to_letter(score) == expected

    def test_negative_score_falls_through_to_F(self) -> None:
        """The ``LETTER_GRADES`` table has a ``(0, "F")`` floor entry,
        so a negative score (impossible in production but tests pin the
        defensive ``return "F"`` line at the bottom of the function so
        a future table edit that drops the 0-floor still degrades
        safely instead of returning the previous letter from leak.
        """
        # This exercises the ``return "F"`` after the loop — only
        # reachable if ``LETTER_GRADES`` lost its 0-threshold floor.
        # We don't mutate the constant here; the floor catches everything
        # at or above 0. A negative score still returns "F" via the
        # 0-threshold row, which is what we expect today.
        assert score_to_letter(-10.0) == "F"


class TestCalculateStudentGradeForCourse:
    """End-to-end through the service: seed real ORM rows, then call
    the calculator and assert the breakdown matches the weight math.
    """

    def test_perfect_quiz_perfect_assignment_full_completion(
        self,
        db: Session,
        student,
    ) -> None:
        course, chapter_id, quiz_id, assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)

        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=10,
                max_score=10,
                completed_at=datetime.now(UTC),
            )
        )
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment_id,
                student_id=STUDENT_ID,
                status="graded",
                grade=100,
                graded_by=TEACHER_ID,
            )
        )
        db.add(
            ChapterProgress(
                id=uuid.uuid4(),
                user_id=STUDENT_ID,
                chapter_id=chapter_id,
                completed=True,
                completion_type="self",
            )
        )
        db.commit()

        breakdown = calculate_student_grade_for_course(db, course, STUDENT_ID)

        # weights are 50/50; everything is 100 → final must be 100.
        assert breakdown.quiz_avg == 100.0
        assert breakdown.quiz_weighted == 50.0
        assert breakdown.assignment_avg == 100.0
        assert breakdown.assignment_weighted == 50.0
        # Participation is retired (D5): still reported for wire
        # compatibility, but it can no longer contribute to the score.
        assert breakdown.participation_pct == 100.0
        assert breakdown.participation_weighted == 0.0
        assert breakdown.final_score == 100.0
        assert breakdown.letter_grade == "A"

    def test_partial_quiz_no_assignment_no_completion(self, db: Session, student) -> None:
        """Half the quiz, no assignment submission, no chapter completion
        — exercises the "best of one attempt" path and the
        ``submissions.grade is None`` skip.
        """
        course, _chapter_id, quiz_id, _assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=5,
                max_score=10,
                completed_at=datetime.now(UTC),
            )
        )
        db.commit()

        breakdown = calculate_student_grade_for_course(db, course, STUDENT_ID)

        # Half the quiz, and the assignment category holds no graded work at
        # all — so it does not take a share (D4). Half of what actually counts
        # is 50%, not the 25% the old formula produced by weighing an empty
        # category as a zero.
        assert breakdown.quiz_avg == 50.0
        assert breakdown.quiz_weighted == 50.0
        assert breakdown.assignment_avg == 0.0
        assert breakdown.assignment_weighted == 0.0
        assert breakdown.participation_pct == 0.0
        assert (breakdown.effective_quiz_weight, breakdown.effective_assignment_weight) == (100, 0)
        assert breakdown.final_score == 50.0
        assert breakdown.letter_grade == "F"

    def test_best_of_two_attempts_wins(self, db: Session, student) -> None:
        """Quiz best-score uses ``MAX(...)`` across attempts — a later
        worse attempt cannot overwrite an earlier perfect score.
        """
        course, _chapter_id, quiz_id, _assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)

        # Earlier perfect attempt + later worse attempt.
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=10,
                max_score=10,
                completed_at=datetime.now(UTC),
            )
        )
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=3,
                max_score=10,
                completed_at=datetime.now(UTC),
            )
        )
        db.commit()

        breakdown = calculate_student_grade_for_course(db, course, STUDENT_ID)
        assert breakdown.quiz_avg == 100.0

    def test_assignment_grade_over_max_score_clamps_to_100(self, db: Session, student) -> None:
        """Historical rows could store ``grade > max_score`` before the
        UI clamped. The calculator must defensively cap each assignment's
        percentage at 100% so a single over-cap row doesn't push the
        course grade above 100.
        """
        course, _chapter_id, _quiz_id, assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)

        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment_id,
                student_id=STUDENT_ID,
                status="graded",
                grade=150,  # over the 100 max_score
                graded_by=TEACHER_ID,
            )
        )
        db.commit()

        breakdown = calculate_student_grade_for_course(db, course, STUDENT_ID)
        assert breakdown.assignment_avg == 100.0
        # No quiz attempt exists, so the quiz category is not live and the
        # assignment carries the full weight.
        assert breakdown.assignment_weighted == 100.0
        assert (breakdown.effective_quiz_weight, breakdown.effective_assignment_weight) == (0, 100)

    def test_uncompleted_attempt_does_not_count(self, db: Session, student) -> None:
        """Attempts without ``completed_at`` (still in flight, saved
        draft, abandoned) MUST be excluded — otherwise a student who
        opens a quiz and walks away gets a 0% baked into their average.
        """
        course, _chapter_id, quiz_id, _assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=0,
                max_score=10,
                completed_at=None,  # incomplete
            )
        )
        db.commit()

        breakdown = calculate_student_grade_for_course(db, course, STUDENT_ID)
        # No completed attempts → 0% quiz_avg over 1 quiz total.
        assert breakdown.quiz_avg == 0.0


class TestCalculateAllStudentGrades:
    """The batch entry point used by the teacher gradebook. Must
    produce the same per-student breakdown as the single-student
    function (anti-divergence pin) and attach manual grades when present.
    """

    def test_empty_when_no_enrollments(self, db: Session, student) -> None:
        course, _chapter_id, _quiz_id, _assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        # Student exists but is not enrolled — batch returns empty list.
        results = calculate_all_student_grades(db, course)
        assert results == []

    def test_single_student_matches_single_student_path(self, db: Session, student) -> None:
        """Anti-divergence: the same data should produce identical
        breakdowns through ``calculate_student_grade_for_course`` and
        ``calculate_all_student_grades`` — the batch path is just a
        query-count optimisation, not a behaviour change.
        """
        course, chapter_id, quiz_id, assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=7,
                max_score=10,
                completed_at=datetime.now(UTC),
            )
        )
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment_id,
                student_id=STUDENT_ID,
                status="graded",
                grade=80,
                graded_by=TEACHER_ID,
            )
        )
        db.add(
            ChapterProgress(
                id=uuid.uuid4(),
                user_id=STUDENT_ID,
                chapter_id=chapter_id,
                completed=True,
                completion_type="self",
            )
        )
        db.commit()

        single = calculate_student_grade_for_course(db, course, STUDENT_ID)
        batch = calculate_all_student_grades(db, course)

        assert len(batch) == 1
        assert batch[0]["student_id"] == str(STUDENT_ID)
        batch_breakdown = batch[0]["breakdown"]
        # The two breakdowns must be field-for-field identical.
        assert batch_breakdown.quiz_avg == single.quiz_avg
        assert batch_breakdown.assignment_avg == single.assignment_avg
        assert batch_breakdown.participation_pct == single.participation_pct
        assert batch_breakdown.final_score == single.final_score
        assert batch_breakdown.letter_grade == single.letter_grade

    def test_manual_grade_is_attached_to_row(self, db: Session, student) -> None:
        """Manual grades override the calculated letter when the teacher
        sets one. The calculator surfaces both — the gradebook UI picks
        which to display. Pin that the manual grade reaches the row.
        """
        course, _chapter_id, _quiz_id, _assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)

        db.add(
            StudentGrade(
                id=uuid.uuid4(),
                student_id=STUDENT_ID,
                course_id=course.id,
                grade="A+",
                comment="Manual override",
                graded_by=TEACHER_ID,
            )
        )
        db.commit()

        batch = calculate_all_student_grades(db, course)
        assert len(batch) == 1
        assert batch[0]["manual_grade"] == "A+"

    def test_course_with_no_gradable_chapters_short_circuits(
        self,
        db: Session,
        student,
    ) -> None:
        """When a course has zero gradable chapters, the helper
        ``_get_quiz_ids_for_chapters`` / ``_get_assignment_ids_for_chapters``
        early-return ``[]`` instead of issuing useless IN-clause
        queries. Pin the short-circuit so a refactor that drops the
        guard surfaces as a perf regression rather than a silent one.
        """
        _ensure_users(db)
        course = make_course_with_text(
            db,
            course_id="empty-course",
            title="Empty",
            status="published",
            created_by=TEACHER_ID,
            quiz_weight=50,
            assignment_weight=50,
        )
        db.commit()
        _enroll(db, STUDENT_ID, course.id)

        # Single-student path — zero everywhere, no crash.
        single = calculate_student_grade_for_course(db, course, STUDENT_ID)
        assert single.quiz_avg == 0.0
        assert single.assignment_avg == 0.0
        assert single.participation_pct == 0.0
        assert single.final_score == 0.0

        # Batch path — one row, zero everywhere.
        batch = calculate_all_student_grades(db, course)
        assert len(batch) == 1
        assert batch[0]["breakdown"].final_score == 0.0

    def test_assignment_clamp_applies_in_batch_too(self, db: Session, student) -> None:
        """The over-100% clamp must also fire on the batch path —
        regression net against a future refactor that moves the
        clamp to only one of the two code paths.
        """
        course, _chapter_id, _quiz_id, assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)

        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment_id,
                student_id=STUDENT_ID,
                status="graded",
                grade=200,
                graded_by=TEACHER_ID,
            )
        )
        db.commit()

        batch = calculate_all_student_grades(db, course)
        assert batch[0]["breakdown"].assignment_avg == 100.0


class TestCategoryGoesLiveOnlyWithGradedWork:
    """A category counts once it holds graded work — not when an item exists.

    Found by an adversarial review of the empty-category redistribution, and it
    is the more dangerous half of that change. Gating on existence means a
    teacher who creates the first assignment — due in two weeks, nothing
    submitted — instantly restores its configured weight against a zero
    average. On the real course (4 quizzes, 0 assignments, 13 students) every
    student would drop from 100% to 40% in the same instant: A to F, no
    warning, nobody having missed anything.
    """

    def test_creating_an_assignment_does_not_move_anyones_grade(self, db: Session, student) -> None:
        course, _chapter_id, quiz_id, _assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=10,
                max_score=10,
                completed_at=datetime.now(UTC),
            )
        )
        db.commit()

        # The assignment exists (the fixture creates it) but nothing has been
        # submitted or marked, so only the quiz category is live.
        breakdown = calculate_student_grade_for_course(db, course, STUDENT_ID)

        assert breakdown.final_score == 100.0
        assert breakdown.letter_grade == "A"
        assert (breakdown.effective_quiz_weight, breakdown.effective_assignment_weight) == (100, 0)

    def test_first_marked_submission_brings_the_configured_split_back(self, db: Session, student) -> None:
        course, _chapter_id, quiz_id, assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=10,
                max_score=10,
                completed_at=datetime.now(UTC),
            )
        )
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment_id,
                student_id=STUDENT_ID,
                status="graded",
                grade=50,  # half of max_score 100
                graded_by=TEACHER_ID,
            )
        )
        db.commit()

        breakdown = calculate_student_grade_for_course(db, course, STUDENT_ID)

        # Weights 50/50 are back now that both categories carry graded work.
        assert (breakdown.effective_quiz_weight, breakdown.effective_assignment_weight) == (50, 50)
        assert breakdown.final_score == 75.0

    def test_an_ungraded_submission_does_not_wake_the_category(self, db: Session, student) -> None:
        """Submitted but not yet marked is still nothing to weigh.

        Otherwise a single student handing work in early would drag the whole
        class down until the teacher got round to marking it.
        """
        course, _chapter_id, quiz_id, assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=10,
                max_score=10,
                completed_at=datetime.now(UTC),
            )
        )
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment_id,
                student_id=STUDENT_ID,
                status="submitted",
                grade=None,
                graded_by=None,
            )
        )
        db.commit()

        breakdown = calculate_student_grade_for_course(db, course, STUDENT_ID)

        assert (breakdown.effective_quiz_weight, breakdown.effective_assignment_weight) == (100, 0)
        assert breakdown.final_score == 100.0

    def test_the_whole_class_is_graded_on_the_same_weights(self, db: Session, student) -> None:
        """One classmate's marked work switches the split for everyone.

        Per-student weights would mean two people in one class holding
        different definitions of the same number — the exact thing Принцип 3
        forbids.
        """
        other_id = uuid.uuid4()
        db.add(
            User(
                id=other_id,
                email="other-student@test.local",
                full_name="Other Student",
                role=UserRole.STUDENT,
            )
        )
        course, _chapter_id, quiz_id, assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)
        _enroll(db, other_id, course.id)
        for uid in (STUDENT_ID, other_id):
            db.add(
                QuizAttempt(
                    id=uuid.uuid4(),
                    quiz_id=quiz_id,
                    user_id=uid,
                    score=10,
                    max_score=10,
                    completed_at=datetime.now(UTC),
                )
            )
        # Only the *other* student has marked work.
        db.add(
            AssignmentSubmission(
                id=uuid.uuid4(),
                assignment_id=assignment_id,
                student_id=other_id,
                status="graded",
                grade=100,
                graded_by=TEACHER_ID,
            )
        )
        db.commit()

        mine = calculate_student_grade_for_course(db, course, STUDENT_ID)
        theirs = calculate_student_grade_for_course(db, course, other_id)

        assert (mine.effective_quiz_weight, mine.effective_assignment_weight) == (50, 50)
        assert (theirs.effective_quiz_weight, theirs.effective_assignment_weight) == (50, 50)
        # Same weights, different scores — mine has no assignment mark yet.
        assert mine.final_score == 50.0
        assert theirs.final_score == 100.0

    def test_batch_path_agrees_with_the_single_student_path(self, db: Session, student) -> None:
        course, _chapter_id, quiz_id, _assignment_id = _seed_course_with_one_quiz_one_assignment(db)
        _enroll(db, STUDENT_ID, course.id)
        db.add(
            QuizAttempt(
                id=uuid.uuid4(),
                quiz_id=quiz_id,
                user_id=STUDENT_ID,
                score=8,
                max_score=10,
                completed_at=datetime.now(UTC),
            )
        )
        db.commit()

        single = calculate_student_grade_for_course(db, course, STUDENT_ID)
        batch = calculate_all_student_grades(db, course)[0]["breakdown"]

        assert batch.effective_quiz_weight == single.effective_quiz_weight
        assert batch.effective_assignment_weight == single.effective_assignment_weight
        assert batch.final_score == single.final_score == 80.0
