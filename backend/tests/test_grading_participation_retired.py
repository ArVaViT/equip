"""Participation retirement — Phase 1 / M2 of the grading redesign (D5).

The retirement has to be atomic across four layers, because the review that
produced the design found three separate leaks in an earlier draft: data
rewritten but defaults left at 20, defaults fixed but the API still accepting
a positive weight, and the API pinned but stale browsers 422-ing mid-edit.
Each layer gets a test here.

The arithmetic has two rules, and the first one is a judgement call worth
stating: the untouched platform default 30/50/20 folds to **40/60**, the new
default — not to the 38/62 that proportional arithmetic gives. Nobody ever
chose 30/50/20. Carrying that non-decision through a rounding step would leave
a school with two different splits (legacy 38/62, new 40/60) and hand teachers
a number they cannot reproduce on paper. Weights a teacher actually set do keep
their ratio.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from app.models.course import Course
from app.schemas.grade import GradingConfigUpdate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# --------------------------------------------------------------------------
# layer 2: defaults
# --------------------------------------------------------------------------


def test_new_course_has_no_participation_weight(db: Session) -> None:
    """A course created after the migration must not resurrect participation.

    This is the leak the review caught: rewriting the rows without moving the
    column defaults means every subsequent course quietly reintroduces the
    double counting.
    """
    course = Course(id="c-weights", status="draft")
    db.add(course)
    db.flush()

    assert course.participation_weight == 0
    assert course.quiz_weight == 40
    assert course.assignment_weight == 60
    assert course.quiz_weight + course.assignment_weight == 100


# --------------------------------------------------------------------------
# layer 3: the write path
# --------------------------------------------------------------------------


def test_stale_client_payload_is_folded_not_rejected() -> None:
    """The exact shape a browser loaded before the change keeps sending.

    Rejecting it would strand a teacher mid-edit with an error they cannot act
    on. It folds to the new platform default, matching what the migration wrote
    to the same rows — so a stale tab cannot quietly drag a course back to a
    different split.
    """
    cfg = GradingConfigUpdate(quiz_weight=30, assignment_weight=50, participation_weight=20)

    assert cfg.participation_weight == 0
    assert (cfg.quiz_weight, cfg.assignment_weight) == (40, 60)


def test_folding_preserves_the_ratio_between_real_categories() -> None:
    cfg = GradingConfigUpdate(quiz_weight=60, assignment_weight=20, participation_weight=20)

    # 60:20 is 75:25 once participation is out of the way.
    assert (cfg.quiz_weight, cfg.assignment_weight) == (75, 25)
    assert cfg.participation_weight == 0


@pytest.mark.parametrize(
    ("quiz", "assignment", "participation", "expected"),
    [
        ((50), 30, 20, (63, 37)),
        (25, 15, 60, (63, 37)),
        (5, 35, 60, (13, 87)),
    ],
)
def test_ties_round_away_from_zero_like_postgres(
    quiz: int, assignment: int, participation: int, expected: tuple[int, int]
) -> None:
    """A .5 share must resolve the same way on both write paths.

    Python's built-in round() is half-to-even and would give 62/38 and 12/88
    here, while Postgres round() in the migration goes half-away-from-zero.
    The normalizer uses Decimal/ROUND_HALF_UP so the two agree.
    """
    cfg = GradingConfigUpdate(quiz_weight=quiz, assignment_weight=assignment, participation_weight=participation)

    assert (cfg.quiz_weight, cfg.assignment_weight) == expected


def test_pure_participation_payload_falls_back_to_the_default_split() -> None:
    """Unreachable through the UI, reachable by a hand-written request.

    There is no ratio to preserve, so inventing one would be arbitrary; the
    platform default is the honest answer.
    """
    cfg = GradingConfigUpdate(quiz_weight=0, assignment_weight=0, participation_weight=100)

    assert (cfg.quiz_weight, cfg.assignment_weight, cfg.participation_weight) == (40, 60, 0)


def test_two_category_payload_passes_through_untouched() -> None:
    cfg = GradingConfigUpdate(quiz_weight=40, assignment_weight=60)

    assert (cfg.quiz_weight, cfg.assignment_weight, cfg.participation_weight) == (40, 60, 0)


def test_participation_may_be_omitted_entirely() -> None:
    """New clients stop sending the field at all."""
    cfg = GradingConfigUpdate.model_validate({"quiz_weight": 70, "assignment_weight": 30})

    assert cfg.participation_weight == 0


def test_weights_still_must_sum_to_100() -> None:
    """Folding must not become a way to smuggle in a broken total."""
    with pytest.raises(ValidationError):
        GradingConfigUpdate(quiz_weight=30, assignment_weight=30, participation_weight=20)


@pytest.mark.parametrize(
    ("quiz", "assignment", "participation"),
    [
        (30, 50, 20),
        (50, 30, 20),  # 62.5 — a tie
        (25, 15, 60),  # 62.5 — a tie
        (5, 35, 60),  # 12.5 — a tie
        (0, 80, 20),
        (80, 0, 20),
        (10, 10, 80),
    ],
)
def test_folded_weights_always_sum_to_100(quiz: int, assignment: int, participation: int) -> None:
    """The CHECK constraint is absolute; rounding must never break it.

    Rounding lands on the quiz side and assignment takes the remainder, so no
    input can produce 99 or 101.
    """
    cfg = GradingConfigUpdate(quiz_weight=quiz, assignment_weight=assignment, participation_weight=participation)

    assert cfg.quiz_weight + cfg.assignment_weight + cfg.participation_weight == 100
    assert cfg.participation_weight == 0


# --------------------------------------------------------------------------
# layer 4: the route, end to end
# --------------------------------------------------------------------------


def test_put_config_from_a_stale_tab_succeeds_and_stores_two_categories(client, db: Session, teacher) -> None:
    course = Course(id="c-put-weights", status="draft", created_by=teacher.id)
    db.add(course)
    db.commit()

    resp = client.put(
        "/api/v1/grades/course/c-put-weights/config",
        json={"quiz_weight": 30, "assignment_weight": 50, "participation_weight": 20},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["participation_weight"] == 0
    assert (body["quiz_weight"], body["assignment_weight"]) == (40, 60)

    db.refresh(course)
    assert course.participation_weight == 0
