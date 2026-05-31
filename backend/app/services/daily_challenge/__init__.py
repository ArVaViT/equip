"""Daily Challenge service surface.

Sprint 2 — service layer on top of the foundation schema (Phase 5c).
Public entry points are re-exported here so route handlers import a
single namespace.

The Daily Challenge architecture is documented in
``memory:project-equip-daily-challenge-decisions.md``. Read it before
touching anything here.
"""

from app.services.daily_challenge.admin import (
    BilingualOption,
    BilingualView,
    CvCellView,
    NotPublishableError,
    OptionDraft,
    QuestionRejectedError,
    QueueItem,
    StatusTransitionError,
    create_question,
    fetch_bilingual_view,
    list_review_queue,
    promote_status,
    publish_question,
    reject_question,
    schedule_for_date,
    upsert_cv_for_question,
)
from app.services.daily_challenge.archive import (
    ArchiveAttemptOutcome,
    ArchiveDateNotAllowedError,
    ArchiveEntry,
    ArchiveNotScheduledError,
    get_archive_question,
    list_archive_entries,
    submit_archive_attempt,
)
from app.services.daily_challenge.attempt import (
    DailyChallengeAttemptOutcome,
    InvalidOptionError,
    NoScheduleError,
    submit_today_attempt,
)
from app.services.daily_challenge.llm import GeminiPromptClient, LLMError
from app.services.daily_challenge.orchestrator import (
    GenerationOutcome,
    GenerationRequest,
    run_generation,
)
from app.services.daily_challenge.schedule import get_today_question
from app.services.daily_challenge.streak import apply_streak_for_attempt, get_user_streak
from app.services.daily_challenge.text import (
    QuestionTextBundle,
    fetch_question_text_bundle,
)

__all__ = [
    "ArchiveAttemptOutcome",
    "ArchiveDateNotAllowedError",
    "ArchiveEntry",
    "ArchiveNotScheduledError",
    "BilingualOption",
    "BilingualView",
    "CvCellView",
    "DailyChallengeAttemptOutcome",
    "GeminiPromptClient",
    "GenerationOutcome",
    "GenerationRequest",
    "InvalidOptionError",
    "LLMError",
    "NoScheduleError",
    "NotPublishableError",
    "OptionDraft",
    "QuestionRejectedError",
    "QuestionTextBundle",
    "QueueItem",
    "StatusTransitionError",
    "apply_streak_for_attempt",
    "create_question",
    "fetch_bilingual_view",
    "fetch_question_text_bundle",
    "get_archive_question",
    "get_today_question",
    "get_user_streak",
    "list_archive_entries",
    "list_review_queue",
    "promote_status",
    "publish_question",
    "reject_question",
    "run_generation",
    "schedule_for_date",
    "submit_archive_attempt",
    "submit_today_attempt",
    "upsert_cv_for_question",
]
