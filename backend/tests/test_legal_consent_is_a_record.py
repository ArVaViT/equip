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

from app.legal import LEGAL_DOCUMENTS, LOCALES, document_for, required_slugs
from app.legal.registry import REFERENCE_DOCUMENTS
from app.models.legal_acceptance import LegalAcceptance

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID

DOCS = "/api/v1/legal/documents"
ACCEPT = "/api/v1/legal/acceptances"
MINE = "/api/v1/legal/acceptances/me"


def test_every_document_exists_in_every_language_the_interface_serves() -> None:
    # A missing translation is a broken deployment, not a fallback to English:
    # half this school reads Russian, and a policy they cannot read is not a
    # policy they can accept. The interface has served four languages for a
    # year; these documents caught up on 2026-09-17.
    for slug in LEGAL_DOCUMENTS:
        for locale in LOCALES:
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
    response = student_client.post(
        ACCEPT, json={"slug": "privacy", "version": LEGAL_DOCUMENTS["privacy"], "locale": "ru"}
    )
    assert response.status_code == 201

    row = db.query(LegalAcceptance).filter(LegalAcceptance.user_id == STUDENT_ID).one()
    assert row.document_slug == "privacy"
    assert row.version == LEGAL_DOCUMENTS["privacy"]
    assert row.locale == "ru"
    # The fingerprint is of the server's copy, so the record attests to the
    # document that actually exists rather than whatever a client claimed.
    assert row.content_sha256 == document_for("privacy", "ru").sha256


def test_accepting_twice_is_not_two_consents(student_client: TestClient, db: Session) -> None:
    payload = {"slug": "privacy", "version": LEGAL_DOCUMENTS["privacy"], "locale": "ru"}
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
    student_owes = set(required_slugs("student"))
    before = student_client.get(MINE).json()
    assert {d["slug"] for d in before["outstanding"]} == student_owes

    student_client.post(ACCEPT, json={"slug": "privacy", "version": LEGAL_DOCUMENTS["privacy"], "locale": "ru"})
    after = student_client.get(MINE).json()

    # The gate asks one question — "is there anything left" — and the server
    # answers it, rather than the client reconstructing it by comparing lists.
    assert {d["slug"] for d in after["outstanding"]} == student_owes - {"privacy"}
    assert [a["slug"] for a in after["accepted"]] == ["privacy"]


def test_a_student_is_never_shown_the_teacher_agreement(student_client: TestClient) -> None:
    # Two tests rather than one, because the client fixtures share a single
    # ``get_current_user`` override and the last one requested wins — asking
    # for both in one test would have both answers come back as the teacher's.
    assert "teacher-terms" not in {d["slug"] for d in student_client.get(MINE).json()["outstanding"]}


def test_a_teacher_cannot_get_past_the_teacher_agreement(client: TestClient) -> None:
    # The reason the status route reads the role off the profile row rather
    # than trusting the caller: this is the answer a promotion changes.
    assert "teacher-terms" in {d["slug"] for d in client.get(MINE).json()["outstanding"]}


def test_the_summary_carries_what_the_gate_needs_to_decide(anon_client: TestClient) -> None:
    # Which roles owe it, and whether this version asks for a signature —
    # both off the registry, so no client has to reconstruct either.
    documents = {d["slug"]: d for d in anon_client.get(DOCS).json()}
    assert documents["teacher-terms"]["required_for"] == ["admin", "director", "teacher"]
    assert sorted(documents["privacy"]["required_for"]) == ["admin", "director", "student", "teacher"]
    assert documents["terms"]["requires_consent"] is True
    assert documents["terms"]["effective"] == "2026-09-17"
    assert "providers" not in documents


def test_a_person_who_is_up_to_date_owes_nothing_and_is_told_nothing(student_client: TestClient) -> None:
    for slug in required_slugs("student"):
        student_client.post(ACCEPT, json={"slug": slug, "version": LEGAL_DOCUMENTS[slug], "locale": "ru"})

    status = student_client.get(MINE).json()
    assert status["outstanding"] == []
    assert status["notices"] == []


def test_the_locale_recorded_is_the_one_they_read(student_client: TestClient, db: Session) -> None:
    student_client.post(ACCEPT, json={"slug": "terms", "version": LEGAL_DOCUMENTS["terms"], "locale": "en"})

    row = db.query(LegalAcceptance).filter(LegalAcceptance.document_slug == "terms").one()
    assert row.locale == "en"
    assert row.content_sha256 == document_for("terms", "en").sha256
    # And the two translations are genuinely different texts, so recording
    # which one was read is not bookkeeping for its own sake.
    assert document_for("terms", "en").sha256 != document_for("terms", "ru").sha256


class TestTheLanguageAPersonIsActuallyReading:
    """The platform speaks four languages, and now so do these documents.

    A German or Ukrainian reader used to be handed the *Russian* privacy
    policy — the frontend collapsed every non-English language to ``ru`` —
    which is a text they cannot read, presented as the thing they are
    agreeing to. Then they were handed the English one with a line
    apologising for it, which is better and still not the document in their
    language. Since 2026-09-17 every document exists in all four, and the
    response says which one it sent, because a page cannot tell somebody
    what they are reading unless the server tells the page.
    """

    def test_every_language_the_interface_serves_gets_its_own_text(self, anon_client: TestClient) -> None:
        bodies = {}
        for locale in LOCALES:
            body = anon_client.get(f"{DOCS}/privacy", params={"locale": locale}).json()
            assert body["locale"] == locale
            bodies[locale] = body["body"]
        # Four genuinely different texts, not four copies of one. A parity
        # check that counts files would pass on four identical English ones.
        assert len(set(bodies.values())) == len(LOCALES)

    def test_a_language_we_do_not_serve_gets_the_governing_text(self, anon_client: TestClient) -> None:
        english = anon_client.get(f"{DOCS}/privacy", params={"locale": "en"}).json()
        body = anon_client.get(f"{DOCS}/privacy", params={"locale": "fr"}).json()
        assert body["locale"] == "en"
        assert body["body"] == english["body"]

    def test_a_bare_request_is_not_answered_in_russian(self, anon_client: TestClient) -> None:
        # The default used to be ``ru``, which made the language a person got
        # depend on whether the client remembered to ask.
        assert anon_client.get(f"{DOCS}/terms").json()["locale"] == "en"

    def test_the_record_names_the_text_they_saw(self, student_client: TestClient, db: Session) -> None:
        response = student_client.post(
            ACCEPT, json={"slug": "privacy", "version": LEGAL_DOCUMENTS["privacy"], "locale": "de"}
        )
        assert response.status_code == 201
        assert response.json()["locale"] == "de"

        row = db.query(LegalAcceptance).filter_by(user_id=STUDENT_ID, document_slug="privacy").one()
        assert row.locale == "de"
        # And the fingerprint is of the German text, so "you agreed to this"
        # points at the words this person actually read.
        assert row.content_sha256 == hashlib.sha256(document_for("privacy", "de").body.encode()).hexdigest()


class TestAReferencePageIsNotAContract:
    """The providers list is read, never signed.

    It exists so that swapping a supplier does not ask a hundred people
    to agree to a policy whose promises have not moved. That only works
    if the platform never asks for it: a reference page in the consent
    gate would train people to click through consent screens, which is
    the opposite of what consent is for.
    """

    def test_it_is_served_like_any_other_page(self, anon_client: TestClient) -> None:
        response = anon_client.get(f"{DOCS}/providers")

        assert response.status_code == 200
        body = response.json()
        # The date it last changed, carried in the field a signed
        # document uses for its version.
        assert body["version"] == REFERENCE_DOCUMENTS["providers"]
        assert "Resend" in body["body"]

    def test_it_is_never_asked_for(self) -> None:
        assert "providers" not in required_slugs()

    def test_it_exists_in_every_locale_the_policy_does(self, anon_client: TestClient) -> None:
        # A person reading the policy in their own language and following its
        # link must not land in another one.
        for locale in LOCALES:
            assert anon_client.get(f"{DOCS}/providers?locale={locale}").json()["locale"] == locale

    def test_accepting_it_is_refused(self, student_client: TestClient) -> None:
        """Even if a stale page or a curious caller tries.

        It has no version to accept, and the acceptance route must not
        invent one.
        """
        response = student_client.post(
            ACCEPT, json={"slug": "providers", "version": REFERENCE_DOCUMENTS["providers"], "locale": "en"}
        )

        assert response.status_code in (400, 409, 422)
