"""Pydantic schemas for the Daily Challenge surface.

Three responses are public:

* ``DailyChallengeTodayResponse`` — what the daily card renders before
  the user submits. Answer key (``is_correct``, ``correct_option_id``,
  ``explanation``) is NOT included; those land on the submit response.
* ``DailyChallengeAttemptResponse`` — the post-submit reveal. Carries
  the correct option id, explanation, and updated streak.
* ``DailyChallengeStreakResponse`` — sidebar / profile chip data.

Authoring schemas (``DailyChallengeQuestionCreate`` etc.) come in
Sprint 3 with the editorial pipeline; not in this file yet.
"""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 — Pydantic runtime resolution
from typing import Literal
from uuid import UUID  # noqa: TC003 — Pydantic runtime resolution

from pydantic import BaseModel, ConfigDict, Field

# Mirrors ``daily_challenge_questions.question_type`` CHECK.
DailyChallengeQuestionType = Literal["multiple_choice", "true_false"]


class DailyChallengeOptionStudentView(BaseModel):
    """One option as it appears to the student BEFORE submitting.
    No ``is_correct`` — the answer key is revealed only after submit.
    Text is the locale-resolved string from ``content_versions``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    option_text: str
    order_index: int = Field(..., ge=0, le=5)


class DailyChallengeAttemptSummary(BaseModel):
    """The user's existing live attempt for today, embedded in the
    today-response when present so the client renders the post-submit
    state without a second round-trip."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    selected_option_id: UUID | None
    is_correct: bool
    streak_after: int | None
    submitted_at: datetime


class DailyChallengeTodayResponse(BaseModel):
    """``GET /daily-challenge/today`` payload."""

    model_config = ConfigDict(from_attributes=True)

    challenge_date: date
    question_id: UUID
    question_type: DailyChallengeQuestionType
    question_text: str
    options: list[DailyChallengeOptionStudentView]
    # Bible reference for "open this passage" link on the card.
    bible_book: str
    bible_chapter: int
    bible_verse_from: int | None
    bible_verse_to: int | None
    # Set when the user already submitted today. Client renders the
    # post-submit reveal state without calling the attempt endpoint.
    already_attempted: bool
    user_attempt: DailyChallengeAttemptSummary | None = None


class DailyChallengeAttemptCreate(BaseModel):
    """``POST /daily-challenge/today/attempt`` body."""

    selected_option_id: UUID


class DailyChallengeAttemptResponse(BaseModel):
    """``POST /daily-challenge/today/attempt`` payload — the reveal."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    challenge_date: date
    selected_option_id: UUID
    correct_option_id: UUID
    is_correct: bool
    explanation: str | None
    streak_after: int
    submitted_at: datetime


class DailyChallengeStreakResponse(BaseModel):
    """``GET /daily-challenge/streak`` payload."""

    model_config = ConfigDict(from_attributes=True)

    current_streak: int = Field(..., ge=0)
    longest_streak: int = Field(..., ge=0)
    last_engaged_date: date | None
