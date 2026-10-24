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

from app.legal import (
    LEGAL_DOCUMENT_FINGERPRINTS,
    LEGAL_DOCUMENTS,
    LEGAL_REGISTRY,
    DocumentSpec,
    Revision,
    document_spec,
)
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


CORRECTION = "2.2"

#: The day 2.1 takes effect. Pinned, because a notice is shown for a month after
#: that day and then not again: run on the real clock these tests would start
#: failing on 2027-01-15, saying nothing about the code.
THE_DAY_2_1_TAKES_EFFECT = date(2026, 12, 15)


def _today_is(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    from app.api.v1 import legal as route

    monkeypatch.setattr(route, "_today", lambda: day)


@pytest.fixture(autouse=True)
def _the_clock_stands_where_2_1_takes_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    _today_is(monkeypatch, THE_DAY_2_1_TAKES_EFFECT)


@pytest.fixture
def publish_a_correction(monkeypatch: pytest.MonkeyPatch) -> Callable[[], str]:
    """Publish a notice-only 2.2 of the privacy policy, for this test only.

    Returned as a function rather than applied by the fixture, because the
    order is the scenario: somebody accepts 2.1, and *then* a correction ships
    under them. Applying it first would mean they never accepted anything —
    the acceptance route would refuse 2.1 as a version it no longer serves,
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
            revisions=(*privacy.revisions, Revision(CORRECTION, date(2027, 1, 1), consent=False)),
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


# ── The real 2.1, not a doctored one ───────────────────────────────────


def test_the_account_deletion_edit_does_not_bring_anybody_back_to_the_gate(
    student_client: TestClient, db: Session
) -> None:
    """Everybody who signed 2.0 is told about 2.1 and asked for nothing.

    2026-10-16: the privacy policy and the terms were rewritten to describe
    the delete button on the profile — it closes and hides, erases nothing —
    beside the erasure on request, which did not change. Production has
    every active account on 2.0. Had either revision been marked
    ``consent=True``, or had the version simply been bumped as it used to
    be, each of them would have met a blocking consent screen the next time
    they opened the app. This is that person, on the registry as shipped.

    The acceptance rows name 2.0 and a fingerprint of the 2.0 text: the
    gate decides by version index, never by comparing hashes with the text
    served now, and this would fail if it started to.
    """
    assert LEGAL_DOCUMENTS["privacy"] == "2.1"
    assert LEGAL_DOCUMENTS["terms"] == "2.1"

    db.query(LegalAcceptance).filter(LegalAcceptance.user_id == STUDENT_ID).delete()
    for slug in ("privacy", "terms"):
        db.add(
            LegalAcceptance(
                user_id=STUDENT_ID,
                document_slug=slug,
                version="2.0",
                locale="ru",
                content_sha256=LEGAL_DOCUMENT_FINGERPRINTS[(slug, "2.0", "ru")],
            )
        )
    db.commit()

    status = student_client.get(MINE).json()
    assert status["outstanding"] == []
    assert sorted((n["slug"], n["version"], n["requires_consent"]) for n in status["notices"]) == [
        ("privacy", "2.1", False),
        ("terms", "2.1", False),
    ]

    # And the gate itself, not only the status it reports: a write goes through.
    assert student_client.post("/api/v1/users/me/onboarding/complete").status_code == 200


def test_both_documents_published_on_2026_10_16_are_notices() -> None:
    for slug in ("privacy", "terms"):
        current = document_spec(slug).current
        assert current.version == "2.1"
        assert current.consent is False


# ── A notice stops a month after the revision takes effect ─────────────


def _signed_2_0(db: Session) -> None:
    db.query(LegalAcceptance).filter(LegalAcceptance.user_id == STUDENT_ID).delete()
    for slug in ("privacy", "terms"):
        db.add(
            LegalAcceptance(
                user_id=STUDENT_ID,
                document_slug=slug,
                version="2.0",
                locale="ru",
                content_sha256=LEGAL_DOCUMENT_FINGERPRINTS[(slug, "2.0", "ru")],
            )
        )
    db.commit()


@pytest.mark.parametrize(
    ("today", "told"),
    [
        pytest.param(date(2026, 10, 16), ["privacy", "terms"], id="the-day-it-was-published"),
        pytest.param(date(2026, 12, 14), ["privacy", "terms"], id="the-day-before-it-takes-effect"),
        pytest.param(date(2026, 12, 15), ["privacy", "terms"], id="the-day-it-takes-effect"),
        pytest.param(date(2027, 1, 14), ["privacy", "terms"], id="the-day-before-the-month-is-out"),
        pytest.param(date(2027, 1, 15), [], id="a-month-on"),
        pytest.param(date(2027, 1, 16), [], id="the-day-after-that"),
    ],
)
def test_a_notice_is_shown_until_a_month_after_the_revision_takes_effect(
    student_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch, today: date, told: list[str]
) -> None:
    """Somebody on 2.0 who never closes banners.

    Until 2026-10-23 they were told about 2.1 for ever. Now the server stops
    telling them a month after the day it took effect — by calendar date, on
    the platform's clock (UTC), the same clock ``effective`` is written in. The
    client is not consulted: nothing about the banner changed there.
    """
    _signed_2_0(db)
    _today_is(monkeypatch, today)

    status = student_client.get(MINE).json()

    assert status["outstanding"] == []
    assert sorted(n["slug"] for n in status["notices"]) == told


def test_an_expired_notice_was_not_quietly_marked_as_seen(
    student_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not shown is not the same as told: the record of who was told stays what
    # it was, so the two tables keep answering different questions.
    _signed_2_0(db)
    _today_is(monkeypatch, date(2027, 2, 1))

    assert student_client.get(MINE).json()["notices"] == []
    assert db.query(LegalNoticeSeen).count() == 0
