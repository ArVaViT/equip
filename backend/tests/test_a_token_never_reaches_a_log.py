"""An invitation token must not be written to any log this process ships.

Found in Datadog on 2026-09-16: over one week the access line
``[INFO] api: GET /api/v1/invitations/token/<token> 200 12ms`` was indexed
71 times, and the 503 handler's ``Database error on GET <path>: <exc>``
carried the same token a second way, in SQLAlchemy's rendered
``[parameters: {'token_1': '<token>'}]``. A token is a bearer credential
for the address and the role it was sent with.

These tests go through the handlers ``setup_logging`` installs -- the
stdout stream Vercel drains and the Datadog intake handler -- rather than
through ``redact_secrets`` alone, because the defect was never a missing
regex. It was a log call that nobody had told about secrets, and the fix
is that no log call has to be told.
"""

from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.core import database as database_module
from app.core import logging as logging_module
from app.core.redact import REDACTED, redact_secrets
from app.services.invitation_service import _accept_url

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient

INVITATION_TOKEN = "fy-eLq3Zx9dS2mPwR7tKc1vB5nHj8uYgA4oLi6eQs0W"
ICAL_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJjMjY2YTI2NyIsInNjb3BlIjoiaWNhbCJ9."
    "TxuWUob9SdLjdqJ_FT9KuIaqELfhnIJ0oIx4qfVmKnI"
)


class Shipped:
    """What left the process: the stdout text and the Datadog payloads."""

    def __init__(self, stream: io.StringIO, payloads: list[dict[str, Any]]) -> None:
        self.stream = stream
        self.payloads = payloads

    def everything(self) -> str:
        return self.stream.getvalue() + "\n".join(json.dumps(p) for p in self.payloads)


@pytest.fixture
def shipped(monkeypatch: pytest.MonkeyPatch) -> Iterator[Shipped]:
    """The production logging setup, with both of its exits captured."""
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level

    payloads: list[dict[str, Any]] = []

    def fake_urlopen(request: Any, timeout: float) -> MagicMock:
        payloads.append(json.loads(request.data.decode("utf-8")))
        return MagicMock()

    monkeypatch.setenv("DD_API_KEY", "test-key")
    monkeypatch.setenv("DD_ENV", "test")
    monkeypatch.setattr(logging_module.urllib.request, "urlopen", fake_urlopen)
    logging_module.setup_logging()

    stream = io.StringIO()
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging_module.DatadogHTTPHandler):
            handler.setStream(stream)
    assert any(isinstance(h, logging_module.DatadogHTTPHandler) for h in root.handlers)
    try:
        yield Shipped(stream, payloads)
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


class TestTheAccessLine:
    def test_a_preview_by_path_is_logged_without_its_token(self, anon_client: TestClient, shipped: Shipped) -> None:
        response = anon_client.get(f"/api/v1/invitations/token/{INVITATION_TOKEN}")

        # The token is unknown, so this is the 404 -- the line is written
        # either way, and a probe with a guessed token is still a token.
        assert response.status_code == 404
        text = shipped.everything()
        assert "/api/v1/invitations/token/" in text, "the access line was not written at all"
        assert INVITATION_TOKEN not in text
        assert f"/api/v1/invitations/token/{REDACTED}" in text

    def test_a_preview_by_body_has_nothing_in_its_path(self, anon_client: TestClient, shipped: Shipped) -> None:
        anon_client.post("/api/v1/invitations/preview", json={"token": INVITATION_TOKEN})

        assert "POST /api/v1/invitations/preview 404" in shipped.everything()
        assert INVITATION_TOKEN not in shipped.everything()


class TestTheDatabaseErrorLine:
    def test_bound_parameters_do_not_reach_either_exit(self, shipped: Shipped) -> None:
        """The 503 handler logs ``str(exc)`` with ``exc_info``.

        An engine built without ``hide_parameters`` renders the bound
        values into both -- the message Vercel drains and the
        ``error.stack`` Datadog indexes. This one is built that way on
        purpose, as a stand-in for any engine that forgets.
        """
        exc = OperationalError(
            "SELECT invitations.id FROM invitations WHERE invitations.token = %(token_1)s",
            {"token_1": INVITATION_TOKEN},
            Exception("server closed the connection unexpectedly"),
        )
        assert INVITATION_TOKEN in str(exc), "precondition: the exception itself carries the token"

        try:
            raise exc
        except OperationalError:
            logging.getLogger("api").error(
                "Database error on %s %s: %s",
                "GET",
                f"/api/v1/invitations/token/{INVITATION_TOKEN}",
                exc,
                exc_info=True,
            )

        assert shipped.payloads, "nothing was shipped to Datadog"
        payload = shipped.payloads[-1]
        assert "server closed the connection" in payload["message"]
        assert "error.stack" in payload
        assert INVITATION_TOKEN not in payload["message"]
        assert INVITATION_TOKEN not in payload["error.stack"]
        assert INVITATION_TOKEN not in shipped.stream.getvalue()
        assert f"[parameters: {REDACTED}]" in payload["message"]


class TestTheEngine:
    def test_the_application_engine_hides_bound_parameters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_create_engine(url: str, **kwargs: Any) -> MagicMock:
            captured.update(kwargs)
            engine = MagicMock()
            engine.dialect.name = "sqlite"
            return engine

        monkeypatch.setattr(database_module, "_engine", None)
        monkeypatch.setattr(database_module, "_SessionLocal", None)
        monkeypatch.setattr(database_module, "create_engine", fake_create_engine)
        monkeypatch.setattr(database_module.settings, "DATABASE_URL", "sqlite:///:memory:")

        database_module._get_engine()

        assert captured.get("hide_parameters") is True


class TestWhatCountsAsASecret:
    @pytest.mark.parametrize(
        ("line", "secret"),
        [
            (f"GET /api/v1/invitations/token/{INVITATION_TOKEN} 200 12ms", INVITATION_TOKEN),
            (f"[GET] /api/v1/calendar/ical/feed?token={ICAL_JWT} status=200", ICAL_JWT),
            (f"https://equipbible.com/invite/accept?token={INVITATION_TOKEN}", INVITATION_TOKEN),
            (f"https://equipbible.com/invite/accept#token={INVITATION_TOKEN}", INVITATION_TOKEN),
            ("https://equipbible.com/auth/callback#access_token=abc.def&refresh_token=4mqdwo5i4klm", "4mqdwo5i4klm"),
            ("https://equipbible.com/auth/callback?code=9f1c2d3e-pkce", "9f1c2d3e-pkce"),
            (f"Authorization: Bearer {INVITATION_TOKEN}", INVITATION_TOKEN),
            (f"decoded {ICAL_JWT} and failed", ICAL_JWT),
            ("could not connect to postgresql://postgres.ref:s3cr3t-pw@host:6543/postgres", "s3cr3t-pw"),
            (
                "[SQL: SELECT 1 WHERE email = %(email_1)s]\n[parameters: {'email_1': 'a@b.c'}]\n"
                "(Background on this error at: https://sqlalche.me/e/20/e3q8)",
                "a@b.c",
            ),
        ],
    )
    def test_a_secret_is_removed(self, line: str, secret: str) -> None:
        redacted = redact_secrets(line)
        assert secret not in redacted
        assert REDACTED in redacted

    @pytest.mark.parametrize(
        "line",
        [
            # Printed on the certificate so a stranger can check it.
            "GET /api/v1/certificates/verify/EQ-2026-000123 200 8ms",
            "GET /api/v1/organizations/ucoat 200 5ms",
            "GET /api/v1/courses/7924a1cf-8a84-4369-91ee-1f293f0f23df 200 30ms",
            # Names that only end like a secret parameter.
            "https://equipbible.com/auth/callback#error=access_denied&error_code=otp_expired",
            "#expires_in=3600&token_type=bearer",
        ],
    )
    def test_a_public_identifier_is_left_alone(self, line: str) -> None:
        assert redact_secrets(line) == line


class TestTheLetter:
    def test_the_link_carries_its_token_in_the_fragment(self) -> None:
        """The frontend host's edge log records the path *and query* of every
        page request -- ``/invite/accept?token=<token>`` was there in full.
        A fragment is never sent to a server, so no server can log it.
        """
        url = _accept_url(INVITATION_TOKEN)

        assert url.endswith(f"/invite/accept#token={INVITATION_TOKEN}")
        assert "?" not in url
