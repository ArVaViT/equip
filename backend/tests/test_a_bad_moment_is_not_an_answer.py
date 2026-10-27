"""A rate limit is not "this verse does not exist".

``fetch_verse`` memoises its answers, which is right: a course quotes
the same verse in a dozen lessons and the edition does not change
between them. What it memoised included the failures — every status
that was not 200, cached as ``None``, for the life of the process.

During a backfill that runs for hours, one 429 meant the verse was
"absent" for the rest of the run, and every quotation of it fell back
to the author's language: an English verse inside German prose, with
nothing anywhere reporting a problem. The one status worth remembering
is 404, which really does mean this edition does not have that verse —
a versification difference, which is data.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.bible import api_source
from app.services.bible.references import BibleRef

REF = BibleRef("john", 3, 16)


class _Response:
    def __init__(self, status_code: int, content: str = "") -> None:
        self.status_code = status_code
        self._content = content

    def json(self) -> dict[str, str]:
        return {"content": self._content}


@pytest.fixture(autouse=True)
def _a_clean_cache_and_a_key(monkeypatch):
    api_source._cache.clear()
    monkeypatch.setenv("YOUVERSION_API_KEY", "test-key")
    yield
    api_source._cache.clear()


def _answer_with(monkeypatch, *responses: _Response) -> list[int]:
    """Serve ``responses`` in order; return a list that counts the calls."""
    calls: list[int] = []

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def get(self, *_args, **_kwargs):
            calls.append(1)
            return responses[min(len(calls) - 1, len(responses) - 1)]

    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: _Client())
    return calls


@pytest.mark.parametrize("status", [429, 500, 502, 401])
def test_a_bad_status_is_asked_again(monkeypatch, status: int):
    calls = _answer_with(monkeypatch, _Response(status), _Response(200, "Denn also hat Gott die Welt geliebt"))

    assert api_source.fetch_verse(REF, "de") is None
    assert api_source.fetch_verse(REF, "de") == "Denn also hat Gott die Welt geliebt"
    assert len(calls) == 2, "the failure was remembered as an answer"


def test_a_missing_verse_is_remembered(monkeypatch):
    # 404 is the edition telling us it does not number this verse. Asking
    # again on every quotation would be a request per lesson for an answer
    # that will not change.
    calls = _answer_with(monkeypatch, _Response(404))

    assert api_source.fetch_verse(REF, "de") is None
    assert api_source.fetch_verse(REF, "de") is None
    assert len(calls) == 1


def test_a_verse_is_fetched_once(monkeypatch):
    calls = _answer_with(monkeypatch, _Response(200, "Denn also hat Gott die Welt geliebt"))

    assert api_source.fetch_verse(REF, "de") == "Denn also hat Gott die Welt geliebt"
    assert api_source.fetch_verse(REF, "de") == "Denn also hat Gott die Welt geliebt"
    assert len(calls) == 1


def _counted(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "equip.metric" and "equip.youversion.api_calls_total" in r.getMessage()
    ]


@pytest.mark.parametrize(
    ("status", "outcome"),
    [(200, "success"), (404, "not_in_bible"), (429, "rate_limited"), (502, "fatal")],
)
def test_every_request_a_lesson_makes_is_counted(monkeypatch, caplog, status: int, outcome: str):
    # 2026-10-27: the publisher answered every request with 429 and only
    # the verse of the day was counted, so nobody could say whose requests
    # had spent the key. A lesson's lookups are most of the traffic.
    _answer_with(monkeypatch, _Response(status, "Denn also hat Gott die Welt geliebt"))

    with caplog.at_level("INFO", logger="equip.metric"):
        api_source.fetch_verse(REF, "de")

    [line] = _counted(caplog)
    assert "caller=passage" in line
    assert f"outcome={outcome}" in line
    assert f"status_code={status}" in line


def test_a_request_that_never_got_an_answer_is_counted_too(monkeypatch, caplog):
    class _Down:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def get(self, *_args, **_kwargs):
            raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: _Down())

    with caplog.at_level("INFO", logger="equip.metric"):
        assert api_source.fetch_verse(REF, "de") is None

    [line] = _counted(caplog)
    assert "outcome=fatal" in line
    assert "status_code=0" in line


def test_a_remembered_answer_costs_no_request_and_is_not_counted(monkeypatch, caplog):
    _answer_with(monkeypatch, _Response(404))
    api_source.fetch_verse(REF, "de")
    caplog.clear()

    with caplog.at_level("INFO", logger="equip.metric"):
        api_source.fetch_verse(REF, "de")

    assert _counted(caplog) == []
