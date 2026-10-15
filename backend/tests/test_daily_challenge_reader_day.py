"""The question turns over at the reader's midnight, not UTC's (2026-10-03).

At 21:00 on a Saturday in Indianapolis it is already Sunday in UTC. The
question used to change then — in the middle of the evening class — and a
student who answered at 19:00 and looked again at 21:00 found a new one,
with yesterday's counted as missed the next morning.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from app.services.daily_challenge import schedule as schedule_module
from app.services.daily_challenge.schedule import reader_today

from .test_daily_challenge_archive import _schedule, _seed_q

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

# Saturday 3 October 2026, 21:00 in Indianapolis = Sunday 01:00 UTC.
INSTANT = datetime(2026, 10, 4, 1, 0, tzinfo=UTC)


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return INSTANT.astimezone(tz) if tz else INSTANT.replace(tzinfo=None)


@pytest.fixture
def author(db: Session) -> User:
    from app.models.user import User, UserRole

    u = User(
        id=uuid.uuid4(), email=f"dc-day-{uuid.uuid4().hex[:8]}@example.com", full_name="A", role=UserRole.TEACHER.value
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_module, "datetime", _Frozen)


def test_the_reader_s_day_is_their_own(frozen: None) -> None:
    assert reader_today("America/Indiana/Indianapolis") == date(2026, 10, 3)
    assert reader_today("Europe/Kyiv") == date(2026, 10, 4)
    assert reader_today(None) == date(2026, 10, 4)
    assert reader_today("Not/AZone") == date(2026, 10, 4)


def test_an_evening_in_indiana_still_shows_saturday_s_question(
    frozen: None,
    db: Session,
    author: User,
    student: User,
    student_client: TestClient,
) -> None:
    saturday = _seed_q(db, author_id=author.id, chapter=3)
    sunday = _seed_q(db, author_id=author.id, chapter=4)
    _schedule(db, saturday, date(2026, 10, 3), author.id)
    _schedule(db, sunday, date(2026, 10, 4), author.id)

    student.time_zone = "America/Indiana/Indianapolis"
    db.commit()
    r = student_client.get("/api/v1/daily-challenge/today")
    assert r.status_code == 200, r.text
    assert r.json()["question_id"] == str(saturday.id)
    assert r.json()["challenge_date"] == "2026-10-03"

    student.time_zone = "Europe/Kyiv"
    db.commit()
    r = student_client.get("/api/v1/daily-challenge/today")
    assert r.json()["question_id"] == str(sunday.id)


def test_saturday_is_not_in_the_archive_while_it_is_still_saturday(
    frozen: None,
    db: Session,
    author: User,
    student: User,
    student_client: TestClient,
) -> None:
    saturday = _seed_q(db, author_id=author.id)
    _schedule(db, saturday, date(2026, 10, 3), author.id)
    student.time_zone = "America/Indiana/Indianapolis"
    db.commit()
    r = student_client.get("/api/v1/daily-challenge/archive/2026-10-03")
    assert r.status_code == 422


def test_an_answer_is_judged_against_the_question_on_screen(
    frozen: None, db: Session, author: User, student: User, student_client: TestClient
) -> None:
    """The card loaded Sunday's question (no zone recorded yet: UTC), then the
    profile's zone arrived and made it Saturday. The answer to the question on
    screen is that question's answer — not "invalid option" against Saturday's."""
    from app.models.daily_challenge import DailyChallengeOption

    saturday = _seed_q(db, author_id=author.id, chapter=3)
    sunday = _seed_q(db, author_id=author.id, chapter=4)
    _schedule(db, saturday, date(2026, 10, 3), author.id)
    _schedule(db, sunday, date(2026, 10, 4), author.id)

    student.time_zone = None
    db.commit()
    card = student_client.get("/api/v1/daily-challenge/today").json()
    assert card["question_id"] == str(sunday.id)

    student.time_zone = "America/Indiana/Indianapolis"
    db.commit()
    option = db.query(DailyChallengeOption).filter(DailyChallengeOption.question_id == sunday.id).first()
    assert option is not None
    r = student_client.post(
        "/api/v1/daily-challenge/today/attempt",
        json={"selected_option_id": str(option.id), "challenge_date": card["challenge_date"]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["challenge_date"] == "2026-10-04"

    # A card two days stale answers to today, and today's question has other options.
    r = student_client.post(
        "/api/v1/daily-challenge/today/attempt",
        json={"selected_option_id": str(option.id), "challenge_date": "2026-10-01"},
    )
    assert r.status_code == 422
