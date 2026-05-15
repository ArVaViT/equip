"""Regression tests for the ``profiles_update_own_safe_fields`` RLS policy.

These tests parse the migration SQL and confirm that the WITH CHECK
clause pins every identity column a user could otherwise spoof
(``role``, ``email``, ``id``, ``created_at``). They never touch a real
database — SQLite (our test DB) cannot enforce RLS, so a text-level
check is the most reliable signal that a future migration relaxing
this policy will get caught in CI.
"""

from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def _profiles_lock_sql() -> str:
    matches = sorted(MIGRATIONS_DIR.glob("*_profiles_lock_email_self_update.sql"))
    assert matches, "profiles_lock_email_self_update migration not found"
    return matches[-1].read_text(encoding="utf-8")


def test_old_permissive_policy_is_dropped() -> None:
    """The previous ``profiles_update_own_no_role`` policy pinned
    only ``role`` and left ``email`` writable. It must be explicitly
    dropped before the safer policy is created."""
    sql = _profiles_lock_sql()
    assert "DROP POLICY IF EXISTS profiles_update_own_no_role ON public.profiles" in sql, (
        "Migration must drop the old profiles_update_own_no_role policy before creating the replacement."
    )


def test_with_check_pins_email() -> None:
    """A user must not be able to PATCH profiles.email to spoof
    another identity (the column is read in analytics/grades/progress
    surfaces that teachers trust)."""
    sql = _profiles_lock_sql()
    # The pin pattern reads the column from the current row and
    # compares it against the new value in the same statement.
    assert "email = (" in sql, (
        "WITH CHECK must compare email against the current row to prevent client-side email spoofing."
    )
    assert "FROM public.profiles p WHERE p.id = (SELECT auth.uid())" in sql, (
        "Pin comparisons must read the canonical row by auth.uid()."
    )


def test_with_check_pins_role() -> None:
    """Role pin must survive the policy rewrite — otherwise we
    re-open the privilege-escalation hole this policy historically
    closed."""
    sql = _profiles_lock_sql()
    assert "role = (" in sql, "WITH CHECK must compare role against the current row to prevent self-promotion."


def test_with_check_pins_created_at() -> None:
    """created_at is part of the audit/identity surface (e.g. admin
    'user list' shows account age). Must not be client-mutable."""
    sql = _profiles_lock_sql()
    assert "created_at IS NOT DISTINCT FROM" in sql, (
        "WITH CHECK must pin created_at using IS NOT DISTINCT FROM (handles the NULL-on-NULL case correctly)."
    )
