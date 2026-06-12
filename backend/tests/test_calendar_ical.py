"""iCal subscription endpoint tests.

Covers token issue/rotation, feed verification, scope enforcement,
ICS structural correctness, and graceful degradation when the
JWT secret is missing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.user import User, UserRole
from app.schemas.calendar import CalendarEvent
from app.services.calendar_ical import render_calendar

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture
def secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """Make the JWT secret deterministic for the tests so we can mint
    and decode tokens without touching the real Supabase one."""
    s = "test-ical-secret"
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", s)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    return s


@pytest.fixture
def student(db: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"ical-{uuid.uuid4().hex[:8]}@example.com",
        full_name="iCal Student",
        role=UserRole.STUDENT.value,
    )
    db.add(u)
    db.commit()
    return u


def _calendar_event(idx: int = 0) -> CalendarEvent:
    return CalendarEvent(
        id=f"e-{idx}",
        title="Module due: Romans 1-5",
        description=None,
        event_type="deadline",
        event_date=dt.datetime(2026, 6, 1 + idx, 12, 0, tzinfo=dt.UTC),
        course_id="c-1",
        course_title="Letter to the Romans",
        source="module_deadline",
    )


# ── ICS rendering ────────────────────────────────────────────────────


def test_render_calendar_emits_required_vcalendar_envelope() -> None:
    ics = render_calendar([_calendar_event()], user_email="x@example.com")
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.endswith("END:VCALENDAR\r\n")
    assert "VERSION:2.0\r\n" in ics
    assert "PRODID:-//Equip//Calendar//EN\r\n" in ics
    assert "X-WR-CALNAME:Equip Calendar (x@example.com)\r\n" in ics


def test_render_calendar_emits_one_vevent_per_event() -> None:
    ics = render_calendar([_calendar_event(0), _calendar_event(1)])
    assert ics.count("BEGIN:VEVENT") == 2
    assert ics.count("END:VEVENT") == 2
    # UID anchors against the source so re-subscribing updates entries.
    assert "UID:module_deadline-e-0@equipbible.com\r\n" in ics
    assert "UID:module_deadline-e-1@equipbible.com\r\n" in ics


def test_render_calendar_escapes_summary_commas_and_semicolons() -> None:
    evt = _calendar_event()
    evt = evt.model_copy(update={"title": "Romans 1:1; Paul, an apostle"})
    ics = render_calendar([evt])
    # Commas + semicolons in SUMMARY must be backslash-escaped per RFC 5545.
    assert "SUMMARY:Romans 1:1\\; Paul\\, an apostle\r\n" in ics


def test_render_calendar_uses_utc_timestamps() -> None:
    ics = render_calendar([_calendar_event()])
    # 2026-06-01 12:00 UTC.
    assert "DTSTART:20260601T120000Z\r\n" in ics


def test_render_calendar_includes_categories() -> None:
    ics = render_calendar([_calendar_event()])
    assert "CATEGORIES:deadline\r\n" in ics


# ── Token issue + feed ───────────────────────────────────────────────


def test_post_token_returns_signed_jwt_and_feed_url(student_client: TestClient, secret: str) -> None:
    resp = student_client.post("/api/v1/calendar/ical/token")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["feed_url"].endswith(f"?token={body['token']}")
    decoded = jwt.decode(body["token"], secret, algorithms=["HS256"], audience="equip-ical")
    assert decoded["scope"] == "ical"


def test_feed_with_valid_token_serves_text_calendar(
    student: User, secret: str, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stub the upstream event collector + override get_db so the
    test doesn't have to seed the full LMS data graph just to verify
    the route stitches together token-verification + ICS rendering."""
    from app.api.v1 import calendar_ical as route_mod

    def _stub_events(**kwargs: object) -> list[CalendarEvent]:
        return [_calendar_event()]

    monkeypatch.setattr(route_mod, "build_calendar_events", _stub_events)

    def _override_db() -> object:
        yield db

    app.dependency_overrides[get_db] = _override_db

    now = int(dt.datetime.now(dt.UTC).timestamp())
    token = jwt.encode(
        {
            "sub": str(student.id),
            "scope": "ical",
            "iat": now,
            "exp": now + 3600,
            "aud": "equip-ical",
        },
        secret,
        algorithm="HS256",
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as tc:
            resp = tc.get(f"/api/v1/calendar/ical/feed?token={token}")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in resp.text
    assert "BEGIN:VEVENT" in resp.text


def test_feed_rejects_token_without_ical_scope(secret: str) -> None:
    """A token signed with our secret but scoped to anything else
    (e.g. an admin token reused as iCal) must be rejected — that's
    the whole point of the scope claim."""
    now = int(dt.datetime.now(dt.UTC).timestamp())
    token = jwt.encode(
        {
            "sub": "abc",
            "scope": "admin",
            "iat": now,
            "exp": now + 3600,
            "aud": "equip-ical",
        },
        secret,
        algorithm="HS256",
    )
    with TestClient(app) as tc:
        resp = tc.get(f"/api/v1/calendar/ical/feed?token={token}")
    assert resp.status_code == 401


def test_feed_rejects_expired_token(secret: str) -> None:
    now = int(dt.datetime.now(dt.UTC).timestamp())
    token = jwt.encode(
        {
            "sub": "abc",
            "scope": "ical",
            "iat": now - 7200,
            "exp": now - 3600,
            "aud": "equip-ical",
        },
        secret,
        algorithm="HS256",
    )
    with TestClient(app) as tc:
        resp = tc.get(f"/api/v1/calendar/ical/feed?token={token}")
    assert resp.status_code == 401


def test_feed_rejects_garbage_token(secret: str) -> None:
    with TestClient(app) as tc:
        resp = tc.get("/api/v1/calendar/ical/feed?token=not-a-jwt")
    assert resp.status_code == 401


def test_feed_rejects_token_signed_with_different_secret(secret: str) -> None:
    """A token with a valid JWT structure but signed with the wrong
    secret must be rejected. This is the core auth guarantee — without
    it, an attacker who can sign tokens with their own key would
    bypass auth entirely."""
    now = int(dt.datetime.now(dt.UTC).timestamp())
    token = jwt.encode(
        {
            "sub": "abc",
            "scope": "ical",
            "iat": now,
            "exp": now + 3600,
            "aud": "equip-ical",
        },
        "attacker-signed-with-a-totally-different-secret",
        algorithm="HS256",
    )
    with TestClient(app) as tc:
        resp = tc.get(f"/api/v1/calendar/ical/feed?token={token}")
    assert resp.status_code == 401


def test_feed_rejects_token_issued_before_rotation_floor(
    student: User, secret: str, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the user calls /token, ``calendar_ical_min_iat`` advances
    to the new token's iat. Any previously issued token must be
    refused — without that floor, JWT's default decode never validates
    iat and a leaked URL stays valid for the full TTL."""
    from app.api.v1 import calendar_ical as route_mod

    def _stub_events(**kwargs: object) -> list[CalendarEvent]:
        return [_calendar_event()]

    monkeypatch.setattr(route_mod, "build_calendar_events", _stub_events)

    def _override_db() -> object:
        yield db

    app.dependency_overrides[get_db] = _override_db

    now = int(dt.datetime.now(dt.UTC).timestamp())
    # Simulate that the user rotated their token a minute ago; this
    # token was issued earlier and is now below the floor.
    student.calendar_ical_min_iat = now
    db.commit()

    old_token = jwt.encode(
        {
            "sub": str(student.id),
            "scope": "ical",
            "iat": now - 60,
            "exp": now + 3600,
            "aud": "equip-ical",
        },
        secret,
        algorithm="HS256",
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as tc:
            resp = tc.get(f"/api/v1/calendar/ical/feed?token={old_token}")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 401


def test_post_token_stamps_calendar_ical_min_iat(student: User, secret: str, db: Session) -> None:
    """The /token route must update the user's rotation floor so a
    subsequent feed call refuses old tokens. Without the DB write,
    rotation is purely cosmetic."""
    from app.api import dependencies as deps

    app.dependency_overrides[deps.get_current_user] = lambda: student

    def _override_db() -> object:
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        before = student.calendar_ical_min_iat
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/calendar/ical/token")
        assert resp.status_code == 200
        body = resp.json()
        decoded = jwt.decode(body["token"], secret, algorithms=["HS256"], audience="equip-ical")
        db.refresh(student)
        assert student.calendar_ical_min_iat == decoded["iat"]
        # And the stored floor is freshly advanced.
        assert before is None or student.calendar_ical_min_iat >= before
    finally:
        app.dependency_overrides.pop(deps.get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
