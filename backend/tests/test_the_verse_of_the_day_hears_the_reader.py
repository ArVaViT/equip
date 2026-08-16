"""Every reader-facing route on this platform reads ``Accept-Language``.

This one did not. It took a ``?locale=`` query parameter, defaulted it
to English, and ignored the header entirely — so a Russian reader who
called it the way they call everything else got an English verse, with
no error and nothing to notice.

The web app happens to send the parameter (its language is a stored
preference, not whatever the browser announces), which is why this
survived: the app was right and the API was wrong, and only a client
that trusted the platform's own convention found out.

The explicit parameter still wins. The header is what answers when
nobody said otherwise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from app.services.verse_of_the_day import VerseOfTheDay

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def _verse(locale: str) -> VerseOfTheDay:
    return VerseOfTheDay(
        reference="John 3:16",
        text=f"text-in-{locale}",
        version="TEST",
        locale=locale,  # type: ignore[arg-type]
        date="2026-08-16",
    )


class TestTheHeaderIsHeard:
    @pytest.mark.parametrize("locale", ["ru", "de", "uk", "en"])
    def test_the_reader_gets_their_own_language(self, client: TestClient, locale: str):
        with patch("app.api.v1.verse_of_the_day.get_verse_of_the_day", side_effect=lambda code: _verse(code)) as call:
            resp = client.get("/api/v1/verse-of-the-day", headers={"Accept-Language": locale})

        assert resp.status_code == 200
        assert call.call_args.args[0] == locale
        assert resp.json()["locale"] == locale

    def test_a_regional_variant_resolves(self, client: TestClient):
        with patch("app.api.v1.verse_of_the_day.get_verse_of_the_day", side_effect=lambda code: _verse(code)) as call:
            client.get("/api/v1/verse-of-the-day", headers={"Accept-Language": "de-AT"})

        assert call.call_args.args[0] == "de"

    def test_the_explicit_parameter_still_wins(self, client: TestClient):
        # The web app sends it, because a person's language here is a
        # stored preference rather than a browser setting.
        with patch("app.api.v1.verse_of_the_day.get_verse_of_the_day", side_effect=lambda code: _verse(code)) as call:
            client.get("/api/v1/verse-of-the-day?locale=uk", headers={"Accept-Language": "de"})

        assert call.call_args.args[0] == "uk"

    def test_nobody_said_anything_gets_english(self, client: TestClient):
        with patch("app.api.v1.verse_of_the_day.get_verse_of_the_day", side_effect=lambda code: _verse(code)) as call:
            client.get("/api/v1/verse-of-the-day")

        assert call.call_args.args[0] == "en"

    def test_the_response_varies_on_the_header(self, client: TestClient):
        # Without this a CDN would serve one language's verse to everyone.
        with patch("app.api.v1.verse_of_the_day.get_verse_of_the_day", side_effect=lambda code: _verse(code)):
            resp = client.get("/api/v1/verse-of-the-day", headers={"Accept-Language": "ru"})

        assert "Accept-Language" in resp.headers.get("Vary", "")
