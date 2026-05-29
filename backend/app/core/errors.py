"""Typed error envelope for HTTPExceptions.

Why this exists
---------------

Before this module every route raised
``HTTPException(detail="Course 'xyz' not found")`` — a free-form
human string. The frontend's only way to react differently to
"course missing" vs "you don't have permission" was substring-matching
on the message text, which:

* breaks when someone reworded the message
* breaks when the locale changes (Russian-speaking teacher,
  English-speaking admin)
* fights every accessibility / i18n best practice that says
  machine-readable codes belong in metadata, not in copy

This module introduces a small contract: each domain failure has a
short stable code (``ErrorCode`` enum), a human message that the
frontend toasts as-is, and an optional ``context`` dict for the
machine-readable bits (the ``course_id`` that wasn't found, the
``min_attempts`` left, etc.). The frontend has a typed switch on
the code; the toast still renders the message string.

Backwards-compatible by construction
------------------------------------

``equip_error`` returns an ``HTTPException`` whose ``detail`` field is
the structured envelope (a dict). FastAPI serialises that to JSON
verbatim, so the response body becomes::

    {"detail": {"code": "course_not_found", "message": "...", "context": {...}}}

instead of the old::

    {"detail": "..."}

Old routes that still raise ``HTTPException(detail="...")`` continue
to work — the frontend's ``getErrorDetail`` extractor falls back to
the string detail when no code is present. Migration is route-by-route
in follow-up PRs.
"""

from __future__ import annotations

import enum
from typing import Any

from fastapi import HTTPException


class ErrorCode(enum.StrEnum):
    """Stable machine-readable identifiers for every domain failure.

    Codes are ``snake_case``, scoped by feature (``auth.*``,
    ``course.*``, etc.). Adding a new code is a one-line append here
    + one client switch arm; removing one is a public-API break.

    Each member is documented inline so a frontend author can pick the
    right one without reading the route source.
    """

    # ── Auth / permissions ──────────────────────────────────────────────
    AUTH_REQUIRED = "auth.required"
    """No valid session; the user must sign in."""

    AUTH_FORBIDDEN = "auth.forbidden"
    """Caller is authenticated but lacks the required role / ownership."""

    # ── Generic resource lookups ────────────────────────────────────────
    RESOURCE_NOT_FOUND = "resource.not_found"
    """A specific entity was not located. ``context.resource_type`` +
    ``context.resource_id`` carry the specifics; route docstrings
    document what shape they take."""

    # ── Course lifecycle ────────────────────────────────────────────────
    COURSE_NOT_PUBLISHED = "course.not_published"
    """Action requires a published course; current state is draft or
    soft-deleted."""

    COURSE_ALREADY_ENROLLED = "course.already_enrolled"
    """Student tried to enrol in a course they're already in."""

    COURSE_ENROLMENT_CLOSED = "course.enrolment_closed"
    """Enrolment window is not currently open."""

    # ── Translation pipeline ────────────────────────────────────────────
    TRANSLATION_DISABLED = "translation.disabled"
    """Translation provider is not configured on this deployment."""

    TRANSLATION_WORKER_UNAUTHORIZED = "translation.worker_unauthorized"
    """Worker secret missing or wrong."""

    TRANSLATION_WORKER_UNCONFIGURED = "translation.worker_unconfigured"
    """``TRANSLATION_WORKER_SECRET`` env var unset on this deployment."""

    # ── Quiz / assignment lifecycle ─────────────────────────────────────
    QUIZ_NOT_OPEN = "quiz.not_open"
    """Quiz is not currently accepting submissions."""

    QUIZ_ATTEMPTS_EXHAUSTED = "quiz.attempts_exhausted"
    """Student has hit the per-quiz attempt cap."""

    # ── Daily Challenge ─────────────────────────────────────────────────
    DAILY_CHALLENGE_NOT_SCHEDULED = "daily_challenge.not_scheduled"
    """No question is scheduled for the requested UTC date — usually
    means today's question hasn't been published yet, or the editorial
    team has gaps in the schedule. Frontend should hide the daily card
    instead of showing an error toast."""

    DAILY_CHALLENGE_ALREADY_ATTEMPTED = "daily_challenge.already_attempted"
    """User already submitted a live attempt for the current UTC date.
    Frontend re-renders the post-submit state from the returned
    ``context.existing_attempt``."""

    DAILY_CHALLENGE_INVALID_OPTION = "daily_challenge.invalid_option"
    """The submitted ``selected_option_id`` does not belong to today's
    question. Either a stale frontend cache or a tampered request."""

    # ── Validation ──────────────────────────────────────────────────────
    VALIDATION_FAILED = "validation.failed"
    """Request body / params failed semantic validation beyond the
    Pydantic schema layer."""


def equip_error(
    code: ErrorCode,
    *,
    status_code: int,
    message: str,
    context: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    """Build an ``HTTPException`` with the typed-envelope ``detail``.

    Usage::

        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )

    The frontend extracts ``code`` for type-safe branching and renders
    ``message`` for the toast. ``context`` is the machine-readable
    payload for code that needs to render specifics (e.g. show the
    remaining attempt count).
    """
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code.value,
            "message": message,
            "context": context or {},
        },
        headers=headers,
    )


__all__ = ["ErrorCode", "equip_error"]
