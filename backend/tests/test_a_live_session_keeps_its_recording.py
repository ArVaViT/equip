"""A live session carries its recording, for the half of the class that watches later.

The teacher pastes the recording's address on the event once it exists.
It is the same kind of value as the meeting link — written by a teacher,
rendered to every student as an ``href`` — so it goes through the same
gate, and it reaches the same surfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .test_a_meeting_link_is_a_web_address import (
    CALENDAR,
    COURSES,
    _create_event,
    _published_course_with_student,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

RECORDING = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s"


def test_the_recording_is_added_after_the_session_and_reaches_the_student(
    client: TestClient, db: Session, student: User
) -> None:
    course_id = _published_course_with_student(db, student)
    event = _create_event(client, course_id).json()
    assert event["recording_url"] is None

    added = client.put(f"{COURSES}/{course_id}/events/{event['id']}", json={"recording_url": RECORDING})
    assert added.status_code == 200, added.text
    assert added.json()["recording_url"] == RECORDING

    assert [r["recording_url"] for r in client.get(f"{COURSES}/{course_id}/events").json()] == [RECORDING]
    assert [r["recording_url"] for r in client.get(CALENDAR).json()] == [RECORDING]

    cleared = client.put(f"{COURSES}/{course_id}/events/{event['id']}", json={"recording_url": None})
    assert cleared.json()["recording_url"] is None


@pytest.mark.parametrize("value", ["javascript:alert(1)", "https://youtube.com@evil.example/x", "youtube.com/x"])
def test_anything_but_a_web_address_is_refused(client: TestClient, db: Session, student: User, value: str) -> None:
    course_id = _published_course_with_student(db, student)
    r = _create_event(client, course_id, recording_url=value)
    assert r.status_code == 422
    assert [e["loc"][-1] for e in r.json()["detail"]] == ["recording_url"]
