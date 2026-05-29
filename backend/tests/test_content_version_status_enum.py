"""Regression tests for ``ContentVersionStatus``.

The enum mirrors the Postgres CHECK constraint on
``content_versions.status``. Drift between the two is a class of bug
that only surfaces at runtime as an IntegrityError on insert — these
tests catch it at PR time.
"""

from __future__ import annotations

from app.models.content_version import ContentVersion, ContentVersionStatus


def test_enum_values_mirror_the_check_constraint():
    """The CHECK constraint string in ``__table_args__`` enumerates
    the allowed values. The Python enum must match exactly — adding a
    new state in code without the migration to extend the CHECK would
    silently fail INSERT in prod."""
    expected = {"ok", "failed", "failed_permanent"}
    assert {member.value for member in ContentVersionStatus} == expected

    # And the CHECK constraint string itself uses the same set.
    check_strs = [
        str(constraint.sqltext)
        for constraint in ContentVersion.__table_args__
        if getattr(constraint, "name", None) == "content_versions_status_check"
    ]
    assert len(check_strs) == 1
    for value in expected:
        assert f"'{value}'" in check_strs[0], f"CHECK constraint missing {value!r}; sync the enum and the constraint."


def test_enum_is_str_subclass():
    """``StrEnum`` semantics — ``ContentVersionStatus.OK == 'ok'`` —
    is what lets every legacy ``Status.X == 'ok'`` comparison keep
    working without churn during the migration. Pin the contract."""
    assert ContentVersionStatus.OK == "ok"
    assert ContentVersionStatus.FAILED == "failed"
    assert ContentVersionStatus.FAILED_PERMANENT == "failed_permanent"
    assert isinstance(ContentVersionStatus.OK, str)
