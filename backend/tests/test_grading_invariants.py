"""Invariants of the grade a student is shown and certified on.

Written as properties over tables rather than as expected constants, because
a constant only catches the case somebody thought of. Each block names the
property, then drives it across the shapes a real course takes: both
categories, one category, a category the teacher weighted at zero, nothing
marked yet, everything excused.

* **Bounded and additive** — a final score is in ``[0, 100]`` and is exactly
  the weighted sum the effective weights claim it is; the effective weights
  sum to 100 whenever there is a number, and to 0 whenever there is not.
* **Monotone** — more marks never lower a grade or its symbol, whether the
  marks are averages fed to the breakdown, a second attempt on a quiz, a
  resubmission marked higher, or work handed in that was missing.
* **Mercy costs nothing** — excusing work the student has not done, or did
  badly, never lowers their grade.
* **No division by zero** — a finished attempt on a quiz worth nothing is not
  a mark and not a crash.
* **The symbol follows the number that is shown** — the letter is read off the
  rounded score every surface prints, never off a number nobody sees.
* **One verdict** — the student's page, the teacher's board, the class list,
  the closed ведомость and the certificate snapshot agree on the same
  student, including on the pass line itself.
* **The deadline is an instant** — late is decided in UTC whatever wall clock
  the teacher typed it in.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.certificate import Certificate, CertificateStatus
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.grade_sheet import GradeSheetRow
from app.models.org_settings import DEFAULT_GRADE_BANDS, OrgSettings
from app.models.quiz import Quiz, QuizAttempt
from app.services.certificate_grade_snapshot import snapshot_certificate_grade
from app.services.certificate_readiness import BELOW_THRESHOLD, certificate_blockers
from app.services.grade_calculator import (
    _build_breakdown,
    calculate_all_student_grades,
    calculate_student_grade_for_course,
    effective_weights,
)
from app.services.grade_exemption_service import apply_exemption
from app.services.grade_sheet_service import FAIL, PASS, finalize_sheet, official_result
from app.services.grading_scheme import effective_bands, score_to_symbol
from app.services.late_work import is_late
from app.services.my_grade_service import build_my_course_grade
from app.services.student_progress_service import build_course_student_progress
from tests.conftest import STUDENT_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ── Pure arithmetic: the breakdown over a table of shapes ───────────────────


def _settings() -> OrgSettings:
    return OrgSettings(
        organization_id=TEST_ORGANIZATION_ID,
        default_grading_scheme="letter",
        default_pass_threshold=Decimal("70"),
        grade_bands=dict(DEFAULT_GRADE_BANDS),
    )


LETTER_BANDS = effective_bands(_settings(), "letter")
#: Symbols in ascending order of merit, so "not a lower symbol" is a comparison.
LETTER_RANK = {symbol: i for i, (_floor, symbol) in enumerate(reversed(LETTER_BANDS))}


def _breakdown(
    quiz_avg: float,
    assignment_avg: float,
    *,
    qw: int = 40,
    aw: int = 60,
    live_quizzes: bool = True,
    live_assignments: bool = True,
    has_quiz_items: bool = True,
    has_assignment_items: bool = True,
    all_items_excused: bool = False,
    current_quiz_avg: float | None = None,
    current_assignment_avg: float | None = None,
):
    course = Course(id="c-inv", status="draft", quiz_weight=qw, assignment_weight=aw, grading_scheme="letter")
    return _build_breakdown(
        course,
        quiz_avg,
        assignment_avg,
        0.0,
        has_quiz_items=has_quiz_items,
        has_assignment_items=has_assignment_items,
        has_quizzes=live_quizzes,
        has_assignments=live_assignments,
        settings=_settings(),
        has_gradable_chapters=has_quiz_items or has_assignment_items,
        all_items_excused=all_items_excused,
        student_has_quiz_marks=live_quizzes,
        student_has_assignment_marks=live_assignments,
        current_quiz_avg=current_quiz_avg,
        current_assignment_avg=current_assignment_avg,
    )


#: Every shape a course takes: (quiz weight, assignment weight, live quizzes, live assignments).
SHAPES = [
    pytest.param(40, 60, True, True, id="both-live"),
    pytest.param(40, 60, True, False, id="quizzes-only"),
    pytest.param(40, 60, False, True, id="assignments-only"),
    pytest.param(100, 0, True, True, id="quizzes-carry-everything"),
    pytest.param(0, 100, True, True, id="assignments-carry-everything"),
    pytest.param(0, 100, True, False, id="only-the-zero-weighted-category-is-live"),
    pytest.param(100, 0, False, True, id="only-the-zero-weighted-category-is-live-the-other-way"),
    pytest.param(40, 60, False, False, id="nothing-marked-yet"),
]

AVERAGES = [0.0, 0.01, 33.3, 59.99, 60.0, 69.99, 70.0, 89.99, 90.0, 99.5, 100.0]


@pytest.mark.parametrize(("qw", "aw", "live_q", "live_a"), SHAPES)
@pytest.mark.parametrize("quiz_avg", AVERAGES)
@pytest.mark.parametrize("assignment_avg", [0.0, 70.0, 100.0])
def test_the_final_is_bounded_and_is_exactly_the_weighted_sum_it_claims(
    qw: int, aw: int, live_q: bool, live_a: bool, quiz_avg: float, assignment_avg: float
) -> None:
    b = _breakdown(quiz_avg, assignment_avg, qw=qw, aw=aw, live_quizzes=live_q, live_assignments=live_a)

    assert 0.0 <= b.final_score <= 100.0
    assert 0.0 <= b.current_score <= 100.0
    if b.result_state == "graded":
        assert b.effective_quiz_weight + b.effective_assignment_weight == 100
        expected = quiz_avg * b.effective_quiz_weight / 100 + assignment_avg * b.effective_assignment_weight / 100
        assert b.final_score == round(expected, 2)
        assert b.quiz_weighted + b.assignment_weighted == pytest.approx(b.final_score, abs=0.011)
        assert b.letter_grade == score_to_symbol(b.final_score, "letter", LETTER_BANDS)
    else:
        assert b.effective_quiz_weight == b.effective_assignment_weight == 0
        assert b.final_score == 0.0
        assert b.letter_grade == ""


@pytest.mark.parametrize(("qw", "aw", "live_q", "live_a"), SHAPES)
def test_a_category_the_teacher_weighted_at_zero_never_inherits_the_grade(
    qw: int, aw: int, live_q: bool, live_a: bool
) -> None:
    course = Course(id="c-w", status="draft", quiz_weight=qw, assignment_weight=aw)
    eq, ea = effective_weights(course, has_quizzes=live_q, has_assignments=live_a)

    assert (eq, ea) in {(0, 0), (100, 0), (0, 100), (qw, aw)}
    if qw == 0:
        assert eq == 0
    if aw == 0:
        assert ea == 0
    if not live_q:
        assert eq == 0
    if not live_a:
        assert ea == 0


@pytest.mark.parametrize(("qw", "aw", "live_q", "live_a"), SHAPES)
@pytest.mark.parametrize("step", [0.01, 1.0, 10.0, 50.0])
def test_more_marks_never_lower_the_final_or_its_letter(
    qw: int, aw: int, live_q: bool, live_a: bool, step: float
) -> None:
    for quiz_avg in AVERAGES:
        for assignment_avg in AVERAGES:
            before = _breakdown(quiz_avg, assignment_avg, qw=qw, aw=aw, live_quizzes=live_q, live_assignments=live_a)
            for dq, da in ((step, 0.0), (0.0, step), (step, step)):
                after = _breakdown(
                    min(100.0, quiz_avg + dq),
                    min(100.0, assignment_avg + da),
                    qw=qw,
                    aw=aw,
                    live_quizzes=live_q,
                    live_assignments=live_a,
                )
                assert after.final_score >= before.final_score, (quiz_avg, assignment_avg, dq, da)
                assert after.current_score >= before.current_score
                if before.letter_grade and after.letter_grade:
                    assert LETTER_RANK[after.letter_grade] >= LETTER_RANK[before.letter_grade]


def test_current_rides_the_same_weights_as_final() -> None:
    """«Текущая» differs only in the denominator inside a category (D10)."""
    b = _breakdown(40.0, 30.0, qw=70, aw=30, current_quiz_avg=80.0, current_assignment_avg=60.0)

    assert b.final_score == 37.0
    assert b.current_score == 74.0
    assert b.scores_differ is True
    assert b.current_letter_grade == "C"
    assert b.letter_grade == "F"


def test_everything_excused_is_not_assessed_whatever_the_averages_say() -> None:
    for quiz_avg in AVERAGES:
        b = _breakdown(quiz_avg, 100.0, all_items_excused=True)
        assert b.result_state == "not_assessed"
        assert b.final_score == 0.0 and b.letter_grade == ""


# ── Rounding at the band edges ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("quiz_avg", "symbol"),
    [
        (89.994, "B"),  # rounds to 89.99
        (89.995, "A"),  # rounds to 90.0 — a float tie, decided by the binary representation
        (89.996, "A"),
        (89.5, "B"),  # one decimal does not round it up to the A line
        (69.994, "D"),
        (69.995, "C"),
        (59.999, "D"),  # 60.0 after rounding
        (0.004, "F"),
        (99.999, "A"),
    ],
)
def test_the_letter_is_read_from_the_two_decimal_score_every_surface_prints(quiz_avg: float, symbol: str) -> None:
    """Whatever the rounding policy at a tie, the symbol and the number must
    come from the same value — a 90.0 beside a B is the contradiction every
    screen is built to avoid."""
    b = _breakdown(quiz_avg, 0.0, qw=100, aw=0, live_assignments=False)

    assert b.final_score == round(quiz_avg, 2)
    assert b.letter_grade == symbol == score_to_symbol(b.final_score, "letter", LETTER_BANDS)


@pytest.mark.parametrize(
    ("score", "threshold", "passes"),
    [
        (70.0, Decimal("70"), True),
        (69.99, Decimal("70"), False),
        (69.995, Decimal("70"), True),  # the breakdown already rounded it to 70.0
        (100.0, Decimal("100"), True),
        (0.0, Decimal("0"), True),
    ],
)
def test_the_pass_line_is_inclusive_on_the_rounded_score(score: float, threshold: Decimal, passes: bool) -> None:
    b = _breakdown(score, 0.0, qw=100, aw=0, live_assignments=False)
    state, code, number, is_override = official_result(
        b, None, None, scheme="letter", pass_threshold=threshold, bands=LETTER_BANDS
    )

    assert state == (PASS if passes else FAIL)
    assert code == b.letter_grade and number is None and is_override is False


@pytest.mark.parametrize(
    ("code", "passes"),
    [("A", True), ("B", True), ("C", True), ("D", False), ("F", False)],
)
def test_a_hand_set_letter_is_measured_by_its_floor_against_the_line(code: str, passes: bool) -> None:
    computed_fail = _breakdown(10.0, 0.0, qw=100, aw=0, live_assignments=False)
    state, got, _number, is_override = official_result(
        computed_fail, code, None, scheme="letter", pass_threshold=Decimal("70"), bands=LETTER_BANDS
    )

    assert is_override is True and got == code
    assert state == (PASS if passes else FAIL)


@pytest.mark.parametrize(
    "state",
    ["not_graded_yet", "zero_weighted", "not_assessed"],
)
def test_an_override_outranks_every_no_number_state(state: str) -> None:
    if state == "not_assessed":
        b = _breakdown(0.0, 0.0, all_items_excused=True)
    elif state == "not_graded_yet":
        b = _breakdown(0.0, 0.0, live_quizzes=False, live_assignments=False)
    else:
        b = _breakdown(100.0, 0.0, qw=0, aw=100, live_assignments=False)
    assert b.result_state == state

    verdict, *_rest = official_result(b, "B", None, scheme="letter", pass_threshold=Decimal("70"), bands=LETTER_BANDS)
    assert verdict == PASS


# ── Deadlines are instants ──────────────────────────────────────────────────

INDIANA = ZoneInfo("America/Indiana/Indianapolis")
DUE_INDIANA = datetime(2026, 10, 11, 23, 59, tzinfo=INDIANA)  # EDT: 03:59Z on the 12th


@pytest.mark.parametrize(
    ("handed_in", "late"),
    [
        (DUE_INDIANA.astimezone(UTC), False),  # on the dot is on time
        (DUE_INDIANA.astimezone(UTC) - timedelta(seconds=1), False),
        (DUE_INDIANA.astimezone(UTC) + timedelta(seconds=1), True),
        (datetime(2026, 10, 12, 0, 30, tzinfo=UTC), False),  # past midnight UTC, still the 11th in Indiana
        (datetime(2026, 10, 12, 3, 58, tzinfo=UTC), False),
        (datetime(2026, 10, 12, 4, 0, tzinfo=UTC), True),
        (datetime(2026, 10, 12, 3, 58), False),  # naive is UTC — what the SQLite tests hand back
        (datetime(2026, 10, 12, 4, 0), True),
        (None, False),
    ],
)
def test_late_is_decided_on_the_instant_not_the_wall_clock(handed_in: datetime | None, late: bool) -> None:
    assert is_late(handed_in, DUE_INDIANA) is late
    assert is_late(handed_in, DUE_INDIANA.astimezone(UTC)) is late
    assert is_late(handed_in, DUE_INDIANA.astimezone(UTC).replace(tzinfo=None)) is late


def test_no_deadline_is_never_late() -> None:
    assert is_late(datetime(2030, 1, 1, tzinfo=UTC), None) is False


# ── Against the database: attempts, submissions, exemptions, surfaces ────────


def _course(
    db: Session, teacher, course_id: str, *, quizzes: int, assignments: int, qw: int = 40, aw: int = 60
) -> tuple[Course, list[Quiz], list[Assignment], Enrollment]:
    course = Course(
        id=course_id,
        status="published",
        created_by=teacher.id,
        quiz_weight=qw,
        assignment_weight=aw,
        grading_scheme="letter",
        pass_threshold=Decimal("70.00"),
    )
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    made_q, made_a = [], []
    for i in range(quizzes):
        ch = Chapter(id=f"{course_id}-q{i}", module_id=module.id, order_index=i, chapter_type="quiz", title=f"Q{i}")
        db.add(ch)
        db.flush()
        quiz = Quiz(id=uuid.uuid4(), chapter_id=ch.id)
        db.add(quiz)
        made_q.append(quiz)
    for i in range(assignments):
        ch = Chapter(
            id=f"{course_id}-a{i}",
            module_id=module.id,
            order_index=quizzes + i,
            chapter_type="assignment",
            title=f"A{i}",
        )
        db.add(ch)
        db.flush()
        assignment = Assignment(id=uuid.uuid4(), chapter_id=ch.id, max_score=100)
        db.add(assignment)
        made_a.append(assignment)
    enrollment = Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=100)
    db.add(enrollment)
    db.commit()
    return course, made_q, made_a, enrollment


def _attempt(db: Session, quiz: Quiz, score: int, max_score: int = 100, *, when: datetime | None = None) -> None:
    db.add(
        QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=STUDENT_ID,
            score=score,
            max_score=max_score,
            passed=max_score > 0 and score * 100 >= 70 * max_score,
            completed_at=when or datetime.now(UTC),
        )
    )
    db.commit()


def _submission(db: Session, assignment: Assignment, grade: int | None, *, when: datetime) -> None:
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            student_id=STUDENT_ID,
            status="graded" if grade is not None else "submitted",
            grade=grade,
            submitted_at=when,
            graded_at=when if grade is not None else None,
        )
    )
    db.commit()


def _pair(db: Session, course: Course) -> tuple[float, float]:
    b = calculate_student_grade_for_course(db, course, STUDENT_ID)
    return b.final_score, b.current_score


def test_a_worse_second_attempt_does_not_lower_the_grade(db: Session, teacher, student) -> None:
    course, (quiz,), _, _ = _course(db, teacher, "c-inv-retake", quizzes=1, assignments=0)
    _attempt(db, quiz, 80)
    before = _pair(db, course)

    _attempt(db, quiz, 20)

    assert _pair(db, course) == before == (80.0, 80.0)


def test_handing_in_missing_work_never_lowers_the_final(db: Session, teacher, student) -> None:
    course, (q0, q1), (a0,), _ = _course(db, teacher, "c-inv-missing", quizzes=2, assignments=1)
    _attempt(db, q0, 90)
    _submission(db, a0, 50, when=datetime.now(UTC))
    before_final, _ = _pair(db, course)

    for score in (0, 1, 50, 100):
        _attempt(db, q1, score)
        after_final, _ = _pair(db, course)
        assert after_final >= before_final, score
        before_final = after_final


def test_a_resubmission_marked_higher_raises_and_marked_lower_lowers(db: Session, teacher, student) -> None:
    """The teacher's latest mark decides (2026-10-03). This is the one place
    "more work" can lower a grade, and it is the teacher's decision, not the
    arithmetic's — pinned so the direction is visible."""
    course, _, (a0,), _ = _course(db, teacher, "c-inv-resubmit", quizzes=0, assignments=1)
    t0 = datetime.now(UTC)
    _submission(db, a0, 40, when=t0)
    assert _pair(db, course) == (40.0, 40.0)

    _submission(db, a0, 70, when=t0 + timedelta(hours=1))
    assert _pair(db, course) == (70.0, 70.0)

    _submission(db, a0, 60, when=t0 + timedelta(hours=2))
    assert _pair(db, course) == (60.0, 60.0)


def test_an_unmarked_resubmission_leaves_the_previous_mark_standing(db: Session, teacher, student) -> None:
    course, _, (a0,), _ = _course(db, teacher, "c-inv-resubmit-wait", quizzes=0, assignments=1)
    t0 = datetime.now(UTC)
    _submission(db, a0, 70, when=t0)
    _submission(db, a0, None, when=t0 + timedelta(hours=1))

    assert _pair(db, course) == (70.0, 70.0)


def test_excusing_work_not_done_or_done_badly_never_lowers_the_grade(db: Session, teacher, student) -> None:
    course, (q0, q1, q2), (a0,), _ = _course(db, teacher, "c-inv-excuse", quizzes=3, assignments=1)
    _attempt(db, q0, 90)
    _attempt(db, q1, 10)
    _submission(db, a0, 80, when=datetime.now(UTC))
    before = _pair(db, course)

    # q2 was never attempted: a zero in итоговая, absent from текущая.
    apply_exemption(
        db, student_id=STUDENT_ID, course_id=course.id, item_type="quiz", item_id=q2.id, teacher_id=teacher.id
    )
    db.commit()
    after_missing = _pair(db, course)
    assert after_missing[0] >= before[0] and after_missing[1] >= before[1]

    # q1 was done badly: below the student's own average in both numbers.
    apply_exemption(
        db, student_id=STUDENT_ID, course_id=course.id, item_type="quiz", item_id=q1.id, teacher_id=teacher.id
    )
    db.commit()
    after_bad = _pair(db, course)
    assert after_bad[0] >= after_missing[0] and after_bad[1] >= after_missing[1]
    assert after_bad == (90.0 * 0.4 + 80.0 * 0.6, 90.0 * 0.4 + 80.0 * 0.6)


def test_excusing_an_entire_category_hands_its_weight_to_the_other(db: Session, teacher, student) -> None:
    course, (q0,), (a0,), _ = _course(db, teacher, "c-inv-excuse-cat", quizzes=1, assignments=1)
    _attempt(db, q0, 50)
    _submission(db, a0, 90, when=datetime.now(UTC))
    assert _pair(db, course)[0] == 50 * 0.4 + 90 * 0.6

    apply_exemption(
        db, student_id=STUDENT_ID, course_id=course.id, item_type="quiz", item_id=q0.id, teacher_id=teacher.id
    )
    db.commit()

    b = calculate_student_grade_for_course(db, course, STUDENT_ID)
    assert (b.effective_quiz_weight, b.effective_assignment_weight) == (0, 100)
    assert b.final_score == 90.0
    assert b.weights_redistributed is True


def test_a_finished_attempt_on_a_quiz_worth_nothing_is_not_a_mark_and_not_a_crash(
    db: Session, teacher, student
) -> None:
    """A quiz with no questions cannot be published (`course_readiness` names
    it), so this is a defensive edge rather than a path a student walks. Pinned
    anyway: the attempt wakes the category — `category_is_live` asks for a
    finished attempt with nothing unread, and this one qualifies — but it is
    not a mark, every surface says "nothing marked yet", and nothing divides
    by the zero."""
    course, (q0, q1), _, enrollment = _course(db, teacher, "c-inv-zero-max", quizzes=2, assignments=0)
    _attempt(db, q0, 0, max_score=0)

    b = calculate_student_grade_for_course(db, course, STUDENT_ID)
    assert b.result_state == "graded", "the category woke on an attempt worth nothing — see docstring"
    assert b.student_has_quiz_marks is False
    (row,) = calculate_all_student_grades(db, course)
    assert row["breakdown"] == b
    assert build_my_course_grade(db, course, enrollment, STUDENT_ID)["result_state"] == "not_graded_yet"
    board = next(
        s for s in build_course_student_progress(db, course, course.id)["students"] if s["id"] == str(STUDENT_ID)
    )
    assert board["quiz_avg"] is None

    # Once a real quiz is marked the empty one is a zero in итоговая, like any
    # quiz the student has no mark on.
    _attempt(db, q1, 100)
    b = calculate_student_grade_for_course(db, course, STUDENT_ID)
    assert (b.final_score, b.current_score) == (50.0, 100.0)


@pytest.mark.parametrize(
    ("quiz_score", "assignment_grade", "letter", "passes"),
    [
        (100, 100, "A", True),
        (80, 70, "C", True),  # 32 + 42 = 74
        (100, 50, "C", True),  # 40 + 30 = 70 — exactly the line
        (75, 50, "D", False),  # 30 + 30 = 60
        (0, 0, "F", False),
    ],
)
def test_every_surface_agrees_on_the_same_student(
    db: Session, teacher, student, quiz_score: int, assignment_grade: int, letter: str, passes: bool
) -> None:
    """Student page, teacher board, class list, closed ведомость, certificate
    snapshot and the gate: one number, one symbol, one verdict."""
    course, (q0,), (a0,), enrollment = _course(
        db, teacher, f"c-inv-agree-{quiz_score}-{assignment_grade}", quizzes=1, assignments=1
    )
    _attempt(db, q0, quiz_score)
    _submission(db, a0, assignment_grade, when=datetime.now(UTC))
    expected = round(quiz_score * 0.4 + assignment_grade * 0.6, 2)

    official = calculate_student_grade_for_course(db, course, STUDENT_ID)
    assert (official.final_score, official.letter_grade) == (expected, letter)

    mine = build_my_course_grade(db, course, enrollment, STUDENT_ID)
    assert (mine["final_score"], mine["final_symbol"]) == (expected, letter)
    assert (mine["current_score"], mine["current_symbol"]) == (expected, letter)

    board = next(
        s for s in build_course_student_progress(db, course, course.id)["students"] if s["id"] == str(STUDENT_ID)
    )
    assert (board["overall_grade"], board["letter_grade"]) == (expected, letter)

    (class_row,) = calculate_all_student_grades(db, course)
    assert class_row["breakdown"] == official

    sheet = finalize_sheet(db, course, None, teacher.id)
    db.commit()
    (sheet_row,) = db.query(GradeSheetRow).filter(GradeSheetRow.sheet_id == sheet.id).all()
    assert (sheet_row.result_state, sheet_row.official_code, sheet_row.is_override) == (
        PASS if passes else FAIL,
        letter,
        False,
    )

    cert = Certificate(
        id=uuid.uuid4(), user_id=STUDENT_ID, course_id=course.id, status=CertificateStatus.TEACHER_APPROVED
    )
    db.add(cert)
    db.commit()
    snapshot_certificate_grade(db, cert, course)
    assert (cert.official_code, cert.official_score, cert.graded_via) == (letter, None, "computed")

    blockers = certificate_blockers(db, course, enrollment, STUDENT_ID)
    below = [b for b in blockers if b.code == BELOW_THRESHOLD]
    assert bool(below) is (not passes)
    assert [b["code"] for b in mine["certificate_blockers"]] == [b.code for b in blockers]
    if below:
        assert below[0].params == {"final_score": expected, "pass_threshold": 70.0, "provisional": False}


def test_a_hand_set_grade_reaches_every_surface_the_same_way(db: Session, teacher, student) -> None:
    from app.models.student_grade import StudentGrade

    course, (q0,), _, enrollment = _course(db, teacher, "c-inv-override", quizzes=1, assignments=0)
    _attempt(db, q0, 10)
    db.add(StudentGrade(student_id=STUDENT_ID, course_id=course.id, override_code="B", graded_by=teacher.id))
    db.commit()

    mine = build_my_course_grade(db, course, enrollment, STUDENT_ID)
    board = next(
        s for s in build_course_student_progress(db, course, course.id)["students"] if s["id"] == str(STUDENT_ID)
    )
    (class_row,) = calculate_all_student_grades(db, course)
    sheet = finalize_sheet(db, course, None, teacher.id)
    db.commit()
    (sheet_row,) = db.query(GradeSheetRow).filter(GradeSheetRow.sheet_id == sheet.id).all()
    cert = Certificate(
        id=uuid.uuid4(), user_id=STUDENT_ID, course_id=course.id, status=CertificateStatus.TEACHER_APPROVED
    )
    db.add(cert)
    db.commit()
    snapshot_certificate_grade(db, cert, course)

    assert mine["official_grade"] == board["manual_grade"] == class_row["manual_grade"] == "B"
    assert (sheet_row.result_state, sheet_row.official_code, sheet_row.is_override) == (PASS, "B", True)
    assert (cert.official_code, cert.graded_via) == ("B", "override")
    assert mine["certificate_blockers"] == [], "a passing hand-set grade ends the conversation"
    # The computed number is still carried beside it, unhidden: 10% F.
    assert (mine["final_score"], mine["final_symbol"]) == (10.0, "F")
