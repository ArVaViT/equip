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

from app.schemas._request import RequestModel

# Runtime import, not a typing-only one: Pydantic resolves these
# annotations at class-construction time to build the validators.
from app.schemas.locale import LocaleCode  # noqa: TC001

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
    # Localized short-form book label (e.g. "Ин." for ru, "John" for en)
    # rendered straight into the card heading so the client doesn't have
    # to ship the book vocabulary. Falls back to ``bible_book`` (the raw
    # canonical English) when the locale isn't bundled.
    bible_book_label: str
    bible_chapter: int
    bible_verse_from: int | None
    bible_verse_to: int | None
    # Set when the user already submitted today. Client renders the
    # post-submit reveal state without calling the attempt endpoint.
    already_attempted: bool
    user_attempt: DailyChallengeAttemptSummary | None = None


class DailyChallengeAttemptCreate(RequestModel):
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


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


class DailyChallengeArchiveEntry(BaseModel):
    """One row in the archive calendar grid."""

    model_config = ConfigDict(from_attributes=True)

    challenge_date: date
    question_id: UUID
    bible_book: str
    bible_book_label: str
    bible_chapter: int
    bible_verse_from: int | None
    bible_verse_to: int | None
    # None = never attempted, True = correct, False = wrong.
    attempted_is_correct: bool | None
    # True when the only attempt on this date is an archive replay
    # (no live attempt happened that day). Drives the "Replay" badge
    # in the detail panel; live attempts get the full streak weight.
    archive_only_attempt: bool


class DailyChallengeArchiveListResponse(BaseModel):
    """``GET /daily-challenge/archive`` payload."""

    entries: list[DailyChallengeArchiveEntry]
    # Pass back to fetch the next page; ``None`` = no more rows.
    next_cursor: date | None


class DailyChallengeArchiveRevealView(BaseModel):
    """Reveal block embedded in an archive question response when the
    user has previously attempted (live or archive)."""

    model_config = ConfigDict(from_attributes=True)

    correct_option_id: UUID
    explanation: str | None
    last_attempt_was_correct: bool


class DailyChallengeArchiveQuestionResponse(BaseModel):
    """``GET /daily-challenge/archive/{challenge_date}`` payload."""

    model_config = ConfigDict(from_attributes=True)

    challenge_date: date
    question_id: UUID
    question_type: DailyChallengeQuestionType
    question_text: str
    options: list[DailyChallengeOptionStudentView]
    bible_book: str
    bible_book_label: str
    bible_chapter: int
    bible_verse_from: int | None
    bible_verse_to: int | None
    # Non-null when the user has attempted this date before; carries
    # answer key + explanation for the reveal-mode render.
    reveal: DailyChallengeArchiveRevealView | None


class DailyChallengeArchiveAttemptResponse(BaseModel):
    """``POST /daily-challenge/archive/{challenge_date}/attempt`` reveal."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    challenge_date: date
    selected_option_id: UUID
    correct_option_id: UUID
    is_correct: bool
    explanation: str | None
    submitted_at: datetime


# ---------------------------------------------------------------------------
# Editorial / admin schemas (Sprint 3)
# ---------------------------------------------------------------------------

DailyChallengeStatus = Literal[
    "draft",
    "scripture_validated",
    "doctrinally_reviewed",
    "bilingually_reviewed",
    "pilot_passed",
    "published",
    "archived",
]


class DailyChallengeOptionDraft(RequestModel):
    """Author-supplied option for ``POST /admin/daily-challenge/questions``."""

    text: str = Field(..., min_length=1, max_length=500)
    is_correct: bool = False


class DailyChallengeQuestionCreate(RequestModel):
    """``POST /admin/daily-challenge/questions`` body."""

    question_type: DailyChallengeQuestionType = "multiple_choice"
    bible_book: str = Field(..., min_length=1, max_length=64)
    bible_chapter: int = Field(..., gt=0)
    bible_verse_from: int | None = Field(None, gt=0)
    bible_verse_to: int | None = Field(None, gt=0)
    question_text: str = Field(..., min_length=1, max_length=2000)
    explanation: str | None = Field(None, max_length=4000)
    category: str | None = Field(None, max_length=64)
    options: list[DailyChallengeOptionDraft] = Field(..., min_length=2, max_length=6)


class DailyChallengeOptionEditorial(BaseModel):
    """Editorial view of an option — INCLUDES ``is_correct``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    option_text: str
    is_correct: bool
    order_index: int = Field(..., ge=0, le=5)


class DailyChallengeQuestionEditorial(BaseModel):
    """Full editorial view of a question — answer key + status + audit."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_type: DailyChallengeQuestionType
    status: DailyChallengeStatus
    rejected: bool
    rejection_reason: str | None
    published_at: datetime | None
    bible_book: str
    bible_chapter: int
    bible_verse_from: int | None
    bible_verse_to: int | None
    category: str | None
    source_locale: str | None
    question_text: str
    explanation: str | None
    options: list[DailyChallengeOptionEditorial]
    created_at: datetime
    updated_at: datetime


class DailyChallengeRejectRequest(RequestModel):
    reason: str = Field(..., min_length=1, max_length=500)


class DailyChallengeScheduleCreate(RequestModel):
    challenge_date: date
    question_id: UUID


class DailyChallengeScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    challenge_date: date
    question_id: UUID
    scheduled_at: datetime


# ---------------------------------------------------------------------------
# AI orchestrator schemas (Sprint 5)
# ---------------------------------------------------------------------------


class DailyChallengeGenerateRequest(RequestModel):
    """``POST /admin/daily-challenge/generate`` body."""

    bible_book: str = Field(..., min_length=1, max_length=64)
    bible_chapter: int = Field(..., gt=0)
    bible_verse_from: int | None = Field(None, gt=0)
    bible_verse_to: int | None = Field(None, gt=0)
    # Bounded so a runaway call can't spawn thousands of LLM round-trips.
    n_candidates_per_agent: int = Field(10, ge=1, le=20)
    max_survivors: int = Field(6, ge=1, le=12)


class DailyChallengeGenerateResponse(BaseModel):
    """``POST /admin/daily-challenge/generate`` response."""

    generation_run_id: UUID
    created_question_ids: list[UUID]
    rejected_at_scripture: int
    rejected_at_doctrinal: int
    rejected_at_bilingual: int
    rounds_executed: int
    errors: list[str]


# ---------------------------------------------------------------------------
# Bilingual review queue (Sprint 7)
# ---------------------------------------------------------------------------


class DailyChallengeQuestionQueueItem(BaseModel):
    """One row in the bilingual review queue list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: DailyChallengeStatus
    rejected: bool
    bible_book: str
    bible_chapter: int
    bible_verse_from: int | None
    bible_verse_to: int | None
    source_locale: str | None
    # Which locales have any cv row at all, so the editor can filter the
    # queue without opening every item. A dict rather than has_en/has_ru:
    # the queue has to answer the same question for however many
    # languages the platform serves.
    has_locale: dict[LocaleCode, bool]
    created_at: datetime
    updated_at: datetime


class DailyChallengeQuestionQueueResponse(BaseModel):
    items: list[DailyChallengeQuestionQueueItem]
    total: int


class DailyChallengeCvCell(BaseModel):
    """A single cv row reduced to what the editor needs to see."""

    model_config = ConfigDict(from_attributes=True)

    cv_id: UUID | None
    text: str
    origin: Literal["human", "mt"] | None
    locale: LocaleCode
    updated_at: datetime | None


class DailyChallengeBilingualOption(BaseModel):
    """One option with its text in every served language."""

    id: UUID
    order_index: int = Field(..., ge=0, le=5)
    is_correct: bool
    # Keyed by locale rather than two named fields: an option has as many
    # texts as the platform has languages.
    texts: dict[LocaleCode, DailyChallengeCvCell]


class DailyChallengeBilingualView(BaseModel):
    """GET /admin/daily-challenge/questions/{id}/bilingual payload.

    Named "bilingual" when the platform had two languages. It carries
    every served locale now; the route keeps its path so existing links
    into the review queue do not break.
    """

    id: UUID
    status: DailyChallengeStatus
    rejected: bool
    rejection_reason: str | None
    bible_book: str
    bible_chapter: int
    bible_verse_from: int | None
    bible_verse_to: int | None
    source_locale: str | None
    question_text: dict[LocaleCode, DailyChallengeCvCell]
    explanation: dict[LocaleCode, DailyChallengeCvCell]
    options: list[DailyChallengeBilingualOption]


class DailyChallengeCvUpsertRequest(RequestModel):
    """POST /admin/daily-challenge/questions/{id}/cv body."""

    field: Literal["question_text", "explanation", "option_text"]
    locale: LocaleCode
    text: str = Field(..., min_length=1, max_length=4000)
    # Required iff field == "option_text"; ignored otherwise.
    option_id: UUID | None = None
