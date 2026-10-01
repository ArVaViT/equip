"""Rule 13 of the Daily Challenge rubric: short and plain.

The rubric checked theology and accuracy and nothing about reading. On
2026-09-30 one option in ten in production ran past 64 characters, the
longest 214, and the card cut them off with an ellipsis. The prompt now
asks for short answers, and the automated stage holds the limit rather
than trusting the model to.
"""

from __future__ import annotations

from app.services.daily_challenge.orchestrator import (
    MAX_OPTION_CHARS,
    MAX_QUESTION_CHARS,
    _too_long_to_read,
)
from app.services.daily_challenge.prompts import ROUND_1_SYSTEM


def _draft(question: str = "Who went to the tomb?", options: list[str] | None = None) -> dict:
    texts = options or ["Mary Magdalene", "Peter", "John", "Thomas"]
    return {
        "question_text": question,
        "options": [{"text": t, "is_correct": i == 0} for i, t in enumerate(texts)],
    }


def test_a_short_draft_passes() -> None:
    assert _too_long_to_read(_draft()) is None


def test_an_option_at_the_limit_passes() -> None:
    assert _too_long_to_read(_draft(options=["x" * MAX_OPTION_CHARS, "a", "b", "c"])) is None


def test_one_long_option_rejects_the_draft() -> None:
    reason = _too_long_to_read(_draft(options=["a", "b", "x" * (MAX_OPTION_CHARS + 1), "c"]))
    assert reason is not None and "option" in reason


def test_a_long_question_rejects_the_draft() -> None:
    reason = _too_long_to_read(_draft(question="x" * (MAX_QUESTION_CHARS + 1)))
    assert reason is not None and "question" in reason


def test_a_malformed_draft_is_left_to_the_other_checks() -> None:
    assert _too_long_to_read({"options": [None, {"text": 5}]}) is None


def test_the_writer_is_told_the_rule() -> None:
    assert "13. Short and plain" in ROUND_1_SYSTEM
    assert "ALL THIRTEEN" in ROUND_1_SYSTEM
