"""Regression tests for security-sensitive migrations.

These tests parse migration SQL and assert that historically-dangerous
patterns stay out of the committed schema. They never touch a real
database — they only read the migration files. Treating the migration
text itself as a contract is the most reliable way to catch a security
regression in a single-developer project where nobody else reviews
RLS / trigger DDL.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def _read_latest_handle_new_user_definition() -> str:
    """Concatenate every migration that touches ``handle_new_user`` in
    timestamp order. The latest ``CREATE OR REPLACE FUNCTION`` wins
    semantically, so we return everything from the last redefinition to
    the end of the file."""
    matching = sorted(f for f in MIGRATIONS_DIR.glob("*_handle_new_user*.sql") if f.is_file())
    assert matching, "no handle_new_user migration files found"
    latest = matching[-1]
    return latest.read_text(encoding="utf-8")


def test_handle_new_user_never_trusts_raw_role_claim() -> None:
    """The signup trigger must NOT drop ``raw_user_meta_data->>'role'``
    straight into ``profiles.role``. That pattern lets an attacker pass
    ``role: 'admin'`` to ``supabase.auth.signUp`` and self-promote.

    The safe pattern whitelists the value with a CASE expression so
    only ``student`` (a non-privileged role) can land via signup; any
    other claim falls back to ``student``. Admin / teacher promotion
    is admin-only.
    """
    sql = _read_latest_handle_new_user_definition()
    # The unsafe pattern from the original trigger:
    #   COALESCE(NEW.raw_user_meta_data->>'role', 'student')
    # which directly assigns whatever the user passed.
    dangerous = re.search(
        r"COALESCE\s*\(\s*NEW\.raw_user_meta_data\s*->>\s*'role'",
        sql,
        re.IGNORECASE,
    )
    assert dangerous is None, (
        "handle_new_user must not COALESCE raw_user_meta_data->>'role' "
        "directly into profiles.role — that is the user-metadata "
        "privilege-escalation pattern."
    )


def test_handle_new_user_only_self_assigns_student() -> None:
    """Self-service signup may only land users at ``student``. Any
    other claim — including ``teacher``, ``pending_teacher`` (a
    deprecated role), and ``admin`` — must fall back to ``student``.
    Teacher promotion is admin-only via the role-change endpoint.
    """
    sql = _read_latest_handle_new_user_definition()
    # The safe whitelist should contain a 'student' THEN branch and
    # an ELSE 'student' fallback (or an equivalent shape). Verify both.
    student_branch = re.search(
        r"WHEN\s+claimed_role\s*=\s*'student'\s+THEN\s+'student'",
        sql,
        re.IGNORECASE,
    )
    else_student = re.search(
        r"ELSE\s+'student'",
        sql,
        re.IGNORECASE,
    )
    assert student_branch and else_student, (
        "handle_new_user must whitelist self-service signup to "
        "'student' only — every other branch should ELSE 'student'."
    )
    # And nothing else should be assignable. A teacher / pending_teacher
    # mention in a THEN clause means the gate is leaky.
    leaky = re.search(
        r"THEN\s+'(?:teacher|pending_teacher)'",
        sql,
        re.IGNORECASE,
    )
    assert leaky is None, (
        "handle_new_user must not let signup land at 'teacher' or "
        "'pending_teacher' — those roles are admin-assigned only."
    )


def test_handle_new_user_never_assigns_admin_from_metadata() -> None:
    """The trigger must never write ``'admin'`` to ``profiles.role``
    based on user-controlled input. Admin promotion goes through the
    explicit ``PUT /users/admin/users/{id}/role`` endpoint, never
    through signup metadata."""
    sql = _read_latest_handle_new_user_definition()
    # Search for any THEN 'admin' clause that pulls from user input.
    # A literal 'admin' string in the trigger body would be a smell;
    # the safe version doesn't reference 'admin' at all in the role
    # whitelist.
    suspicious = re.search(r"THEN\s+'admin'", sql, re.IGNORECASE)
    assert suspicious is None, (
        "handle_new_user contains a 'THEN \\'admin\\'' clause — admin must never be self-assignable via user metadata."
    )
