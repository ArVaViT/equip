# ruff: noqa: RUF002
# Edition and psalm text quoted in the prose is Cyrillic because that is what it is.
"""Unit + route tests for the verse-of-the-day feature.

We never hit YouVersion in tests — both the service-level cases and the
route case monkeypatch the single ``_fetch_passage`` seam in the service
module. ``settings.YOUVERSION_API_KEY`` is patched per-test; the
``apikey_missing`` route case relies on that.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
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
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
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
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
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
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
    monkeypatch.setattr(svc, "_fetch_passage", _stub_fetch())
    svc.get_verse_of_the_day("en", today=dt.date(2026, 5, 13))
    svc.get_verse_of_the_day("en", today=dt.date(2026, 5, 14))
    keys = list(svc._CACHE.keys())
    assert all(k[0] == "2026-05-14" for k in keys)


def test_get_verse_of_the_day_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", None)
    with pytest.raises(svc.VerseOfTheDayUnavailable):
        svc.get_verse_of_the_day("en")


def test_get_verse_of_the_day_raises_for_unsupported_locale(monkeypatch):
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
    with pytest.raises(svc.VerseOfTheDayUnavailable):
        # Cast through ``str`` since the function's signature is
        # ``LocaleCode``; we want to exercise the runtime guard for
        # locales that pass past the normalization layer somehow.
        svc.get_verse_of_the_day("uk")  # type: ignore[arg-type]


def test_strip_html_collapses_paragraph_wrapper():
    html = "<p class='v'>For <span class='wj'>God</span>\nso loved</p>"
    assert svc._strip_html(html) == "For God so loved"


def test_route_returns_verse_when_service_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
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
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
    monkeypatch.setattr(svc, "_fetch_passage", _stub_fetch())
    with TestClient(app) as tc:
        # en-US should match the 'en' catalog; ru-RU should match 'ru'.
        for raw in ("en-US", "ru_RU"):
            resp = tc.get(f"/api/v1/verse-of-the-day?locale={raw}")
            assert resp.status_code == 200, raw


def test_route_returns_404_when_apikey_missing(monkeypatch):
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", None)
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/verse-of-the-day?locale=en")
    assert resp.status_code == 404
    assert resp.json()["detail"]["message"] == "verse_of_the_day_unavailable"


def test_walks_forward_on_verse_not_in_bible(monkeypatch):
    """NRT lacks some Psalm verses due to Septuagint/Masoretic
    numbering differences. The service must walk forward in the
    catalog until a present reference is found, and the chosen
    fallback must be deterministic for (date, locale)."""
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
    today = dt.date(2026, 5, 31)
    primary = svc._pick_reference(today)
    fallback = svc._pick_reference_offset(today, 1)
    seen: list[str] = []

    def _selective(api_key: str, bible_id: int, ref: str) -> tuple[str, str]:
        seen.append(ref)
        if ref == primary:
            raise svc.VerseNotInBible(f"no {ref} in {bible_id}")
        return f"{ref} ru-ref", "RU body"

    monkeypatch.setattr(svc, "_fetch_passage", _selective)
    # Use EN locale so the catalog ref reaches ``_fetch_passage`` without
    # the Psalms Septuagint remap; the locale-specific remap behaviour
    # is covered by dedicated tests below.
    verse = svc.get_verse_of_the_day("en", today=today)
    assert verse.reference == f"{fallback} ru-ref"
    assert seen == [primary, fallback]


def test_walks_forward_then_caches_the_fallback(monkeypatch):
    """A successful walk-forward fallback must cache so the second
    call on the same UTC date does NOT walk again."""
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
    today = dt.date(2026, 5, 31)
    primary = svc._pick_reference(today)
    calls = {"n": 0}

    def _selective(api_key: str, bible_id: int, ref: str) -> tuple[str, str]:
        calls["n"] += 1
        if ref == primary:
            raise svc.VerseNotInBible(f"no {ref} in {bible_id}")
        return "fallback-ref", "fallback body"

    monkeypatch.setattr(svc, "_fetch_passage", _selective)
    svc.get_verse_of_the_day("en", today=today)
    svc.get_verse_of_the_day("en", today=today)
    # First call: 2 fetches (primary 404 → fallback ok). Second call:
    # 0 fetches (cache hit). Total: 2.
    assert calls["n"] == 2


def test_gives_up_after_walk_cap(monkeypatch):
    """If every reference in the walk window is absent, surface the
    standard ``VerseOfTheDayUnavailable`` so the frontend hides the
    card silently — never expose a partial / broken state."""
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))

    def _always_missing(api_key: str, bible_id: int, ref: str) -> tuple[str, str]:
        raise svc.VerseNotInBible(f"no {ref} in {bible_id}")

    monkeypatch.setattr(svc, "_fetch_passage", _always_missing)
    with pytest.raises(svc.VerseOfTheDayUnavailable):
        # EN locale to avoid the Psalms Septuagint remap shadowing
        # this cap-exhaustion path; the RU remap has its own tests.
        svc.get_verse_of_the_day("en", today=dt.date(2026, 5, 31))


def test_walk_does_not_consume_transient_errors(monkeypatch):
    """A 5xx / timeout from YouVersion is transient — it must NOT
    be treated as "verse missing from this bible" and trigger the
    walk forward. Surface as ``VerseOfTheDayUnavailable`` directly so
    the route 404s and the frontend hides; the next page load tries
    again. (Walking forward on transient errors would silently mask
    upstream outages by always serving the second verse.)"""
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))

    def _transient(api_key: str, bible_id: int, ref: str) -> tuple[str, str]:
        raise svc.VerseOfTheDayUnavailable("YouVersion 503")

    monkeypatch.setattr(svc, "_fetch_passage", _transient)
    with pytest.raises(svc.VerseOfTheDayUnavailable):
        svc.get_verse_of_the_day("en", today=dt.date(2026, 5, 31))


def test_remap_psalm_for_ru_simple_offset_range() -> None:
    """For the simple offset range (Hebrew 11-113, 117-146), NRT
    references should be one chapter lower than the catalog."""
    assert svc._remap_ref_for_locale("PSA.23.1", "ru") == "PSA.22.1"
    assert svc._remap_ref_for_locale("PSA.28.7", "ru") == "PSA.27.7"
    assert svc._remap_ref_for_locale("PSA.119.105", "ru") == "PSA.118.105"
    assert svc._remap_ref_for_locale("PSA.121.1", "ru") == "PSA.120.1"


def test_remap_psalm_for_ru_identical_range() -> None:
    """Hebrew Psalms 1, 2 and 148-150 match Septuagint numbering.

    Only those. Psalms 3 through 8 keep their chapter number and still
    shift a verse, because the Slavic tradition numbers the heading —
    Hebrew 4:8 is 4:9 there, and calling the whole 1-8 band identical
    quoted every one of them one verse early.
    """
    assert svc._remap_ref_for_locale("PSA.1.1", "ru") == "PSA.1.1"
    assert svc._remap_ref_for_locale("PSA.4.8", "ru") == "PSA.4.9"
    assert svc._remap_ref_for_locale("PSA.148.1", "ru") == "PSA.148.1"


def test_remap_psalm_for_ru_split_chapters_now_have_an_answer() -> None:
    """Hebrew 9, 10, 114, 115, 116 and 147 are split or joined across
    the two traditions. That used to mean "no honest mapping" and a
    Russian reader saw the author's untranslated verse; the per-verse
    table names each one. Read off НРТ on 2026-08-16."""
    assert svc._remap_ref_for_locale("PSA.9.1", "ru") == "PSA.9.2"
    assert svc._remap_ref_for_locale("PSA.10.1", "ru") == "PSA.9.22"
    assert svc._remap_ref_for_locale("PSA.116.1", "ru") == "PSA.114.1"
    assert svc._remap_ref_for_locale("PSA.147.1", "ru") == "PSA.146.1"


def test_remap_non_psalm_or_non_ru_is_identity() -> None:
    """Only the RU (NRT) locale + Psalms book needs remapping."""
    assert svc._remap_ref_for_locale("JHN.3.16", "ru") == "JHN.3.16"
    assert svc._remap_ref_for_locale("PSA.23.1", "en") == "PSA.23.1"


def test_walk_skips_a_reference_the_edition_cannot_hold(monkeypatch) -> None:
    """A span that straddles a seam cannot be named in the other
    tradition — Hebrew 116 is two psalms there — so the walk advances to
    the next catalog entry rather than quoting the wrong half."""
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
    today = dt.date(2026, 5, 31)
    # Find an offset where the catalog hits a complex chapter; fall
    # back to monkey-stubbing the picker so the test is deterministic.
    seen_refs: list[str] = []

    def _picker(d: dt.date, offset: int) -> str:
        # offset 0 returns a complex psalm; offset 1 returns a clean one.
        return ["PSA.116.1-19", "JHN.3.16"][offset]

    def _stub_fetch(api_key: str, bible_id: int, ref: str) -> tuple[str, str]:
        seen_refs.append(ref)
        return "От Иоанна 3:16", "Ведь Бог так полюбил мир..."

    monkeypatch.setattr(svc, "_pick_reference_offset", _picker)
    monkeypatch.setattr(svc, "_fetch_passage", _stub_fetch)
    verse = svc.get_verse_of_the_day("ru", today=today)
    assert verse.reference == "От Иоанна 3:16"
    # The straddling span was skipped without even hitting the API.
    assert seen_refs == ["JHN.3.16"]


def test_psalm_for_ru_uses_remapped_chapter(monkeypatch) -> None:
    """For an RU Psalm in the simple-offset range, the route must
    call the upstream API with chapter-1 so the returned content
    matches the catalog's intent (the Hebrew-numbered verse)."""
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
    today = dt.date(2026, 6, 1)
    requested: list[str] = []

    def _picker(d: dt.date, offset: int) -> str:
        # offset 0 is the day's verse; only one offset needed.
        return "PSA.28.7" if offset == 0 else "JHN.1.1"

    def _stub_fetch(api_key: str, bible_id: int, ref: str) -> tuple[str, str]:
        requested.append(ref)
        return "Псалтирь 27:7", "Господь — моя сила и щит"

    monkeypatch.setattr(svc, "_pick_reference_offset", _picker)
    monkeypatch.setattr(svc, "_fetch_passage", _stub_fetch)
    verse = svc.get_verse_of_the_day("ru", today=today)
    assert "сила и щит" in verse.text
    # Pinned: the upstream request used the SEPTUAGINT reference,
    # not the Hebrew one the catalog stores.
    assert requested == ["PSA.27.7"]
