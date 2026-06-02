"""Unit tests for ``app.core.http.get_client_ip``.

``get_client_ip`` is the single source of truth for the real client IP
behind a reverse proxy. Rate limiting + audit logging both consume it,
and the trust gate (``_TRUSTED_PROXY``) decides whether we believe the
``X-Forwarded-For`` / ``X-Real-IP`` headers at all. Spoofing those
headers in a bare deploy used to let any client farm fresh rate-limit
buckets, so we pin the trust gate + fallback paths directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request

from app.core import http as core_http

if TYPE_CHECKING:
    import pytest


def _make_request(
    *,
    headers: dict[str, str] | None = None,
    client_host: str | None = "127.0.0.1",
) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


class TestTrustedProxy:
    """When a trusted reverse proxy is in front of us, X-Forwarded-For
    is the authoritative source of the real client IP — left-most entry
    of a comma-separated chain.
    """

    def test_xff_left_most_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)
        req = _make_request(
            headers={"x-forwarded-for": "203.0.113.5, 10.0.0.1, 10.0.0.2"},
        )
        assert core_http.get_client_ip(req) == "203.0.113.5"

    def test_xff_single_ip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)
        req = _make_request(headers={"x-forwarded-for": "203.0.113.5"})
        assert core_http.get_client_ip(req) == "203.0.113.5"

    def test_xff_trims_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)
        req = _make_request(
            headers={"x-forwarded-for": "  203.0.113.5  , 10.0.0.1"},
        )
        assert core_http.get_client_ip(req) == "203.0.113.5"

    def test_xff_empty_left_falls_back_to_xri(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An XFF that starts with a blank entry (``"" , 10.0.0.1, ...``)
        is malformed; we shouldn't return the empty string. The
        implementation skips the empty value and falls through to
        ``X-Real-IP`` when present.
        """
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)
        req = _make_request(
            headers={
                "x-forwarded-for": ", 10.0.0.1",
                "x-real-ip": "203.0.113.9",
            },
        )
        assert core_http.get_client_ip(req) == "203.0.113.9"

    def test_xri_when_no_xff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)
        req = _make_request(headers={"x-real-ip": "203.0.113.7"})
        assert core_http.get_client_ip(req) == "203.0.113.7"

    def test_xri_whitespace_is_trimmed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)
        req = _make_request(headers={"x-real-ip": "  203.0.113.7  "})
        assert core_http.get_client_ip(req) == "203.0.113.7"


class TestUntrustedProxy:
    """Without a trusted proxy signal we MUST ignore X-Forwarded-For /
    X-Real-IP — a client controlling the headers would otherwise spoof
    a fresh rate-limit bucket per request.
    """

    def test_xff_ignored_when_untrusted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", False)
        req = _make_request(
            headers={"x-forwarded-for": "203.0.113.5"},
            client_host="10.0.0.42",
        )
        assert core_http.get_client_ip(req) == "10.0.0.42"

    def test_xri_ignored_when_untrusted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", False)
        req = _make_request(
            headers={"x-real-ip": "203.0.113.7"},
            client_host="10.0.0.42",
        )
        assert core_http.get_client_ip(req) == "10.0.0.42"


class TestFallback:
    """Final fallback chain: ``request.client.host`` first, then the
    caller-supplied ``fallback`` argument (``"unknown"`` for rate
    limiter, ``None`` for audit logger).
    """

    def test_returns_client_host_when_no_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)
        req = _make_request(client_host="198.51.100.10")
        assert core_http.get_client_ip(req) == "198.51.100.10"

    def test_returns_fallback_when_client_missing_and_no_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)
        req = _make_request(client_host=None)
        assert core_http.get_client_ip(req, fallback="unknown") == "unknown"

    def test_returns_none_fallback_for_audit_logger(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Audit logger passes ``fallback=None`` so the DB column stays NULL."""
        monkeypatch.setattr(core_http, "_TRUSTED_PROXY", True)
        req = _make_request(client_host=None)
        assert core_http.get_client_ip(req, fallback=None) is None
