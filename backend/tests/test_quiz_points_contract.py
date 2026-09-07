"""Locks the quiz_questions.points range contract (part of the 4-way mirror).

``schemas.quiz.QuizQuestionCreate.points`` is ``Field(ge=1, le=100)``; migration
``20260607120000_quiz_points_range_check`` tightened the DB CHECK to match
(``points BETWEEN 1 AND 100``) after the earlier constraint only enforced
``>= 0`` with no upper bound. This pins the schema side so the Postgres ⇄
Pydantic mirror can't silently drift again.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.quiz import QuizQuestionCreate


def _make(points: int) -> QuizQuestionCreate:
    # ``short_answer``: the range under test is ``points``; a choice question
    # would also need an answerable option list, which is a different contract.
    return QuizQuestionCreate(question_text="Q", question_type="short_answer", points=points)


def test_points_accepts_inclusive_bounds() -> None:
    assert _make(1).points == 1
    assert _make(100).points == 100


@pytest.mark.parametrize("bad", [0, -1, 101, 1000])
def test_points_rejects_out_of_range(bad: int) -> None:
    with pytest.raises(ValidationError):
        _make(bad)
