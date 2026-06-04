"""Production hardening: the interactive docs UIs AND the raw OpenAPI
schema must all be disabled when the app boots in production.

We test the pure ``docs_url_config`` helper rather than reloading
``app.main`` — a module reload re-runs ``add_middleware`` /
``include_router`` and corrupts global app state for unrelated tests
(rate-limit buckets, the shared TestClient app). The helper is exactly
what the ``FastAPI(...)`` constructor is fed, so this still locks the
real behaviour: leaving ``/openapi.json`` served while the UIs are off
would hand out the full route + model inventory.
"""

from __future__ import annotations

from app.main import docs_url_config


def test_docs_and_openapi_disabled_in_production() -> None:
    cfg = docs_url_config(is_production=True)
    assert cfg["docs_url"] is None
    assert cfg["redoc_url"] is None
    assert cfg["openapi_url"] is None


def test_docs_and_openapi_enabled_outside_production() -> None:
    cfg = docs_url_config(is_production=False)
    assert cfg["docs_url"] == "/docs"
    assert cfg["redoc_url"] == "/redoc"
    assert cfg["openapi_url"] == "/openapi.json"
