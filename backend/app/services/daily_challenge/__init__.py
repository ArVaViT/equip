"""Daily Challenge service surface.

Sprint 2 — service layer on top of the foundation schema (Phase 5c).
Public entry points are re-exported here so route handlers import a
single namespace.

The Daily Challenge architecture is documented in
``memory:project-equip-daily-challenge-decisions.md``. Read it before
touching anything here.
"""

from app.services.daily_challenge.attempt import (
    DailyChallengeAttemptOutcome,
    InvalidOptionError,
    NoScheduleError,
    submit_today_attempt,
)
from app.services.daily_challenge.schedule import get_today_question
from app.services.daily_challenge.streak import apply_streak_for_attempt, get_user_streak
from app.services.daily_challenge.text import (
    QuestionTextBundle,
    fetch_question_text_bundle,
)

__all__ = [
    "DailyChallengeAttemptOutcome",
    "InvalidOptionError",
    "NoScheduleError",
    "QuestionTextBundle",
    "apply_streak_for_attempt",
    "fetch_question_text_bundle",
    "get_today_question",
    "get_user_streak",
    "submit_today_attempt",
]
