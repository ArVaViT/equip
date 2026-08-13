"""Consent has to be a record of a specific text, not a tick in a browser.

Before this the first-run gate asked people to accept a privacy policy and
terms of use that did not exist, promised a full version in a footer that had
no link, and wrote the result to `localStorage`. Clearing a browser erased
every trace that anybody had agreed to anything; a second device never had one.

These tests pin the three properties that make the replacement worth having:
the documents are real and readable without an account, the record names the
version and fingerprints the text, and a stale page cannot manufacture consent
to something we no longer serve.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from app.legal import LEGAL_DOCUMENTS, document_for
from app.models.legal_acceptance import LegalAcceptance

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID

DOCS = "/api/v1/legal/documents"
ACCEPT = "/api/v1/legal/acceptances"
MINE = "/api/v1/legal/acceptances/me"


def test_every_document_exists_in_both_languages() -> None:
    # A missing translation is a broken deployment, not a fallback to English:
    # half this school reads Russian, and a policy they cannot read is not a
    # policy they can accept.
    for slug in LEGAL_DOCUMENTS:
        for locale in ("ru", "en"):
            doc = document_for(slug, locale)
            assert doc.body.strip(), f"{slug}.{locale} is empty"
            assert doc.version == LEGAL_DOCUMENTS[slug]


def test_the_documents_say_the_things_the_product_relies_on() -> None:
    # These are not stylistic assertions. Each of these three claims is made by
    # the product elsewhere, and a policy that contradicts it is worse than no
    # policy: the certificate survives account deletion, sixteen is the
    # self-registration floor, and we do not run AI detectors.
    privacy = document_for("privacy", "ru").body
    terms = document_for("terms", "ru").body
    assert "сертификат" in privacy.lower()
    assert "16" in privacy
    assert "детектор" in terms.lower()


def test_a_document_is_readable_without_an_account(anon_client: TestClient) -> None:
    # A policy you can only see after accepting it is not a policy.
    response = anon_client.get(f"{DOCS}/privacy", params={"locale": "ru"})
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == LEGAL_DOCUMENTS["privacy"]
    assert body["sha256"] == hashlib.sha256(body["body"].encode()).hexdigest()


def test_unknown_document_is_a_404_not_a_blank_page(anon_client: TestClient) -> None:
    assert anon_client.get(f"{DOCS}/cookies").status_code == 404


def test_accepting_records_the_version_and_the_hash(student_client: TestClient, db: Session) -> None:
    response = student_client.post(ACCEPT, json={"slug": "privacy", "version": "1.0", "locale": "ru"})
    assert response.status_code == 201

    row = db.query(LegalAcceptance).filter(LegalAcceptance.user_id == STUDENT_ID).one()
    assert row.document_slug == "privacy"
    assert row.version == "1.0"
    assert row.locale == "ru"
    # The fingerprint is of the server's copy, so the record attests to the
    # document that actually exists rather than whatever a client claimed.
    assert row.content_sha256 == document_for("privacy", "ru").sha256


def test_accepting_twice_is_not_two_consents(student_client: TestClient, db: Session) -> None:
    payload = {"slug": "privacy", "version": "1.0", "locale": "ru"}
    first = student_client.post(ACCEPT, json=payload)
    second = student_client.post(ACCEPT, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["accepted_at"] == second.json()["accepted_at"]
    assert db.query(LegalAcceptance).filter(LegalAcceptance.user_id == STUDENT_ID).count() == 1


def test_a_stale_page_cannot_manufacture_consent(student_client: TestClient, db: Session) -> None:
    # A tab left open across a deploy would otherwise write a row asserting
    # agreement to a version nobody can produce any more.
    response = student_client.post(ACCEPT, json={"slug": "privacy", "version": "0.9", "locale": "ru"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "legal.document_changed"
    assert db.query(LegalAcceptance).count() == 0


def test_status_says_what_is_still_outstanding(student_client: TestClient) -> None:
    before = student_client.get(MINE).json()
    assert {d["slug"] for d in before["outstanding"]} == set(LEGAL_DOCUMENTS)

    student_client.post(ACCEPT, json={"slug": "privacy", "version": "1.0", "locale": "ru"})
    after = student_client.get(MINE).json()

    # The gate asks one question — "is there anything left" — and the server
    # answers it, rather than the client reconstructing it by comparing lists.
    assert {d["slug"] for d in after["outstanding"]} == set(LEGAL_DOCUMENTS) - {"privacy"}
    assert [a["slug"] for a in after["accepted"]] == ["privacy"]


def test_the_locale_recorded_is_the_one_they_read(student_client: TestClient, db: Session) -> None:
    student_client.post(ACCEPT, json={"slug": "terms", "version": "1.0", "locale": "en"})

    row = db.query(LegalAcceptance).filter(LegalAcceptance.document_slug == "terms").one()
    assert row.locale == "en"
    assert row.content_sha256 == document_for("terms", "en").sha256
    # And the two translations are genuinely different texts, so recording
    # which one was read is not bookkeeping for its own sake.
    assert document_for("terms", "en").sha256 != document_for("terms", "ru").sha256
