"""Being told is not agreeing, and the two must not share a table.

The documents now promise two different things about two different kinds of
change: a material one asks for a signature, everything else is published and
announced. The announcement needs somewhere to remember it was made, and that
somewhere cannot be ``legal_acceptances`` — a row there asserts agreement, and
asserting agreement to a change nobody was asked about empties the table of
meaning.

These tests pin the boundary: a dismissal writes to ``legal_notices_seen`` and
nowhere else, the banner stops coming back on every device rather than only the
one it was closed on, and a notice-only version never becomes a gate.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import TYPE_CHECKING

import pytest

from app.legal import LEGAL_DOCUMENTS, LEGAL_REGISTRY, DocumentSpec, Revision, document_spec
from app.models.legal_acceptance import LegalAcceptance
from app.models.legal_notice_seen import LegalNoticeSeen

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID

ACCEPT = "/api/v1/legal/acceptances"
MINE = "/api/v1/legal/acceptances/me"
SEEN = "/api/v1/legal/notices/seen"


CORRECTION = "2.1"


@pytest.fixture
def publish_a_correction(monkeypatch: pytest.MonkeyPatch) -> Callable[[], str]:
    """Publish a notice-only 2.1 of the privacy policy, for this test only.

    Returned as a function rather than applied by the fixture, because the
    order is the scenario: somebody accepts 2.0, and *then* a correction ships
    under them. Applying it first would mean they never accepted anything —
    the acceptance route would refuse 2.0 as a version it no longer serves,
    which it should.

    A real correction would come with four edited files and four new
    fingerprints. What is under test is the mechanism, not the prose, so the
    registry is doctored and the files stay as they are.
    """

    def publish() -> str:
        from app.legal import registry as module

        privacy = document_spec("privacy")
        patched = dataclasses.replace(
            privacy,
            revisions=(*privacy.revisions, Revision(CORRECTION, date(2026, 10, 1), consent=False)),
        )
        doctored: tuple[DocumentSpec, ...] = tuple(s if s.slug != "privacy" else patched for s in LEGAL_REGISTRY)
        monkeypatch.setattr(module, "LEGAL_REGISTRY", doctored)
        monkeypatch.setattr(module, "_BY_SLUG", {s.slug: s for s in doctored})
        return CORRECTION

    return publish


def _accept_everything(client: TestClient) -> None:
    for slug, version in LEGAL_DOCUMENTS.items():
        if slug == "teacher-terms":
            continue
        client.post(ACCEPT, json={"slug": slug, "version": version, "locale": "ru"})


def test_a_correction_is_a_notice_and_not_a_gate(
    student_client: TestClient, publish_a_correction: Callable[[], str]
) -> None:
    _accept_everything(student_client)
    version = publish_a_correction()

    status = student_client.get(MINE).json()

    # The whole point. Under the old arrangement the only lever was a version
    # bump, so this correction would have met every account with a blocking
    # consent screen — and a consent screen people meet over corrections is a
    # consent screen people stop reading.
    assert status["outstanding"] == []
    assert [n["slug"] for n in status["notices"]] == ["privacy"]
    assert status["notices"][0]["version"] == version
    assert status["notices"][0]["requires_consent"] is False


def test_dismissing_a_notice_does_not_write_a_consent_row(
    student_client: TestClient, db: Session, publish_a_correction: Callable[[], str]
) -> None:
    _accept_everything(student_client)
    version = publish_a_correction()
    before = db.query(LegalAcceptance).count()

    response = student_client.post(SEEN, json={"slug": "privacy", "version": version})

    assert response.status_code == 204
    assert db.query(LegalAcceptance).count() == before
    row = db.query(LegalNoticeSeen).filter_by(user_id=STUDENT_ID, document_slug="privacy").one()
    assert row.version == version


def test_a_dismissed_notice_does_not_come_back_on_the_next_device(
    student_client: TestClient, publish_a_correction: Callable[[], str]
) -> None:
    _accept_everything(student_client)
    version = publish_a_correction()
    assert student_client.get(MINE).json()["notices"]

    student_client.post(SEEN, json={"slug": "privacy", "version": version})

    # Server-side rather than a browser flag, because a banner closed on a
    # phone waiting on the laptop teaches people to close banners unread.
    assert student_client.get(MINE).json()["notices"] == []


def test_being_told_twice_is_being_told(student_client: TestClient, db: Session) -> None:
    payload = {"slug": "privacy", "version": LEGAL_DOCUMENTS["privacy"]}
    assert student_client.post(SEEN, json=payload).status_code == 204
    assert student_client.post(SEEN, json=payload).status_code == 204
    assert db.query(LegalNoticeSeen).count() == 1


def test_a_notice_for_a_document_that_does_not_exist_is_a_404(student_client: TestClient) -> None:
    assert student_client.post(SEEN, json={"slug": "cookies", "version": "1.0"}).status_code == 404


def test_a_stale_tab_can_still_close_its_banner(student_client: TestClient) -> None:
    """Unlike accepting, which refuses a version we no longer serve.

    There is nothing to get wrong here: closing a banner about a superseded
    version is closing a banner, and refusing it would leave it on screen for
    as long as the tab stays open.
    """
    assert student_client.post(SEEN, json={"slug": "privacy", "version": "1.0"}).status_code == 204


def test_the_notice_record_keeps_no_address(student_client: TestClient, db: Session) -> None:
    # ``legal_acceptances.ip`` and ``submission_declarations.ip`` exist because
    # the privacy policy names those two moments and because they may one day
    # have to be proved. Closing a banner is neither, and 20260917031817
    # removed exactly this kind of incidental collection from ``audit_logs``.
    student_client.post(SEEN, json={"slug": "terms", "version": LEGAL_DOCUMENTS["terms"]})
    row = db.query(LegalNoticeSeen).one()
    assert not hasattr(row, "ip")
    assert not hasattr(row, "user_agent")
