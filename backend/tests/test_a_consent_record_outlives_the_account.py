"""An acceptance that has lost its person is still an acceptance, and stays out of sight.

The row survives account deletion with the person taken out of it — ``user_id``
NULL, the IP erased, a one-way fingerprint of the account id left behind. That
part is a database trigger, and the assertions for it are in
``supabase/ci/consent_survives_deletion_assertions.sql``, run against real
Postgres by the schema-replay job: these tests run on SQLite and cannot see a
trigger.

What SQLite *can* answer is the other half, and it is the half that would leak:
now that a row can exist with no owner, no route may hand it to anybody, and no
count may be thrown off by it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.legal import LEGAL_DOCUMENTS, required_slugs
from app.models.legal_acceptance import LegalAcceptance

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID

ACCEPT = "/api/v1/legal/acceptances"
MINE = "/api/v1/legal/acceptances/me"

#: What the trigger leaves behind. sha256 of some account id that is gone.
ORPHAN_FINGERPRINT = "9f2c8b1e" * 8


def _orphan(slug: str, version: str) -> LegalAcceptance:
    """A row whose person has been deleted, as the trigger leaves it."""
    return LegalAcceptance(
        user_id=None,
        document_slug=slug,
        version=version,
        locale="ru",
        content_sha256="0" * 64,
        ip=None,
        subject_hash=ORPHAN_FINGERPRINT,
    )


def test_a_row_can_outlive_its_person(db: Session) -> None:
    # ``user_id`` was NOT NULL with ON DELETE CASCADE until 2026-09-17, which
    # is why deleting an account destroyed the evidence rather than anonymising
    # it. The column has to accept the absence for the trigger to have anywhere
    # to put it.
    db.add(_orphan("privacy", LEGAL_DOCUMENTS["privacy"]))
    db.commit()

    row = db.query(LegalAcceptance).one()
    assert row.user_id is None
    assert row.ip is None
    assert row.subject_hash == ORPHAN_FINGERPRINT
    # And the five things the record is kept for are all still there.
    assert row.document_slug == "privacy"
    assert row.version == LEGAL_DOCUMENTS["privacy"]
    assert row.locale == "ru"
    assert row.content_sha256
    assert row.accepted_at is not None


def test_two_people_who_left_do_not_collide_on_the_same_version(db: Session) -> None:
    # The unique constraint is (user_id, document_slug, version), and both
    # SQLite and Postgres treat NULLs as distinct. Two people who accepted the
    # same version and then deleted their accounts must both leave a trace.
    first = _orphan("privacy", LEGAL_DOCUMENTS["privacy"])
    second = _orphan("privacy", LEGAL_DOCUMENTS["privacy"])
    second.subject_hash = "1a2b3c4d" * 8
    db.add_all([first, second])
    db.commit()

    assert db.query(LegalAcceptance).count() == 2


def test_an_orphaned_row_is_nobody_s_acceptance(student_client: TestClient, db: Session) -> None:
    # The status route selects by user_id, so a row with none cannot match —
    # but "cannot" is worth a test rather than a reading, because the shape of
    # that query is what stands between a deleted person's record and a live
    # person's screen.
    db.add(_orphan("privacy", LEGAL_DOCUMENTS["privacy"]))
    db.add(_orphan("terms", LEGAL_DOCUMENTS["terms"]))
    db.commit()

    status = student_client.get(MINE).json()

    assert status["accepted"] == []
    # And the student still owes everything: somebody else's surviving record
    # must not answer for them.
    assert {d["slug"] for d in status["outstanding"]} == set(required_slugs("student"))


def test_an_orphaned_row_does_not_block_a_living_person_from_accepting(student_client: TestClient, db: Session) -> None:
    # The idempotency path on the accept route looks up an existing row by
    # (user, slug, version). An orphan shares the slug and version and has no
    # user, so a query that forgot the user would find it and return somebody
    # else's timestamp as this person's consent.
    db.add(_orphan("privacy", LEGAL_DOCUMENTS["privacy"]))
    db.commit()

    response = student_client.post(
        ACCEPT, json={"slug": "privacy", "version": LEGAL_DOCUMENTS["privacy"], "locale": "ru"}
    )

    assert response.status_code == 201
    mine = db.query(LegalAcceptance).filter(LegalAcceptance.user_id == STUDENT_ID).one()
    assert mine.subject_hash is None
    assert db.query(LegalAcceptance).count() == 2


def test_a_living_acceptance_carries_no_fingerprint(student_client: TestClient, db: Session) -> None:
    # ``subject_hash`` is written at deletion, not at insert. Filling it while
    # the account exists would store a second identifier for a person we
    # already identify by ``user_id`` — more data, for nothing.
    student_client.post(ACCEPT, json={"slug": "terms", "version": LEGAL_DOCUMENTS["terms"], "locale": "ru"})

    row = db.query(LegalAcceptance).one()
    assert row.subject_hash is None
