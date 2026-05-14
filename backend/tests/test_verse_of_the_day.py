"""Unit + route tests for the verse-of-the-day feature.

We never hit YouVersion in tests — both the service-level cases and the
route case monkeypatch the single ``_fetch_passage`` seam in the service
module. CI does not have ``YOUVERSION_API_KEY`` set; the
``apikey_missing`` route case relies on that.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import verse_of_the_day as svc


@pytest.fixture(autouse=True)
def _reset_cache():
    svc._reset_cache_for_tests()
    yield
    svc._reset_cache_for_tests()


def _stub_fetch(reference: str = "John 3:16", text: str = "For God so loved the world."):
    """Build a monkeypatch target that mimics YouVersion's success path."""

    def _impl(api_key: str, bible_id: int, ref: str) -> tuple[str, str]:
        return reference, text

    return _impl


def test_pick_reference_deterministic_for_same_date():
    today = dt.date(2026, 5, 14)
    assert svc._pick_reference(today) == svc._pick_reference(today)


def test_pick_reference_varies_by_date():
    # Adjacent days should yield different references for a catalog with
    # > 1 entry — guards against an off-by-one indexing regression.
    a = svc._pick_reference(dt.date(2026, 5, 14))
    b = svc._pick_reference(dt.date(2026, 5, 15))
    assert a != b


def test_get_verse_of_the_day_returns_localized_payload(monkeypatch):
    monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")
    monkeypatch.setattr(
        svc,
        "_fetch_passage",
        _stub_fetch("От Иоанна 3:16", "Ведь Бог так полюбил этот мир..."),
    )
    verse = svc.get_verse_of_the_day("ru", today=dt.date(2026, 5, 14))
    assert verse.locale == "ru"
    assert verse.version == "NRT"
    assert verse.reference == "От Иоанна 3:16"
    assert "полюбил" in verse.text
    assert verse.date == "2026-05-14"


def test_get_verse_of_the_day_caches_within_day(monkeypatch):
    """Two calls on the same UTC date hit the upstream API exactly once."""
    monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")
    calls = {"n": 0}

    def _counting(api_key: str, bible_id: int, ref: str) -> tuple[str, str]:
        calls["n"] += 1
        return "John 3:16", "For God so loved the world..."

    monkeypatch.setattr(svc, "_fetch_passage", _counting)
    today = dt.date(2026, 5, 14)
    svc.get_verse_of_the_day("en", today=today)
    svc.get_verse_of_the_day("en", today=today)
    assert calls["n"] == 1


def test_get_verse_of_the_day_evicts_stale_dates(monkeypatch):
    """Yesterday's cache entry must be dropped when today's lands so the
    cache never grows unbounded across long-lived warm instances."""
    monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")
    monkeypatch.setattr(svc, "_fetch_passage", _stub_fetch())
    svc.get_verse_of_the_day("en", today=dt.date(2026, 5, 13))
    svc.get_verse_of_the_day("en", today=dt.date(2026, 5, 14))
    keys = list(svc._CACHE.keys())
    assert all(k[0] == "2026-05-14" for k in keys)


def test_get_verse_of_the_day_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("YOUVERSION_API_KEY", raising=False)
    with pytest.raises(svc.VerseOfTheDayUnavailable):
        svc.get_verse_of_the_day("en")


def test_get_verse_of_the_day_raises_for_unsupported_locale(monkeypatch):
    monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")
    with pytest.raises(svc.VerseOfTheDayUnavailable):
        # Cast through ``str`` since the function's signature is
        # ``LocaleCode``; we want to exercise the runtime guard for
        # locales that pass past the normalization layer somehow.
        svc.get_verse_of_the_day("uk")  # type: ignore[arg-type]


def test_strip_html_collapses_paragraph_wrapper():
    html = "<p class='v'>For <span class='wj'>God</span>\nso loved</p>"
    assert svc._strip_html(html) == "For God so loved"


def test_route_returns_verse_when_service_succeeds(monkeypatch):
    monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")
    monkeypatch.setattr(svc, "_fetch_passage", _stub_fetch())
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/verse-of-the-day?locale=en")
    assert resp.status_code == 200
    body = resp.json()
    assert body["locale"] == "en"
    assert body["reference"] == "John 3:16"
    assert body["version"] == "BSB"
    assert body["text"].startswith("For God")


def test_route_normalizes_bcp47_locales(monkeypatch):
    monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")
    monkeypatch.setattr(svc, "_fetch_passage", _stub_fetch())
    with TestClient(app) as tc:
        # en-US should match the 'en' catalog; ru-RU should match 'ru'.
        for raw in ("en-US", "ru_RU"):
            resp = tc.get(f"/api/v1/verse-of-the-day?locale={raw}")
            assert resp.status_code == 200, raw


def test_route_returns_404_when_apikey_missing(monkeypatch):
    monkeypatch.delenv("YOUVERSION_API_KEY", raising=False)
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/verse-of-the-day?locale=en")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "verse_of_the_day_unavailable"
