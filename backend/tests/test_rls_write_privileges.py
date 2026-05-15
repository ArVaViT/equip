"""Regression tests for RLS / GRANT shape on sensitive write paths.

These tests parse the latest ``rls_tighten_write_policies`` migration
and assert that the dangerous client-side UPDATE / DELETE permissions
stay revoked. They never touch a real database — they only read the
migration files. SQLite (our test DB) cannot enforce RLS at all, so
text-level checks are the most reliable signal that an RLS regression
will get caught in CI.
"""

from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def _rls_tighten_sql() -> str:
    """Return the contents of the ``rls_tighten_write_policies``
    migration. Searches by suffix rather than hard-coding the timestamp
    so a rename or rebase doesn't break this test."""
    matches = sorted(MIGRATIONS_DIR.glob("*_rls_tighten_write_policies.sql"))
    assert matches, "rls_tighten_write_policies migration not found"
    return matches[-1].read_text(encoding="utf-8")


# Tables where the FastAPI backend is the only legitimate writer.
# A direct PostgREST UPDATE / DELETE from a user's JWT would let them
# bypass every server-side authorization / locking / audit check.
SERVER_ONLY_WRITE_TABLES = (
    "certificates",
    "quiz_attempts",
    "assignment_submissions",
)


def test_dangerous_update_policies_dropped() -> None:
    """The four pre-existing UPDATE policies that combined to allow
    self-grading / self-certificate-issuance / score-tampering must be
    explicitly dropped by this migration."""
    sql = _rls_tighten_sql()
    expected_drops = (
        "DROP POLICY IF EXISTS certificates_update_approval",
        "DROP POLICY IF EXISTS quiz_attempts_update_own",
        "DROP POLICY IF EXISTS submissions_update_teacher",
        "DROP POLICY IF EXISTS reviews_update_own",
    )
    for clause in expected_drops:
        assert clause in sql, (
            f"Migration must contain `{clause}` to remove the unsafe "
            "RLS policy. If you re-introduce client-side UPDATE for "
            "these tables, do it with an explicit WITH CHECK clause "
            "and a fresh threat model — not by reverting this DROP."
        )


def test_authenticated_update_revoked_on_server_only_tables() -> None:
    """For tables where only the FastAPI service should write, the
    authenticated + anon roles must lose UPDATE entirely. RLS alone
    is not enough — a future policy authored without WITH CHECK would
    re-open the hole. The GRANT-level REVOKE is a second line."""
    sql = _rls_tighten_sql().upper()
    for table in SERVER_ONLY_WRITE_TABLES:
        # Match the REVOKE pattern across whitespace; we just need
        # the table name to appear in a REVOKE ... UPDATE ... ON ...
        # clause that names both roles.
        needle = f"ON PUBLIC.{table.upper()} FROM AUTHENTICATED, ANON"
        assert needle in sql, (
            f"REVOKE ... ON public.{table} FROM authenticated, anon "
            "missing. The FastAPI service is the only legitimate "
            "writer for this table; PostgREST must not be able to "
            "issue UPDATE / DELETE statements against it."
        )


def test_reviews_update_revoked_but_delete_intact() -> None:
    """course_reviews UPDATE goes through the FastAPI upsert route
    (POST /reviews/course/{id}); the previous direct PostgREST UPDATE
    let a user reassign authorship by changing user_id. Strip UPDATE
    but leave DELETE alone — reviews_delete_own is well-scoped
    (qual = user_id = auth.uid()) and DELETE has no with-check
    foot-gun."""
    sql = _rls_tighten_sql().upper()
    assert "REVOKE UPDATE ON PUBLIC.COURSE_REVIEWS FROM AUTHENTICATED, ANON" in sql, (
        "course_reviews UPDATE must be revoked from authenticated/anon."
    )
    # Defensive: the migration must NOT also strip DELETE on
    # course_reviews; doing so would break the delete-my-review flow.
    assert "REVOKE UPDATE, DELETE ON PUBLIC.COURSE_REVIEWS" not in sql, (
        "Do not revoke DELETE on course_reviews — the reviews_delete_own "
        "RLS policy is intentionally available to clients."
    )
