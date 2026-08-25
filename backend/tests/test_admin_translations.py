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
from app.services.content_versions import record_mt_version

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


# ---------------------------------------------------------------------------
# accept-reviewed — a person read the row and the check was wrong about it
# ---------------------------------------------------------------------------


def test_accept_reviewed_makes_the_row_servable(admin_client: TestClient, db: Session):
    """The structural check is strict on purpose, and its cost lands on
    the reader: a row it parks is invisible until somebody acts. Redoing
    it is no help — at temperature 0 the same source returns the same
    text and the same verdict — so without this, a correct translation
    the checker misread stays unreadable forever."""
    row = _seed_needs_review(db, locale="uk")

    resp = admin_client.post(
        "/api/v1/admin/translations/accept-reviewed",
        json={"ids": [str(row.id)]},
    )

    assert resp.status_code == 200
    assert resp.json() == {"reset": 1}
    db.refresh(row)
    assert row.status == "ok"


def test_accept_reviewed_keeps_the_reason_on_the_row(admin_client: TestClient, db: Session):
    """Accepting is a person overruling the check, not the check having
    been right. What it objected to stays on the row so the next reader
    of this history can see what was overruled."""
    row = _seed_needs_review(db, locale="uk")
    row.review_reason = "[wrong_language] reads as ru, not uk"
    db.commit()

    admin_client.post("/api/v1/admin/translations/accept-reviewed", json={"ids": [str(row.id)]})

    db.refresh(row)
    assert row.status == "ok"
    assert row.review_reason == "[wrong_language] reads as ru, not uk"


def test_accept_reviewed_ignores_rows_that_were_never_parked(admin_client: TestClient, db: Session):
    """Only ``needs_review`` is acceptable. A row that failed outright
    has no text worth serving, and one that is already ``ok`` needs
    nothing."""
    ok_row = _seed_needs_review(db)
    ok_row.status = "ok"
    db.commit()

    resp = admin_client.post(
        "/api/v1/admin/translations/accept-reviewed",
        json={"ids": [str(ok_row.id)]},
    )

    assert resp.status_code == 404


def test_accept_reviewed_is_admin_only(student_client: TestClient):
    resp = student_client.post(
        "/api/v1/admin/translations/accept-reviewed",
        json={"ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# purge-orphans — rows whose entity is gone
# ---------------------------------------------------------------------------


def test_purge_orphans_counts_without_deleting_by_default(admin_client: TestClient, db: Session):
    """Counting is free and decides nothing, so it is what happens when
    nobody asked for a deletion."""
    orphan = ContentVersion(
        id=uuid.uuid4(),
        entity_type="chapter_block",
        entity_id=str(uuid.uuid4()),
        field="content",
        locale="en",
        text="<p>Orphaned by a course that is gone.</p>",
        origin="mt",
        status="ok",
        source_locale="ru",
        source_hash="c" * 64,
    )
    db.add(orphan)
    db.commit()

    resp = admin_client.post("/api/v1/admin/translations/purge-orphans", json={})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["removed"] == 0
    assert body["by_entity_type"]["chapter_block"] >= 1
    assert db.query(ContentVersion).filter(ContentVersion.id == orphan.id).count() == 1


def test_purge_orphans_removes_them_on_confirm(admin_client: TestClient, db: Session):
    orphan = ContentVersion(
        id=uuid.uuid4(),
        entity_type="quiz_option",
        entity_id=str(uuid.uuid4()),
        field="option_text",
        locale="de",
        text="Vier Jahrhunderte",
        origin="mt",
        status="ok",
        source_locale="ru",
        source_hash="d" * 64,
    )
    db.add(orphan)
    db.commit()
    orphan_id = orphan.id

    resp = admin_client.post("/api/v1/admin/translations/purge-orphans", json={"confirm": True})

    assert resp.status_code == 200, resp.text
    assert resp.json()["removed"] >= 1
    assert db.query(ContentVersion).filter(ContentVersion.id == orphan_id).count() == 0


def test_purge_orphans_leaves_a_row_whose_entity_exists(admin_client: TestClient, db: Session):
    """The point of the endpoint is what it does NOT touch."""
    kept = _seed_needs_review(db)
    kept_id, kept_entity_id = kept.id, kept.entity_id
    # Give it a real entity to belong to.
    from app.models.daily_challenge import DailyChallengeQuestion

    db.add(
        DailyChallengeQuestion(
            id=uuid.UUID(kept_entity_id),
            question_type="multiple_choice",
            bible_book="Romans",
            bible_chapter=1,
            status="draft",
        )
    )
    db.commit()

    resp = admin_client.post("/api/v1/admin/translations/purge-orphans", json={"confirm": True})

    assert resp.status_code == 200, resp.text
    assert db.query(ContentVersion).filter(ContentVersion.id == kept_id).count() == 1


def test_purge_orphans_is_admin_only(student_client: TestClient):
    resp = student_client.post("/api/v1/admin/translations/purge-orphans", json={})
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# restore-last-good — undo a supersede that cost readers a translation
# ---------------------------------------------------------------------------


def _seed_superseded_good(db: Session, *, locale: str = "en") -> tuple[ContentVersion, ContentVersion]:
    """A servable row that a rejected retry pushed out of the way.

    Built through the write path rather than by hand, so the chain is
    the one production actually produced: a good translation, then a
    rejected answer to a *changed* source, which still supersedes.
    """
    entity_id = str(uuid.uuid4())
    good = record_mt_version(
        db,
        entity_type="chapter_block",
        entity_id=entity_id,
        field="content",
        locale=locale,
        text="<p>Grace is unearned favour.</p>",
        source_locale="ru",
        source_hash="a" * 64,
    )
    db.commit()
    rejected = record_mt_version(
        db,
        entity_type="chapter_block",
        entity_id=entity_id,
        field="content",
        locale=locale,
        text="<p>Grace is <em>unearned</em> favour.</p>",
        source_locale="ru",
        source_hash="b" * 64,
        status="failed",
        review_reason="[markup_mismatch] source has 1 tag, translation has 2",
    )
    db.commit()
    db.refresh(good)
    db.refresh(rejected)
    return good, rejected


def test_restore_last_good_puts_the_translation_back(admin_client: TestClient, db: Session):
    """One chapter block of «Glossary in Your Pocket» sat like this from
    2026-08-19: correct English translation, superseded by a retry that
    added two ``<em>`` and was parked. Readers got nothing while the good
    text sat one row below in the same table."""
    good, rejected = _seed_superseded_good(db)

    resp = admin_client.post(
        "/api/v1/admin/translations/restore-last-good",
        json={"ids": [str(rejected.id)]},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["reset"] == 1
    db.refresh(good)
    db.refresh(rejected)
    assert good.superseded_by is None
    assert good.status == "ok"
    # Nothing is deleted: what the model said is still readable, now
    # standing behind the row it briefly replaced.
    assert rejected.superseded_by == good.id
    assert "<em>" in rejected.text


def test_restore_last_good_leaves_a_servable_row_alone(admin_client: TestClient, db: Session):
    """A row that is already ``ok`` is not something to restore from."""
    good, _rejected = _seed_superseded_good(db)
    resp = admin_client.post(
        "/api/v1/admin/translations/restore-last-good",
        json={"ids": [str(good.id)]},
    )
    assert resp.status_code == 404


def test_restore_last_good_refuses_when_there_is_nothing_behind(admin_client: TestClient, db: Session):
    """A first-ever attempt that failed superseded nothing. There is no
    earlier translation to put back, and saying so is better than
    inventing one."""
    row = _seed_needs_review(db)
    resp = admin_client.post(
        "/api/v1/admin/translations/restore-last-good",
        json={"ids": [str(row.id)]},
    )
    assert resp.status_code == 404


def test_restore_last_good_is_admin_only(student_client: TestClient):
    resp = student_client.post(
        "/api/v1/admin/translations/restore-last-good",
        json={"ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# retry-reviewed by id — one row, named by the person reading it
# ---------------------------------------------------------------------------


def test_retry_reviewed_can_name_one_row(admin_client: TestClient, db: Session):
    """Retrying from the review queue is a decision about the row the
    reviewer is looking at. The narrowest request this endpoint used to
    accept was "every parked row of this entity type in this language" —
    far too much collateral for a button beside a single line of text."""
    mine = _seed_needs_review(db)
    bystander = _seed_needs_review(db)

    resp = admin_client.post(
        "/api/v1/admin/translations/retry-reviewed",
        json={"ids": [str(mine.id)]},
    )

    assert resp.status_code == 200
    assert resp.json() == {"reset": 1}
    db.refresh(mine)
    db.refresh(bystander)
    assert mine.status == "failed"
    assert bystander.status == "needs_review"


def test_retry_reviewed_by_id_still_refuses_a_persons_own_translation(admin_client: TestClient, db: Session):
    """Naming a row explicitly does not buy past the guard: an id is not
    an argument that the pipeline should redo someone's own typing."""
    human = _seed_needs_review(db, origin="human")

    resp = admin_client.post(
        "/api/v1/admin/translations/retry-reviewed",
        json={"ids": [str(human.id)]},
    )

    assert resp.status_code == 404
    db.refresh(human)
    assert human.status == "needs_review"


def test_retry_reviewed_refuses_a_request_that_selects_nothing(admin_client: TestClient):
    """An empty body would otherwise mean "every parked row on the
    platform", which is not a request anybody makes on purpose."""
    resp = admin_client.post("/api/v1/admin/translations/retry-reviewed", json={})

    assert resp.status_code == 422
