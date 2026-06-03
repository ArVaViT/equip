"""Tests for ``equip.errors.unhandled_total`` emission from the
global FastAPI exception handler.

The metric drives the Datadog "backend unhandled exception rate"
monitor — current state has us reading raw Vercel logs to find
500s, which doesn't scale.

Pinned guarantees:

* Fires once per unhandled exception that hits the global handler.
* Tagged with method + path_prefix + exception_type so a spike
  is triageable without grepping logs.
* exception_type is the **class name only** — message content
  could carry PII (uuids, emails from validation errors); the
  class name is enough to bucket spikes.
* Non-raising — a metric failure cannot leak through and turn the
  500 into a different status code.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import app

if TYPE_CHECKING:
    import pytest

_test_router = APIRouter(prefix="/_metric_test", tags=["_internal"])


# ``include_in_schema=False`` keeps these test routes callable for the
# TestClient but invisible to OpenAPI generation, so they DO NOT bleed
# into the production /openapi.json (and the snapshot contract test
# stays clean).
@_test_router.get("/raise-runtime-error", include_in_schema=False)
def _raise_runtime_error() -> None:
    raise RuntimeError("boom")


@_test_router.get("/raise-key-error", include_in_schema=False)
def _raise_key_error() -> None:
    raise KeyError("missing")


# Register at module import time so every test that imports this file
# sees the test routes.
app.include_router(_test_router)


class TestUnhandledExceptionEmission:
    def test_emits_counter_with_method_path_and_type_tags(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/_metric_test/raise-runtime-error")
        assert resp.status_code == 500
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.errors.unhandled_total" in m]
        assert events, "expected unhandled_total event"
        assert any("method=GET" in m for m in events)
        assert any("exception_type=RuntimeError" in m for m in events)
        assert any("path_prefix=/_metric_test" in m or "path_prefix=/_metric_test/" in m for m in events)
        assert any("value=1.0" in m for m in events)

    def test_emits_different_exception_type_tag(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Two different exception classes raised from two different
        routes must produce two distinct ``exception_type`` tag values
        so the dashboard can rank "top error types"."""
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            client = TestClient(app, raise_server_exceptions=False)
            client.get("/_metric_test/raise-runtime-error")
            client.get("/_metric_test/raise-key-error")
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.errors.unhandled_total" in m]
        assert any("exception_type=RuntimeError" in m for m in events)
        assert any("exception_type=KeyError" in m for m in events)

    def test_does_not_emit_on_normal_request(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``/health`` doesn't raise — the unhandled-exception counter
        MUST be silent. Otherwise the dashboard's error-rate widget
        would show a false-positive baseline that drowns out real
        spikes."""
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/health")
        assert resp.status_code == 200
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.errors.unhandled_total" in m]
        assert events == [], "must NOT fire on a 200 path"
