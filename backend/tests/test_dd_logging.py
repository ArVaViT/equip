"""Tests for the Datadog HTTP logging handler in app.core.logging."""

import json
import logging
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.core.logging import DatadogHTTPHandler, setup_logging


def _make_handler() -> DatadogHTTPHandler:
    return DatadogHTTPHandler(
        api_key="test-key",
        site="us5.datadoghq.com",
        service="equip-backend",
        env="production",
        version="abc1234",
        vercel_region="iad1",
    )


def test_endpoint_uses_site_param() -> None:
    h = _make_handler()
    assert h.endpoint == "https://http-intake.logs.us5.datadoghq.com/api/v2/logs"


def test_emit_posts_to_intake_with_api_key() -> None:
    h = _make_handler()
    h.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="api",
        level=logging.WARNING,
        pathname="x.py",
        lineno=1,
        msg="boom",
        args=(),
        exc_info=None,
    )
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value = MagicMock()
        h.emit(record)
    assert urlopen.called, "expected urlopen to be called once"
    req = urlopen.call_args.args[0]
    assert req.headers["Dd-api-key"] == "test-key"
    body = json.loads(req.data.decode("utf-8"))
    assert body["service"] == "equip-backend"
    assert body["status"] == "warning"
    assert "env:production" in body["ddtags"]
    assert "version:abc1234" in body["ddtags"]
    assert "vercel_region:iad1" in body["ddtags"]
    assert body["hostname"] == "vercel-iad1"
    assert body["message"] == "boom"


def test_emit_includes_vercel_request_id_when_set() -> None:
    from app.core.logging import vercel_request_id

    h = _make_handler()
    h.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="api",
        level=logging.WARNING,
        pathname="x.py",
        lineno=1,
        msg="boom",
        args=(),
        exc_info=None,
    )
    token = vercel_request_id.set("syd1::abc123")
    try:
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = MagicMock()
            h.emit(record)
        body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        assert body["vercel.request_id"] == "syd1::abc123"
    finally:
        vercel_request_id.reset(token)


def test_emit_omits_vercel_request_id_when_unset() -> None:
    h = _make_handler()
    h.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="api",
        level=logging.WARNING,
        pathname="x.py",
        lineno=1,
        msg="boom",
        args=(),
        exc_info=None,
    )
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value = MagicMock()
        h.emit(record)
    body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert "vercel.request_id" not in body


def test_emit_swallows_network_errors() -> None:
    h = _make_handler()
    h.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="api",
        level=logging.ERROR,
        pathname="x.py",
        lineno=1,
        msg="db down",
        args=(),
        exc_info=None,
    )
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
        # Must not raise — losing a log record is preferable to crashing the request
        h.emit(record)


def test_emit_includes_exc_info_when_present() -> None:
    h = _make_handler()
    h.setFormatter(logging.Formatter("%(message)s"))
    try:
        raise ValueError("kaboom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="api",
            level=logging.ERROR,
            pathname="x.py",
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value = MagicMock()
        h.emit(record)
    body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert body["error.kind"] == "ValueError"
    assert "ValueError: kaboom" in body["error.stack"]


def test_setup_logging_skips_dd_handler_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DD_API_KEY", raising=False)
    setup_logging()
    root = logging.getLogger()
    assert not any(isinstance(h, DatadogHTTPHandler) for h in root.handlers)


def test_setup_logging_installs_dd_handler_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DD_API_KEY", "x")
    monkeypatch.setenv("DD_SITE", "us5.datadoghq.com")
    setup_logging()
    root = logging.getLogger()
    dd_handlers = [h for h in root.handlers if isinstance(h, DatadogHTTPHandler)]
    assert len(dd_handlers) == 1
    assert dd_handlers[0].level == logging.WARNING
