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

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from app.models.course import Course
from app.models.org_settings import DEFAULT_GRADE_BANDS, OrgSettings
from app.services.grade_calculator import _build_breakdown, effective_weights
from tests.conftest import TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from app.schemas.grade import GradeBreakdown


def _course(quiz: int = 40, assignment: int = 60) -> Course:
    return Course(id="c-eff", status="draft", quiz_weight=quiz, assignment_weight=assignment)


def _settings() -> OrgSettings:
    """Shipped defaults, without a session — these tests exercise arithmetic."""
    return OrgSettings(
        organization_id=TEST_ORGANIZATION_ID,
        default_grading_scheme="letter",
        default_pass_threshold=Decimal("70"),
        grade_bands=dict(DEFAULT_GRADE_BANDS),
    )


def _breakdown(
    course: Course,
    quiz_avg: float,
    assignment_avg: float,
    *,
    has_quizzes: bool,
    has_assignments: bool,
    has_quiz_items: bool | None = None,
    has_assignment_items: bool | None = None,
    has_gradable_chapters: bool = False,
) -> GradeBreakdown:
    """Default: the course contains exactly the categories that are live.

    Pass ``has_*_items`` explicitly to model the case that matters most — the
    course has items, but nothing has been graded in them yet.
    """
    return _build_breakdown(
        course,
        quiz_avg,
        assignment_avg,
        0.0,
        has_quiz_items=has_quizzes if has_quiz_items is None else has_quiz_items,
        has_assignment_items=has_assignments if has_assignment_items is None else has_assignment_items,
        has_quizzes=has_quizzes,
        has_assignments=has_assignments,
        settings=_settings(),
        has_gradable_chapters=has_gradable_chapters,
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

    b = _build_breakdown(
        course,
        100.0,
        100.0,
        100.0,
        has_quiz_items=True,
        has_assignment_items=True,
        has_quizzes=True,
        has_assignments=True,
        settings=_settings(),
    )

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


# --------------------------------------------------------------------------
# "has items" and "has graded work" are different questions
# --------------------------------------------------------------------------


def test_course_with_quizzes_but_no_attempts_is_not_called_completion_pass() -> None:
    """The regression an adversarial review caught in the previous fix.

    First week of term: four quizzes sit in the course, nobody has taken one.
    Reporting `completion_pass` there tells thirteen students they passed and
    tells their teacher the course contains no quizzes — while four quizzes
    sit in it. Both statements are false.
    """
    b = _breakdown(
        _course(),
        0.0,
        0.0,
        has_quizzes=False,
        has_assignments=False,
        has_quiz_items=True,
        has_assignment_items=False,
    )

    assert b.result_state == "not_graded_yet"
    assert b.letter_grade == ""
    assert b.final_score == 0.0


def test_completion_pass_requires_the_course_to_actually_have_nothing() -> None:
    b = _breakdown(
        _course(),
        0.0,
        0.0,
        has_quizzes=False,
        has_assignments=False,
        has_quiz_items=False,
        has_assignment_items=False,
    )

    assert b.result_state == "completion_pass"


def test_first_graded_work_moves_the_course_out_of_not_graded_yet() -> None:
    b = _breakdown(
        _course(),
        90.0,
        0.0,
        has_quizzes=True,
        has_assignments=False,
        has_quiz_items=True,
        has_assignment_items=True,
    )

    assert b.result_state == "graded"
    assert b.final_score == 90.0
    assert (b.effective_quiz_weight, b.effective_assignment_weight) == (100, 0)


# --------------------------------------------------------------------------
# institutional bands actually reach the grade
# --------------------------------------------------------------------------


def test_school_bands_decide_the_symbol_not_hardcoded_letters(db) -> None:
    """The point of `org_settings`: a school moves its bands, grades follow.

    Before this was wired in, the calculator applied 90/80/70/60 to every
    course on the platform, so a school could edit the table and watch nothing
    happen. That is worse than not offering the setting at all.
    """
    from app.services.grade_calculator import resolve_symbol
    from app.services.grading_scheme import get_org_settings

    settings = get_org_settings(db, TEST_ORGANIZATION_ID)
    course = _course()

    assert resolve_symbol(85.0, course, settings) == "B"

    # UA practice: «5 от 85». The school lowers its A boundary.
    settings.grade_bands = {"letter": [[85, "A"], [75, "B"], [65, "C"], [55, "D"], [0, "F"]]}
    db.flush()

    assert resolve_symbol(85.0, course, settings) == "A"


def test_five_point_course_shows_five_point_symbols(db) -> None:
    """A course on the five-point scheme must not show a US letter.

    Showing «B» to a RU-locale student in a пятибалльная course is exactly the
    culturally-wrong default the redesign exists to remove.
    """
    from app.services.grade_calculator import resolve_symbol
    from app.services.grading_scheme import get_org_settings

    settings = get_org_settings(db, TEST_ORGANIZATION_ID)
    course = _course()
    course.grading_scheme = "five_point"

    assert resolve_symbol(95.0, course, settings) == "5"
    assert resolve_symbol(80.0, course, settings) == "4"
    assert resolve_symbol(72.0, course, settings) == "3"
    assert resolve_symbol(50.0, course, settings) == "2"


def test_percent_course_has_no_symbol(db) -> None:
    """The number is the result; inventing a letter beside it would be noise."""
    from app.services.grade_calculator import resolve_symbol
    from app.services.grading_scheme import get_org_settings

    course = _course()
    course.grading_scheme = "percent"

    assert resolve_symbol(82.0, course, get_org_settings(db, TEST_ORGANIZATION_ID)) == ""


def test_pass_fail_does_not_derive_a_pass_from_a_percentage(db) -> None:
    """D2: «зачёт» is completion-native, never a hidden average clearing a line.

    Returning a symbol here would reintroduce exactly the behaviour the design
    removed — and would do it silently, which is worse.
    """
    from app.services.grade_calculator import resolve_symbol
    from app.services.grading_scheme import get_org_settings

    course = _course()
    course.grading_scheme = "pass_fail"

    assert resolve_symbol(99.0, course, get_org_settings(db, TEST_ORGANIZATION_ID)) == ""


# --------------------------------------------------------------------------
# a category the teacher zeroed must never inherit the grade
# --------------------------------------------------------------------------


def test_zero_weight_category_does_not_take_over_the_grade() -> None:
    """Quizzes as practice self-checks, the essay carrying the whole grade.

    A real shape for a correspondence Bible school. Redistribution used to hand
    the quizzes 100% while the essay waited to be marked, grading the student
    on work their teacher had explicitly declared worthless — 4/10 on a
    practice check became a hard F in the gradebook and in the printed CSV.
    """
    course = _course(quiz=0, assignment=100)

    b = _breakdown(
        course,
        40.0,
        0.0,
        has_quizzes=True,
        has_assignments=False,
        has_quiz_items=True,
        has_assignment_items=True,
    )

    # Not "nothing graded yet" — the quizzes were taken and 40% is a real
    # figure. It simply carries no weight, and the gradebook must keep showing
    # it rather than denying a mark that exists.
    assert b.result_state == "zero_weighted"
    assert b.quiz_avg == 40.0
    assert b.letter_grade == ""
    assert (b.effective_quiz_weight, b.effective_assignment_weight) == (0, 0)


def test_zero_weight_category_cannot_manufacture_a_high_grade_either() -> None:
    """The mirror case: the lie cuts both ways.

    95% on a practice check would have read as an A earned from work that
    counts for nothing — which a teacher signing off the final grade would
    have no reason to distrust.
    """
    course = _course(quiz=0, assignment=100)

    b = _breakdown(
        course,
        95.0,
        0.0,
        has_quizzes=True,
        has_assignments=False,
        has_quiz_items=True,
        has_assignment_items=True,
    )

    assert b.result_state == "zero_weighted"
    assert b.quiz_avg == 95.0


def test_the_weighted_category_still_carries_everything_when_it_is_the_live_one() -> None:
    course = _course(quiz=0, assignment=100)

    b = _breakdown(
        course,
        0.0,
        80.0,
        has_quizzes=False,
        has_assignments=True,
        has_quiz_items=True,
        has_assignment_items=True,
    )

    assert b.result_state == "graded"
    assert (b.effective_quiz_weight, b.effective_assignment_weight) == (0, 100)
    assert b.final_score == 80.0


def test_course_items_are_reported_so_the_ui_can_word_itself_honestly() -> None:
    """Telling a teacher to "mark the first assignment" when the course has
    none sends them looking for something that does not exist."""
    b = _breakdown(
        _course(),
        90.0,
        0.0,
        has_quizzes=True,
        has_assignments=False,
        has_quiz_items=True,
        has_assignment_items=False,
    )

    assert b.has_quiz_items is True
    assert b.has_assignment_items is False


def test_course_under_construction_is_not_called_completion_pass_material() -> None:
    """A chapter typed «quiz» exists before the quiz does.

    `create_chapter` never creates a Quiz row, and the editor refuses to save a
    quiz with no questions — so a course mid-build has gradable chapters and no
    gradable items. Reporting that as "nothing to grade here" told a teacher
    staring at «Тест 1» that their course had no quizzes, and put the same
    claim on the exported sheet.

    The state is still `completion_pass` arithmetically — there is nothing to
    compute — but the surfaces must be able to tell the two apart.
    """
    b = _breakdown(
        _course(),
        0.0,
        0.0,
        has_quizzes=False,
        has_assignments=False,
        has_quiz_items=False,
        has_assignment_items=False,
        has_gradable_chapters=True,
    )

    assert b.result_state == "completion_pass"
    assert b.has_gradable_chapters is True


def test_a_genuinely_content_only_course_reports_no_gradable_chapters() -> None:
    b = _breakdown(
        _course(),
        0.0,
        0.0,
        has_quizzes=False,
        has_assignments=False,
        has_quiz_items=False,
        has_assignment_items=False,
    )

    assert b.result_state == "completion_pass"
    assert b.has_gradable_chapters is False
