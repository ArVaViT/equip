"""The new-format Supabase secret key is read under the name it goes by elsewhere."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings

if TYPE_CHECKING:
    import pytest


def test_supabase_secret_key_wins_over_the_legacy_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJ-legacy-disabled-2026-06")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_current")
    assert Settings(_env_file=None).SUPABASE_SERVICE_ROLE_KEY == "sb_secret_current"


def test_the_legacy_name_still_works_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sb_secret_under_old_name")
    assert Settings(_env_file=None).SUPABASE_SERVICE_ROLE_KEY == "sb_secret_under_old_name"
