"""Production hardening: the interactive docs UIs AND the raw OpenAPI
schema must all be disabled when the app boots in production.

``_IS_PRODUCTION`` is derived from the ``VERCEL`` / ``PRODUCTION`` env vars
at import time, so we reload ``app.main`` with the env toggled to assert the
FastAPI app is constructed with ``docs_url`` / ``redoc_url`` / ``openapi_url``
all ``None``. Leaving ``/openapi.json`` served while the UIs are hidden would
still leak the full route + model inventory to anyone — this test locks the
three together so a future refactor can't silently re-expose the schema.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize("env_var", ["PRODUCTION", "VERCEL"])
def test_docs_and_openapi_disabled_in_production(monkeypatch: pytest.MonkeyPatch, env_var: str) -> None:
    # Ensure neither flag is set from the outer environment, then set the one
    # under test so _IS_PRODUCTION evaluates True on reload.
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("PRODUCTION", raising=False)
    monkeypatch.setenv(env_var, "1")

    import app.main as main_module

    reloaded = importlib.reload(main_module)
    try:
        assert reloaded.app.docs_url is None
        assert reloaded.app.redoc_url is None
        assert reloaded.app.openapi_url is None
    finally:
        # Restore the module to its non-production form so the rest of the
        # suite (which imports ``app.main`` freely) sees the dev config.
        monkeypatch.delenv(env_var, raising=False)
        importlib.reload(reloaded)


def test_docs_and_openapi_enabled_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("PRODUCTION", raising=False)

    import app.main as main_module

    reloaded = importlib.reload(main_module)
    assert reloaded.app.docs_url == "/docs"
    assert reloaded.app.redoc_url == "/redoc"
    assert reloaded.app.openapi_url == "/openapi.json"
