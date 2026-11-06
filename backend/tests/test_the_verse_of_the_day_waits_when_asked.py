"""The verse of the day waits when YouVersion asks it to, and keeps its card.

26.10.2026: YouVersion answered 429, and every render of one reader's
dashboard asked again — four refusals in five minutes, each spent from the
key the lessons share, each answered to the reader with a card that vanished.
The lessons learned to wait on 27.10 (``api_source``); the verse of the day
did not. Pinned here: a 429 holds the whole process for as long as the
publisher said, the verse of the day honours a refusal the lessons heard, and
while it waits the last verse it had is shown rather than nothing.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services import verse_of_the_day as svc
from app.services.bible import api_source

TODAY = dt.date(2026, 11, 6)
YESTERDAY = TODAY - dt.timedelta(days=1)


class _Resp:
    def __init__(self, status_code: int, *, body: dict[str, Any] | None = None, retry_after: str | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}
        self.headers = {"Retry-After": retry_after} if retry_after else {}

    def json(self) -> dict[str, Any]:
        return self._body


class _Publisher:
    """YouVersion, answering in turn from a script, counting what it was asked."""

    def __init__(self, *answers: _Resp) -> None:
        self.answers = list(answers)
        self.asked = 0

    def __enter__(self) -> _Publisher:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(self, url: str, *, headers: dict[str, str]) -> _Resp:
        self.asked += 1
        return self.answers.pop(0)


def _verse(text: str) -> _Resp:
    return _Resp(200, body={"reference": "John 10:10", "content": f"<p>{text}</p>"})


@pytest.fixture(autouse=True)
def _a_key_and_an_empty_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "YOUVERSION_API_KEY", SecretStr("test-key"))
    svc._reset_cache_for_tests()
    yield
    svc._reset_cache_for_tests()


def _publish(monkeypatch: pytest.MonkeyPatch, *answers: _Resp) -> _Publisher:
    publisher = _Publisher(*answers)
    monkeypatch.setattr(svc.httpx, "Client", lambda *a, **k: publisher)
    return publisher


def test_a_refusal_stops_the_next_request(monkeypatch: pytest.MonkeyPatch) -> None:
    publisher = _publish(monkeypatch, _Resp(429, retry_after="120"))

    for _ in range(4):
        with pytest.raises(svc.VerseOfTheDayUnavailable):
            svc.get_verse_of_the_day("en", today=TODAY)

    assert publisher.asked == 1
    assert api_source.publisher_is_refusing()


def test_a_refusal_the_lessons_heard_holds_the_verse_too(monkeypatch: pytest.MonkeyPatch) -> None:
    publisher = _publish(monkeypatch, _verse("I came that they may have life"))
    api_source.publisher_refused("60")

    with pytest.raises(svc.VerseOfTheDayUnavailable):
        svc.get_verse_of_the_day("en", today=TODAY)

    assert publisher.asked == 0


def test_while_it_waits_the_last_verse_stays_on_the_card(monkeypatch: pytest.MonkeyPatch) -> None:
    _publish(monkeypatch, _verse("Yesterday's verse"), _Resp(429, retry_after="120"))
    svc.get_verse_of_the_day("en", today=YESTERDAY)

    verse = svc.get_verse_of_the_day("en", today=TODAY)

    assert verse.text == "Yesterday's verse"
    assert verse.date == YESTERDAY.isoformat(), "it says which day it was the verse of"


def test_another_language_s_verse_is_not_shown_instead(monkeypatch: pytest.MonkeyPatch) -> None:
    _publish(monkeypatch, _verse("A verse in English"), _Resp(429, retry_after="120"))
    svc.get_verse_of_the_day("en", today=YESTERDAY)

    with pytest.raises(svc.VerseOfTheDayUnavailable):
        svc.get_verse_of_the_day("ru", today=TODAY)


def test_once_the_wait_is_over_today_s_verse_replaces_it(monkeypatch: pytest.MonkeyPatch) -> None:
    publisher = _publish(
        monkeypatch, _verse("Yesterday's verse"), _Resp(429, retry_after="120"), _verse("Today's verse")
    )
    svc.get_verse_of_the_day("en", today=YESTERDAY)
    svc.get_verse_of_the_day("en", today=TODAY)

    monkeypatch.setattr(api_source, "_refusing_until", 0.0)
    verse = svc.get_verse_of_the_day("en", today=TODAY)

    assert verse.text == "Today's verse"
    assert publisher.asked == 3


def test_a_refusal_is_counted_as_one(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr("app.core.metrics.increment", lambda name, **tags: seen.append({"name": name, **tags}))
    _publish(monkeypatch, _Resp(429))

    with pytest.raises(svc.VerseOfTheDayUnavailable):
        svc.get_verse_of_the_day("en", today=TODAY)

    assert [s["outcome"] for s in seen if s["name"] == "equip.youversion.api_calls_total"] == ["rate_limited"]
