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

    ACCOUNT_DEACTIVATED = "account.deactivated"
    """The account was soft-deleted (deactivated) by an admin. The token may
    still be valid, but every authenticated surface is blocked until restored.
    Distinct from AUTH_FORBIDDEN so the client can sign the user out cleanly
    rather than showing a generic permission error."""

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

    DAILY_CHALLENGE_NOT_TRANSLATED = "daily_challenge.not_translated"
    """A question is scheduled, but not in the language this reader
    asked for. The platform serves no substitute language, so there is
    nothing to render — the alternative is a card with an empty question
    and blank buttons. Frontend shows "not available in your language
    yet" rather than hiding the card silently, because the reader can
    see other people have a challenge today."""

    DAILY_CHALLENGE_ALREADY_ATTEMPTED = "daily_challenge.already_attempted"
    """User already submitted a live attempt for the current UTC date.
    Frontend re-renders the post-submit state from the returned
    ``context.existing_attempt``."""

    DAILY_CHALLENGE_INVALID_OPTION = "daily_challenge.invalid_option"
    """The submitted ``selected_option_id`` does not belong to today's
    question. Either a stale frontend cache or a tampered request."""

    DAILY_CHALLENGE_ARCHIVE_DATE_NOT_ALLOWED = "daily_challenge.archive_date_not_allowed"
    """Archive endpoints refuse today's date or any future date —
    those are owned by the live ``/today`` surface. Frontend should
    redirect the user back to today's card."""

    # ── Invitations ──────────────────────────────────────────────────────
    INVITATION_NOT_FOUND = "invitation.not_found"
    """No invitation matches the given token."""

    INVITATION_EXPIRED = "invitation.expired"
    """The invitation's ``expires_at`` has passed. Still ``status='pending'``
    in the DB -- expiry is computed at read/accept time, not a stored
    transition."""

    INVITATION_ALREADY_USED = "invitation.already_used"
    """The invitation's ``status`` is no longer ``pending`` (already
    accepted, or revoked by an admin re-inviting with a fresh row)."""

    INVITATION_EMAIL_MISMATCH = "invitation.email_mismatch"
    """The authenticated caller's email does not match the email the
    invitation was issued to."""

    # ── Validation ──────────────────────────────────────────────────────
    VALIDATION_FAILED = "validation.failed"
    """Request body / params failed semantic validation beyond the
    Pydantic schema layer."""

    LEGAL_DOCUMENT_CHANGED = "legal.document_changed"
    """The client tried to accept a version of a policy we no longer serve —
    a page left open across a deploy. Recording it would produce a consent row
    pointing at a text nobody can now produce, which is the one thing the
    acceptance record exists to prevent. The frontend reloads the document and
    asks again rather than surfacing an error."""


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
