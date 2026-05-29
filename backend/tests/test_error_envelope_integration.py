"""End-to-end tests that the typed error envelope reaches the client.

Phase 5ay shipped the foundation. Phase 5az migrated the catalog
routes as the first demonstration. These tests assert the wire
format: a 404 on ``/courses/{id}`` returns the structured
``{code, message, context}`` body, not the legacy string detail.

A frontend that switch-matches on ``code`` can rely on this
contract; a frontend that toasts ``message`` keeps working too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_get_course_returns_structured_404(client: TestClient):
    resp = client.get("/api/v1/courses/this-id-does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    detail = body["detail"]
    assert detail["code"] == "resource.not_found"
    assert "not found" in detail["message"].lower()
    assert detail["context"] == {
        "resource_type": "course",
        "resource_id": "this-id-does-not-exist",
    }


def test_get_module_returns_structured_404(client: TestClient):
    resp = client.get("/api/v1/courses/missing/modules/also-missing")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    # The route checks course existence first, so the response should
    # describe the course as the missing resource.
    assert detail["code"] == "resource.not_found"
    assert detail["context"]["resource_id"] == "missing"
