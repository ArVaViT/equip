"""Finishing the first-run flow is something the account remembers, not the browser.

Until now the flow's "done" mark lived in ``localStorage`` under the user's
id. A second device, a private window or cleared site data had never seen it,
so a returning student was asked to set up their account and pick a first
course all over again — the owner's complaint, word for word. The server now
holds the mark; the browser flag is a cache of it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.user import User

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID

COMPLETE = "/api/v1/users/me/onboarding/complete"
ME = "/api/v1/auth/me"


def test_a_new_account_has_not_finished_onboarding(student_client: TestClient) -> None:
    response = student_client.get(ME)
    assert response.status_code == 200
    assert response.json()["onboarding_completed_at"] is None


def test_finishing_is_recorded_and_returned(student_client: TestClient, db: Session) -> None:
    response = student_client.post(COMPLETE)
    assert response.status_code == 200
    stamped = response.json()["onboarding_completed_at"]
    assert stamped is not None

    row = db.get(User, STUDENT_ID)
    assert row is not None
    assert row.onboarding_completed_at is not None
    # And the profile every other client reads says the same thing, so a
    # second device does not have to be told.
    assert student_client.get(ME).json()["onboarding_completed_at"] == stamped


def test_finishing_twice_keeps_the_first_time(student_client: TestClient, db: Session) -> None:
    # A second browser reporting the cached flag months later must not make
    # the record say the flow was finished more recently than it was.
    row = db.get(User, STUDENT_ID)
    assert row is not None
    row.onboarding_completed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    db.commit()

    response = student_client.post(COMPLETE)
    assert response.status_code == 200
    assert response.json()["onboarding_completed_at"].startswith("2026-01-01T12:00:00")


def test_finishing_needs_an_account(anon_client: TestClient) -> None:
    assert anon_client.post(COMPLETE).status_code in (401, 403)
