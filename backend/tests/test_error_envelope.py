"""Regression tests for the typed error envelope.

These pin three invariants future contributors must not break:

1. ``equip_error`` produces an ``HTTPException`` whose ``detail`` is
   a dict with the documented shape (``code``, ``message``,
   ``context``).
2. The code-enum string values stay stable. A renamed enum entry is a
   breaking change for every client that switch-matches on the code;
   this test catches that at PR time.
3. ``context`` defaults to an empty dict, never ``None`` — the
   frontend can always read ``context.<field>`` without a null check.
"""

from __future__ import annotations

from app.core.errors import ErrorCode, equip_error


def test_equip_error_returns_structured_detail():
    exc = equip_error(
        ErrorCode.RESOURCE_NOT_FOUND,
        status_code=404,
        message="Course 'x' not found",
        context={"resource_type": "course", "resource_id": "x"},
    )
    assert exc.status_code == 404
    assert exc.detail == {
        "code": "resource.not_found",
        "message": "Course 'x' not found",
        "context": {"resource_type": "course", "resource_id": "x"},
    }


def test_context_defaults_to_empty_dict_not_none():
    exc = equip_error(
        ErrorCode.AUTH_REQUIRED,
        status_code=401,
        message="Sign in to continue",
    )
    # The frontend extracts ``context`` and reads fields off it; a
    # ``None`` here would force every caller into a null check.
    assert exc.detail["context"] == {}


def test_enum_values_are_stable_strings():
    """Renaming a member breaks every consumer that switch-matches on
    the value. Pin the current set so a rename surfaces in code
    review."""
    expected = {
        "auth.required",
        "auth.forbidden",
        "account.deactivated",
        "resource.not_found",
        "course.not_published",
        "course.already_enrolled",
        "course.enrolment_closed",
        "translation.disabled",
        "translation.worker_unauthorized",
        "translation.worker_unconfigured",
        "quiz.not_open",
        "quiz.attempts_exhausted",
        "quiz.not_translated",
        "quiz.question_already_answered",
        "quiz.has_attempts",
        "daily_challenge.not_scheduled",
        "daily_challenge.not_translated",
        "daily_challenge.already_attempted",
        "daily_challenge.invalid_option",
        "daily_challenge.archive_date_not_allowed",
        "invitation.not_found",
        "invitation.expired",
        "invitation.already_used",
        "invitation.email_mismatch",
        "validation.failed",
        "legal.document_changed",
    }
    assert {member.value for member in ErrorCode} == expected


def test_equip_error_headers_passthrough():
    """``headers=`` lands on the raised HTTPException unchanged so a
    consumer that needs ``WWW-Authenticate`` / ``Retry-After`` can
    still set them alongside the code."""
    exc = equip_error(
        ErrorCode.QUIZ_ATTEMPTS_EXHAUSTED,
        status_code=429,
        message="Try again later",
        context={"retry_after_seconds": 60},
        headers={"Retry-After": "60"},
    )
    assert exc.headers == {"Retry-After": "60"}
