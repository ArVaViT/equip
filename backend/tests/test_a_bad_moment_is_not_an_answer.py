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
