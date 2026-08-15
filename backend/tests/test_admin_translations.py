"""Tests for the admin failed_permanent reset endpoints.

Both routes share the same shape — admin-only, audit-logged, idempotent
on already-OK rows, 404 when no row matched the selector. The tests
pin every important branch.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.content_version import (
    CONTENT_VERSION_MAX_ATTEMPTS,
    ContentVersion,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_failed_permanent(
    db: Session,
    *,
    entity_id: str = "test-entity-1",
    entity_type: str = "course",
    field: str = "title",
    locale: str = "en",
) -> ContentVersion:
    row = ContentVersion(
        id=uuid.uuid4(),
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
        text="",
        origin="mt",
        status="failed_permanent",
        attempts=CONTENT_VERSION_MAX_ATTEMPTS,
        source_locale="ru",
        source_hash="x" * 64,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_reset_by_ids_flips_failed_permanent_to_failed(admin_client: TestClient, db: Session):
    row = _seed_failed_permanent(db)
    resp = admin_client.post(
        "/api/v1/admin/translations/reset-by-ids",
        json={"ids": [str(row.id)]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"reset": 1}

    db.refresh(row)
    assert row.status == "failed"
    assert row.attempts == 0


def test_reset_by_ids_404_when_no_failed_permanent_match(admin_client: TestClient, db: Session):
    """A row that's currently ``ok`` is silently skipped (the endpoint
    only flips ``failed_permanent`` rows). When the result is zero
    affected rows, the route returns 404 so the operator can spot the
    misfire instead of seeing a 200 that did nothing."""
    ok_row = ContentVersion(
        id=uuid.uuid4(),
        entity_type="course",
        entity_id="x",
        field="title",
        locale="en",
        text="alive",
        origin="mt",
        status="ok",
        attempts=0,
        source_locale="ru",
        source_hash="y" * 64,
    )
    db.add(ok_row)
    db.commit()

    resp = admin_client.post(
        "/api/v1/admin/translations/reset-by-ids",
        json={"ids": [str(ok_row.id)]},
    )
    assert resp.status_code == 404


def test_reset_by_ids_requires_admin(client: TestClient, db: Session):
    """The teacher-scoped client must be rejected."""
    row = _seed_failed_permanent(db)
    resp = client.post(
        "/api/v1/admin/translations/reset-by-ids",
        json={"ids": [str(row.id)]},
    )
    assert resp.status_code == 403


def test_reset_by_entity_flips_matching_row(admin_client: TestClient, db: Session):
    row = _seed_failed_permanent(
        db,
        entity_type="quiz_option",
        entity_id="opt-1",
        field="option_text",
        locale="en",
    )
    resp = admin_client.post(
        "/api/v1/admin/translations/reset-by-entity",
        json={
            "entity_type": "quiz_option",
            "entity_id": "opt-1",
            "field": "option_text",
            "locale": "en",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"reset": 1}

    db.refresh(row)
    assert row.status == "failed"
    assert row.attempts == 0


def test_reset_by_entity_404_on_no_match(admin_client: TestClient):
    resp = admin_client.post(
        "/api/v1/admin/translations/reset-by-entity",
        json={
            "entity_type": "course",
            "entity_id": "ghost",
            "field": "title",
            "locale": "en",
        },
    )
    assert resp.status_code == 404


def test_reset_by_ids_rejects_empty_id_list(admin_client: TestClient):
    """``min_length=1`` on the Pydantic model surfaces as a 422."""
    resp = admin_client.post(
        "/api/v1/admin/translations/reset-by-ids",
        json={"ids": []},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# retry-reviewed — re-open rows parked by a validator rule that has changed
# ---------------------------------------------------------------------------


def _seed_needs_review(
    db: Session,
    *,
    entity_type: str = "daily_challenge_question",
    locale: str = "de",
    origin: str = "mt",
) -> ContentVersion:
    row = ContentVersion(
        id=uuid.uuid4(),
        entity_type=entity_type,
        entity_id=str(uuid.uuid4()),
        field="explanation",
        locale=locale,
        text="Johannes 3,17 besagt: 'For God did not send his Son…'",
        origin=origin,
        status="needs_review",
        attempts=1,
        source_locale="en",
        source_hash="y" * 64,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_retry_reviewed_reopens_parked_rows(admin_client: TestClient, db: Session):
    row = _seed_needs_review(db)
    resp = admin_client.post(
        "/api/v1/admin/translations/retry-reviewed",
        json={"entity_type": "daily_challenge_question"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"reset": 1}

    db.refresh(row)
    # ``failed`` rather than deleted: the text and its review_reason stay
    # readable, and ``failed`` is the one status the orchestrator retries.
    assert row.status == "failed"
    assert row.attempts == 0


def test_retry_reviewed_can_be_scoped_to_one_language(admin_client: TestClient, db: Session):
    german = _seed_needs_review(db, locale="de")
    ukrainian = _seed_needs_review(db, locale="uk")

    resp = admin_client.post(
        "/api/v1/admin/translations/retry-reviewed",
        json={"entity_type": "daily_challenge_question", "locale": "de"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"reset": 1}

    db.refresh(german)
    db.refresh(ukrainian)
    assert german.status == "failed"
    assert ukrainian.status == "needs_review"


def test_retry_reviewed_never_touches_a_persons_own_translation(admin_client: TestClient, db: Session):
    human = _seed_needs_review(db, origin="human")

    resp = admin_client.post(
        "/api/v1/admin/translations/retry-reviewed",
        json={"entity_type": "daily_challenge_question"},
    )

    assert resp.status_code == 404
    db.refresh(human)
    assert human.status == "needs_review"


def test_retry_reviewed_honours_the_limit(admin_client: TestClient, db: Session):
    for _ in range(3):
        _seed_needs_review(db)

    resp = admin_client.post(
        "/api/v1/admin/translations/retry-reviewed",
        json={"entity_type": "daily_challenge_question", "limit": 2},
    )
    assert resp.status_code == 200
    assert resp.json() == {"reset": 2}


def test_retry_reviewed_404s_when_nothing_is_parked(admin_client: TestClient, db: Session):
    resp = admin_client.post(
        "/api/v1/admin/translations/retry-reviewed",
        json={"entity_type": "course"},
    )
    assert resp.status_code == 404


def test_retry_reviewed_is_admin_only(student_client: TestClient):
    resp = student_client.post(
        "/api/v1/admin/translations/retry-reviewed",
        json={"entity_type": "daily_challenge_question"},
    )
    assert resp.status_code in (401, 403)
