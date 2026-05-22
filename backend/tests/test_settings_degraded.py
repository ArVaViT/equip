"""Boot-time tolerance for partially-configured environments.

The backend deploys to multiple Vercel environments (production, preview,
development). Until 2026-05 only Production had the SUPABASE_*, DATABASE_URL,
and JWT_SECRET_KEY env vars set, so every preview deploy crashed during
``Settings()`` import — converting every favicon scrape and root probe on a
preview URL into a 500 with a full Pydantic ValidationError stack trace.

These tests pin the contract that Settings now *boots* even with critical
fields missing, surfaces the missing names via ``runtime_ready_errors()``,
and lets the app process serve static surfaces (/health, /favicon.*) while
auth-requiring routes degrade to a clean 401 via the security layer.
"""

from __future__ import annotations

from app.core.config import Settings


def _clear_settings_env(monkeypatch) -> None:
    """Strip every Settings field from the environment for the duration of
    the test. ``_env_file=None`` then prevents ``.env`` from re-populating
    them on construction, so what's left is exactly what the field defaults
    would produce on a fresh worker."""
    for var in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_KEY",
        "SUPABASE_JWT_SECRET",
        "DATABASE_URL",
        "POSTGRES_URL",
        "POSTGRES_PRISMA_URL",
        "JWT_SECRET_KEY",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)


def test_settings_boots_with_no_env(monkeypatch):
    """All critical fields missing must NOT raise — that was the original
    crash and is the whole reason this graceful-degradation path exists."""
    _clear_settings_env(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.SUPABASE_URL is None
    assert settings.DATABASE_URL is None
    assert settings.JWT_SECRET_KEY is None


def test_runtime_ready_errors_lists_each_missing_field(monkeypatch):
    """The startup warning in app.main names every missing field so an
    operator opening the Vercel log sees the full punch list in one line,
    not three sequential boots until they fix each one."""
    _clear_settings_env(monkeypatch)
    settings = Settings(_env_file=None)
    missing = settings.runtime_ready_errors()
    assert set(missing) == {"DATABASE_URL", "JWT_SECRET_KEY", "SUPABASE_URL"}


def test_runtime_ready_errors_empty_when_all_set(monkeypatch):
    """Fully-configured production should report zero missing fields — this
    is the assertion that catches a future field promoted to ``required``
    but never added to ``runtime_ready_errors()``."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x@h/d")
    monkeypatch.setenv("JWT_SECRET_KEY", "s")
    settings = Settings(_env_file=None)
    assert settings.runtime_ready_errors() == []


def test_runtime_ready_errors_reports_only_missing(monkeypatch):
    """Partial config (e.g. someone set DATABASE_URL but forgot the rest)
    must report only the still-missing fields, so the warning narrows as
    the operator fills them in."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x@h/d")
    settings = Settings(_env_file=None)
    assert set(settings.runtime_ready_errors()) == {"JWT_SECRET_KEY", "SUPABASE_URL"}


def test_decode_access_token_returns_none_when_no_jwt_secret_and_no_supabase(monkeypatch):
    """The old code asserted JWT_SECRET_KEY was non-None and crashed with
    AssertionError on first auth attempt in a degraded environment. The
    cleaner contract: missing config → return ``None``, which the caller
    turns into a 401. No stack traces, no 500s — just an honest 401."""
    from app.core import security as security_module

    monkeypatch.setattr(security_module.settings, "JWT_SECRET_KEY", None)
    monkeypatch.setattr(security_module.settings, "SUPABASE_URL", None)
    assert security_module.decode_access_token("any-token") is None
