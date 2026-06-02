"""Unit tests for the internal helpers in ``app.services.verse_of_the_day``.

The main test file (``test_verse_of_the_day.py``) covers the
end-to-end happy path and the route. This file pins three internal
seams that the e2e tests skip because they monkeypatch
``_fetch_passage`` away:

* ``_fetch_passage`` itself — exercises the YouVersion HTTP shape, the
  404→``VerseNotInBible`` mapping, the non-200→``VerseOfTheDayUnavailable``
  mapping, the HTML strip, and the malformed-payload guard.
* ``_remap_ref_for_locale`` — pins the Psalm chapter remap for the
  Septuagint locales, including the ``ValueError`` / ``IndexError``
  guard for catalog entries that don't parse as ``BOOK.CH.VERSE``.
* ``get_verse_of_the_day`` HTTP-error path — when ``_fetch_passage``
  raises ``httpx.HTTPError`` the walk does NOT keep going; it
  surfaces ``VerseOfTheDayUnavailable`` so the route 404s and the
  card hides instead of looping through stale catalog entries.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from app.services import verse_of_the_day as svc

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


class _FakeResp:
    def __init__(self, *, status_code: int, json_body: dict | None = None) -> None:
        self.status_code = status_code
        self._body = json_body or {}

    def json(self) -> dict:
        return self._body


class _FakeClient:
    def __init__(self, *, response: _FakeResp | Exception) -> None:
        self._response = response
        self.last_url: str | None = None
        self.last_headers: dict | None = None

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def get(self, url: str, *, headers: dict) -> _FakeResp:
        self.last_url = url
        self.last_headers = headers
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _install_client(monkeypatch: pytest.MonkeyPatch, response: _FakeResp | Exception) -> _FakeClient:
    fake = _FakeClient(response=response)

    def factory(*_a: object, **_k: object) -> _FakeClient:
        return fake

    monkeypatch.setattr(svc.httpx, "Client", factory)
    return fake


@pytest.fixture(autouse=True)
def _reset_cache() -> Generator[None, None, None]:
    svc._reset_cache_for_tests()
    yield
    svc._reset_cache_for_tests()


class TestRemapRefForLocale:
    """The Septuagint/Masoretic chapter remap. Locale-gated; English
    catalog refs pass through unchanged for ``en``."""

    def test_english_locale_passes_ref_unchanged(self) -> None:
        assert svc._remap_ref_for_locale("PSA.23.1", "en") == "PSA.23.1"

    def test_non_psalm_ref_passes_unchanged_for_russian(self) -> None:
        """Only ``PSA.*`` refs get remapped; gospels and epistles use the
        same numbering across NRT and BSB."""
        assert svc._remap_ref_for_locale("JHN.3.16", "ru") == "JHN.3.16"
        assert svc._remap_ref_for_locale("ROM.8.28", "ru") == "ROM.8.28"

    def test_simple_offset_range_decrements_chapter(self) -> None:
        """Hebrew 11-113 maps to Septuagint 10-112 (single -1 offset).
        117-146 also remaps -1. Pin both."""
        assert svc._remap_ref_for_locale("PSA.23.1", "ru") == "PSA.22.1"
        assert svc._remap_ref_for_locale("PSA.100.1", "ru") == "PSA.99.1"
        assert svc._remap_ref_for_locale("PSA.119.105", "ru") == "PSA.118.105"
        assert svc._remap_ref_for_locale("PSA.139.14", "ru") == "PSA.138.14"

    def test_identical_chapters_outside_offset_range(self) -> None:
        """Hebrew 1-8 + 148-150 share Septuagint numbering — pass through."""
        assert svc._remap_ref_for_locale("PSA.1.1", "ru") == "PSA.1.1"
        assert svc._remap_ref_for_locale("PSA.8.1", "ru") == "PSA.8.1"
        # 148-150 has no entry in the current catalog so we just sanity
        # check the function doesn't crash on these.
        assert svc._remap_ref_for_locale("PSA.150.1", "ru") == "PSA.150.1"

    def test_complex_boundary_returns_none(self) -> None:
        """Hebrew 9, 10, 114, 115, 116, 147 sit at split/combine
        boundaries — no clean per-verse remap. ``None`` signals the
        caller to walk to the next ref."""
        assert svc._remap_ref_for_locale("PSA.9.10", "ru") is None
        assert svc._remap_ref_for_locale("PSA.10.1", "ru") is None
        assert svc._remap_ref_for_locale("PSA.114.1", "ru") is None
        assert svc._remap_ref_for_locale("PSA.115.1", "ru") is None
        assert svc._remap_ref_for_locale("PSA.116.1", "ru") is None
        assert svc._remap_ref_for_locale("PSA.147.1", "ru") is None

    def test_malformed_ref_falls_through_unchanged(self) -> None:
        """A catalog entry that doesn't parse as ``BOOK.CH.VERSE``
        (defensive guard for a future catalog typo) returns the ref
        as-is rather than blowing up the whole walk."""
        # Missing verse part — split on '.' twice returns only 2 tokens
        # → IndexError, caught and ref returned as-is.
        assert svc._remap_ref_for_locale("PSA.23", "ru") == "PSA.23"
        # Non-integer chapter → ValueError, same defence.
        assert svc._remap_ref_for_locale("PSA.X.1", "ru") == "PSA.X.1"


class TestFetchPassage:
    """The single httpx seam. End-to-end tests monkeypatch this away;
    here we pin its actual behaviour."""

    def test_happy_path_strips_html_and_returns_tuple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = {
            "reference": "John 3:16",
            "content": "<p>For <span>God</span> so loved...</p>",
        }
        _install_client(monkeypatch, _FakeResp(status_code=200, json_body=body))
        ref, text = svc._fetch_passage("KEY", 3034, "JHN.3.16")
        assert ref == "John 3:16"
        assert text == "For God so loved..."

    def test_url_carries_bible_id_and_reference(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _install_client(
            monkeypatch,
            _FakeResp(status_code=200, json_body={"reference": "x", "content": "y"}),
        )
        svc._fetch_passage("APIKEY", 3034, "JHN.3.16")
        assert fake.last_url is not None
        assert "/bibles/3034/passages/JHN.3.16" in fake.last_url
        assert fake.last_headers == {"X-YVP-App-Key": "APIKEY"}

    def test_404_maps_to_verse_not_in_bible(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """404 means the BIBLE doesn't carry this reference (Psalm
        versification mismatch, apocrypha gap). The caller walks
        forward — it must NOT raise VerseOfTheDayUnavailable for this."""
        _install_client(monkeypatch, _FakeResp(status_code=404))
        with pytest.raises(svc.VerseNotInBible):
            svc._fetch_passage("KEY", 3034, "MISSING.1.1")

    def test_500_maps_to_vot_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-200 non-404 is a transient outage. The caller must
        surface VerseOfTheDayUnavailable so the route returns 404 and
        the frontend hides the card."""
        _install_client(monkeypatch, _FakeResp(status_code=500))
        with pytest.raises(svc.VerseOfTheDayUnavailable):
            svc._fetch_passage("KEY", 3034, "JHN.3.16")

    def test_malformed_payload_missing_reference_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A 200 with empty or absent ``reference`` / ``content`` is
        treated as an outage rather than a content gap — silently
        returning empty strings would render an empty card."""
        _install_client(
            monkeypatch,
            _FakeResp(status_code=200, json_body={"content": "text"}),
        )
        with pytest.raises(svc.VerseOfTheDayUnavailable):
            svc._fetch_passage("KEY", 3034, "JHN.3.16")

    def test_malformed_payload_missing_content_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_client(
            monkeypatch,
            _FakeResp(status_code=200, json_body={"reference": "John 3:16"}),
        )
        with pytest.raises(svc.VerseOfTheDayUnavailable):
            svc._fetch_passage("KEY", 3034, "JHN.3.16")


class TestStripHtml:
    """The collapse-to-prose helper — pure regex, easy unit-test."""

    def test_strips_tag_wrappers(self) -> None:
        assert svc._strip_html("<p>hi</p>") == "hi"

    def test_collapses_whitespace(self) -> None:
        assert svc._strip_html("<p>line\n\nbreaks   inside</p>") == "line breaks inside"

    def test_passes_plain_text_through(self) -> None:
        assert svc._strip_html("no markup here") == "no markup here"


class TestGetVerseOfTheDayHttpErrorPath:
    """When the YouVersion request fails at the transport layer
    (``httpx.HTTPError``) the walk MUST NOT keep going — that's a
    "we can't talk to YouVersion" condition, not a "this ref missing
    in the bible" condition. Returning the next catalog ref would
    serve stale content silently."""

    def test_httpx_transport_error_aborts_walk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")
        call_count = {"n": 0}

        def fail(*_a: object, **_k: object) -> Any:
            call_count["n"] += 1
            raise httpx.ConnectError("upstream down")

        monkeypatch.setattr(svc, "_fetch_passage", fail)

        with pytest.raises(svc.VerseOfTheDayUnavailable):
            svc.get_verse_of_the_day("en", today=dt.date(2026, 5, 14))

        # _fetch_passage called exactly once — walk did NOT continue
        # after the transport error.
        assert call_count["n"] == 1


class TestGetVerseOfTheDayWalkExhausted:
    """If every ref in the bounded walk is missing from the bible, we
    surface ``VerseOfTheDayUnavailable`` with the last seen
    ``VerseNotInBible`` attached so the runbook has a starting point."""

    def test_walk_cap_exceeded_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")

        def always_missing(*_a: object, **_k: object) -> Any:
            raise svc.VerseNotInBible("ref missing")

        monkeypatch.setattr(svc, "_fetch_passage", always_missing)

        with pytest.raises(svc.VerseOfTheDayUnavailable) as exc:
            svc.get_verse_of_the_day("en", today=dt.date(2026, 5, 14))
        # The last-seen VerseNotInBible message should be referenced.
        assert "ref missing" in str(exc.value)


def _stub_fetch_for_walk(
    expected_calls: list[tuple[int, str]],
) -> Callable[..., tuple[str, str]]:
    """Returns a stub that asserts ``_fetch_passage`` was invoked with
    exactly the references in ``expected_calls`` (used to verify the
    walk advances by 1 each step) before succeeding."""
    call_idx = {"i": 0}

    def stub(_key: str, bible_id: int, ref: str) -> tuple[str, str]:
        i = call_idx["i"]
        assert i < len(expected_calls), f"Unexpected extra call: ({bible_id}, {ref})"
        expected_bible, expected_ref = expected_calls[i]
        assert bible_id == expected_bible
        assert ref == expected_ref
        call_idx["i"] += 1
        if i == len(expected_calls) - 1:
            return ("Ref", "Text")
        raise svc.VerseNotInBible("walk forward")

    return stub
