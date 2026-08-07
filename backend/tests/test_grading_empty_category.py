"""Empty-category redistribution and the vacuous-course rule (D4).

The defect this closes is the largest real one in the old calculator, and it
is worth stating in production terms rather than abstractly.

Course ``1f3c4803`` has 4 quizzes, 0 assignments and 13 enrolled students. The
old formula weighted all three categories unconditionally, so the empty
assignment bucket contributed zero and kept its weight. A student answering
every question of every quiz perfectly scored the quiz weight and nothing
more — a failing letter, unreachable ceiling, no path to a certificate. Two
production courses and 23 students sat in that state.

Two rules fix it:

* an empty category drops out and its weight goes to the other one, decided at
  calculation time so adding the first assignment mid-course just works;
* a course with nothing gradable at all has no number to compute — reporting
  0% would read as "failed everything" to someone with nothing to fail — so it
  reports ``completion_pass`` and the certificate gate falls back to progress.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.models.course import Course
from app.services.grade_calculator import _build_breakdown, effective_weights

if TYPE_CHECKING:
    from app.schemas.grade import GradeBreakdown


def _course(quiz: int = 40, assignment: int = 60) -> Course:
    return Course(id="c-eff", status="draft", quiz_weight=quiz, assignment_weight=assignment)


def _breakdown(
    course: Course,
    quiz_avg: float,
    assignment_avg: float,
    *,
    has_quizzes: bool,
    has_assignments: bool,
) -> GradeBreakdown:
    return _build_breakdown(
        course,
        quiz_avg,
        assignment_avg,
        0.0,
        has_quizzes=has_quizzes,
        has_assignments=has_assignments,
    )


# --------------------------------------------------------------------------
# the production defect
# --------------------------------------------------------------------------


def test_perfect_student_in_a_quiz_only_course_scores_100() -> None:
    """Course 1f3c4803, the exact shape: quizzes only, nothing else.

    Before: 40 (the quiz weight) and a failing letter, permanently.
    """
    b = _breakdown(_course(), quiz_avg=100.0, assignment_avg=0.0, has_quizzes=True, has_assignments=False)

    assert b.final_score == 100.0
    assert b.letter_grade == "A"
    assert (b.effective_quiz_weight, b.effective_assignment_weight) == (100, 0)
    assert b.weights_redistributed is True


def test_half_marks_in_a_quiz_only_course_are_half_not_a_fifth() -> None:
    b = _breakdown(_course(), quiz_avg=50.0, assignment_avg=0.0, has_quizzes=True, has_assignments=False)

    assert b.final_score == 50.0


def test_assignment_only_course_redistributes_the_other_way() -> None:
    b = _breakdown(_course(), quiz_avg=0.0, assignment_avg=90.0, has_quizzes=False, has_assignments=True)

    assert b.final_score == 90.0
    assert (b.effective_quiz_weight, b.effective_assignment_weight) == (0, 100)
    assert b.weights_redistributed is True


# --------------------------------------------------------------------------
# the ordinary case must not move
# --------------------------------------------------------------------------


def test_a_course_with_both_categories_uses_the_configured_weights() -> None:
    b = _breakdown(_course(40, 60), quiz_avg=100.0, assignment_avg=50.0, has_quizzes=True, has_assignments=True)

    assert b.final_score == 70.0  # 100*0.4 + 50*0.6
    assert (b.effective_quiz_weight, b.effective_assignment_weight) == (40, 60)
    assert b.weights_redistributed is False


def test_redistribution_is_decided_per_calculation_not_stored() -> None:
    """Adding the first assignment mid-course must restore the real weights.

    Same course object, same configured weights — only the presence of items
    changes, and the effective split follows immediately.
    """
    course = _course(40, 60)

    before = _breakdown(course, 100.0, 0.0, has_quizzes=True, has_assignments=False)
    after = _breakdown(course, 100.0, 0.0, has_quizzes=True, has_assignments=True)

    assert (before.effective_quiz_weight, before.effective_assignment_weight) == (100, 0)
    assert (after.effective_quiz_weight, after.effective_assignment_weight) == (40, 60)
    assert course.quiz_weight == 40  # unchanged on the row


@pytest.mark.parametrize(
    ("quiz_w", "assignment_w", "quiz_avg", "assignment_avg", "expected"),
    [
        (40, 60, 100.0, 100.0, 100.0),
        (40, 60, 0.0, 0.0, 0.0),
        (50, 50, 80.0, 60.0, 70.0),
        (70, 30, 90.0, 50.0, 78.0),
    ],
)
def test_weighted_mean_is_unchanged_for_full_courses(
    quiz_w: int, assignment_w: int, quiz_avg: float, assignment_avg: float, expected: float
) -> None:
    b = _breakdown(_course(quiz_w, assignment_w), quiz_avg, assignment_avg, has_quizzes=True, has_assignments=True)

    assert b.final_score == expected


# --------------------------------------------------------------------------
# the vacuous course
# --------------------------------------------------------------------------


def test_course_with_nothing_gradable_reports_completion_not_zero() -> None:
    """Most of the 4 certificates issued so far came from this shape.

    A content-only course has nothing to fail. Reporting 0%/F would brand
    every student on it as failing.
    """
    b = _breakdown(_course(), quiz_avg=0.0, assignment_avg=0.0, has_quizzes=False, has_assignments=False)

    assert b.result_state == "completion_pass"
    assert b.letter_grade == ""
    assert (b.effective_quiz_weight, b.effective_assignment_weight) == (0, 0)
    assert b.weights_redistributed is False


def test_graded_courses_keep_the_graded_state() -> None:
    for has_q, has_a in ((True, False), (False, True), (True, True)):
        b = _breakdown(_course(), 50.0, 50.0, has_quizzes=has_q, has_assignments=has_a)
        assert b.result_state == "graded"


# --------------------------------------------------------------------------
# participation cannot come back through this path
# --------------------------------------------------------------------------


def test_participation_never_contributes_even_with_a_stale_row() -> None:
    """A row written before the CHECK landed must still not affect a score."""
    course = _course(40, 60)
    course.participation_weight = 20  # only reachable pre-migration

    b = _build_breakdown(course, 100.0, 100.0, 100.0, has_quizzes=True, has_assignments=True)

    assert b.participation_weighted == 0.0
    assert b.final_score == 100.0


# --------------------------------------------------------------------------
# effective_weights on its own
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("has_q", "has_a", "expected"),
    [(True, True, (40, 60)), (True, False, (100, 0)), (False, True, (0, 100)), (False, False, (0, 0))],
)
def test_effective_weights_table(has_q: bool, has_a: bool, expected: tuple[int, int]) -> None:
    assert effective_weights(_course(40, 60), has_quizzes=has_q, has_assignments=has_a) == expected
