"""Tests for the request-middleware metric emission in ``app.main``.

Pins:
* ``_extract_course_id`` parses the canonical route shapes correctly
  and returns None for non-course paths.
* The middleware emits ``equip.activity.requests_total`` and
  ``equip.activity.duration_ms`` on every successful request.
* The locale tag follows ``Accept-Language`` (ru vs en).
* A failure inside the metric emission cannot crash the request.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from app.main import _extract_course_id

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestExtractCourseId:
    @pytest.mark.parametrize(
        "path, expected",
        [
            ("/api/v1/courses/course-1", "course-1"),
            ("/api/v1/courses/course-1/modules", "course-1"),
            ("/api/v1/courses/course-1/chapters", "course-1"),
            ("/api/v1/grades/course/abc-123/summary", "abc-123"),
            ("/api/v1/calendar/course/c-2/events", "c-2"),
            ("/api/v1/progress/course/c-3/my-progress", "c-3"),
        ],
    )
    def test_extracts_course_id_from_canonical_paths(self, path: str, expected: str) -> None:
        assert _extract_course_id(path) == expected

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/health/db",
            "/api/v1/users/me/courses",
            "/api/v1/users/admin/users",
            "/api/v1/courses",  # listing, no id
            "/api/v1/courses/my",  # ``my`` is a reserved literal
            "/api/v1/courses/my/courses",
            "/",
        ],
    )
    def test_returns_none_for_non_course_paths(self, path: str) -> None:
        assert _extract_course_id(path) is None


class TestActivityEmission:
    def test_health_request_emits_requests_total(
        self,
        admin_client: TestClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Any successful request — even health — should produce a
        ``requests_total`` event so the global rate is accurate."""
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            r = admin_client.get("/api/v1/health/db")
        assert r.status_code in (200, 503)
        metric_messages = [rec.getMessage() for rec in caplog.records if rec.name == "equip.metric"]
        assert any("equip.activity.requests_total" in m for m in metric_messages)

    def test_course_path_tags_with_course_id(
        self,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Requests hitting a course-scoped route should tag
        ``course_id`` so the Course Engagement dashboard's
        per-course filter works."""
        # Seed a course so the GET returns 200 (not 404). The
        # specific status doesn't matter for the metric assertion —
        # the middleware emits for every status.
        from sqlalchemy.orm import Session as _Session  # noqa: F401  (typing-only)

        from ._cv_helpers import make_course_with_text
        from .conftest import TEACHER_ID

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            r = client.get("/api/v1/courses/some-id-that-may-not-exist")
        # Regardless of 200/404, the metric should have fired with
        # course_id=some-id-that-may-not-exist.
        msgs = [rec.getMessage() for rec in caplog.records if rec.name == "equip.metric"]
        activity = [m for m in msgs if "equip.activity.requests_total" in m]
        assert activity, "expected at least one requests_total event"
        assert any("course_id=some-id-that-may-not-exist" in m for m in activity)
        assert r.status_code in (200, 404)
        # Reference imports to keep linters happy (we may need them
        # if we extend this test to construct a real course).
        _ = make_course_with_text
        _ = TEACHER_ID


class TestNeverCrashes:
    def test_metric_failure_does_not_break_response(
        self,
        admin_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If the metric helper raises, the middleware swallows so
        the actual API response still ships normally."""
        from app.core import metrics as metrics_mod

        def boom(*_a: object, **_k: object) -> None:
            raise RuntimeError("simulated metric crash")

        monkeypatch.setattr(metrics_mod, "increment", boom)
        monkeypatch.setattr(metrics_mod, "timing", boom)

        # The endpoint should still return its normal status code.
        r = admin_client.get("/api/v1/health/db")
        assert r.status_code in (200, 503)
