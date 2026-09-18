"""When the supplier list moves, the people whose data it is find out.

The privacy policy names no suppliers. It points at ``providers`` — a page
read and never signed — and says that which company holds the database this
quarter is housekeeping rather than a new promise. That split is correct, and
the registry argues it at length: making a supplier swap a version bump brings
a hundred people back to a consent screen over something none of them agreed
to, and a consent screen people meet over housekeeping is a consent screen
people stop reading.

"You do not have to agree again" is not "you do not get to know". GDPR
Art. 28(2) gives a controller who granted general authorisation the right to be
*informed* of an addition or a replacement, and to object. The policy promises
it. Nothing kept it: ``notices_for`` walks ``required_slugs(role)``, which by
construction holds only documents somebody signs — so the one class of
document the notice mechanism was needed for was the one class it could never
reach, and changing the provider list told nobody at all.

These tests pin who is told, who is not, and that being told once is enough.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.legal.reference_notices import reference_notices_for
from app.legal.registry import LEGAL_REGISTRY, document_spec
from app.models.legal_acceptance import LegalAcceptance
from app.models.legal_notice_seen import LegalNoticeSeen

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

MINE = "/api/v1/legal/acceptances/me"
SEEN = "/api/v1/legal/notices/seen"

PROVIDERS = "providers"


@pytest.fixture(autouse=True)
def _they_arrive_having_signed_nothing(nobody_has_signed_anything: None) -> None:
    """These tests place the acceptances themselves, at chosen times.

    ``conftest._everybody_in_the_tests_has_already_signed`` hands every
    fabricated profile the current acceptances so that the several hundred
    tests which write something are not stopped at a consent screen they are
    not about. Here the acceptance date is the thing under test: who is told
    about a supplier change depends on whether they agreed before it.
    """


def _accept_everything(db: Session, user: User, *, on: datetime) -> None:
    """Put this person through the gate, at a moment of our choosing."""
    for spec in LEGAL_REGISTRY:
        if not spec.signable:
            continue
        db.add(
            LegalAcceptance(
                user_id=user.id,
                document_slug=spec.slug,
                version=spec.current.version,
                locale="en",
                content_sha256="hash",
                accepted_at=on,
            )
        )
    db.commit()


def _notice_slugs(client: TestClient) -> list[str]:
    response = client.get(MINE)
    assert response.status_code == 200, response.text
    return [notice["slug"] for notice in response.json()["notices"]]


def test_the_supplier_page_has_more_than_one_revision() -> None:
    """Otherwise every test below passes for the wrong reason."""
    assert len(document_spec(PROVIDERS).revisions) > 1


class TestWhoIsTold:
    def test_somebody_who_agreed_before_the_change_is_told(
        self, student_client: TestClient, db: Session, student: User
    ) -> None:
        before = datetime.combine(document_spec(PROVIDERS).current.effective, datetime.min.time(), UTC)
        _accept_everything(db, student, on=before - timedelta(days=30))

        assert PROVIDERS in _notice_slugs(student_client)

    def test_somebody_who_agreed_after_it_is_not(self, student_client: TestClient, db: Session, student: User) -> None:
        """They met the list on the screen that links to it. A banner saying it
        changed, to somebody who never saw the unchanged version, is noise —
        and noise is what teaches people to close banners unread."""
        after = datetime.combine(document_spec(PROVIDERS).current.effective, datetime.min.time(), UTC)
        _accept_everything(db, student, on=after + timedelta(days=1))

        assert PROVIDERS not in _notice_slugs(student_client)

    def test_somebody_who_has_agreed_to_nothing_is_not(self, student_client: TestClient) -> None:
        """They are about to meet the gate and do not need a banner in front of it."""
        assert PROVIDERS not in _notice_slugs(student_client)

    def test_it_reaches_a_teacher_the_same_way(self, client: TestClient, db: Session, teacher: User) -> None:
        """Not a student feature. Whose data it is, is everybody's."""
        before = datetime.combine(document_spec(PROVIDERS).current.effective, datetime.min.time(), UTC)
        _accept_everything(db, teacher, on=before - timedelta(days=30))

        assert PROVIDERS in _notice_slugs(client)


class TestBeingToldOnce:
    @pytest.fixture(autouse=True)
    def _agreed_long_ago(self, db: Session, student: User) -> None:
        before = datetime.combine(document_spec(PROVIDERS).current.effective, datetime.min.time(), UTC)
        _accept_everything(db, student, on=before - timedelta(days=30))

    def test_closing_it_stops_it_coming_back(self, student_client: TestClient) -> None:
        assert PROVIDERS in _notice_slugs(student_client)

        dismissed = student_client.post(
            SEEN,
            json={"slug": PROVIDERS, "version": document_spec(PROVIDERS).current.version},
        )
        assert dismissed.status_code == 204, dismissed.text

        assert PROVIDERS not in _notice_slugs(student_client)

    def test_it_is_recorded_as_a_telling_and_not_as_a_signature(
        self, student_client: TestClient, db: Session, student: User
    ) -> None:
        """A row in ``legal_acceptances`` would assert agreement to a page
        nobody was asked to agree to, which is how a consent table stops
        meaning anything."""
        student_client.post(
            SEEN,
            json={"slug": PROVIDERS, "version": document_spec(PROVIDERS).current.version},
        )

        told = db.query(LegalNoticeSeen).filter(LegalNoticeSeen.document_slug == PROVIDERS).all()
        signed = db.query(LegalAcceptance).filter(LegalAcceptance.document_slug == PROVIDERS).all()
        assert len(told) == 1
        assert signed == []


class TestTheRuleItself:
    """The decision, away from HTTP, so the edges are readable."""

    def test_nobody_is_told_who_has_agreed_to_nothing(self) -> None:
        assert reference_notices_for(None, set()) == ()

    def test_a_page_already_seen_is_not_repeated(self) -> None:
        spec = document_spec(PROVIDERS)

        told = reference_notices_for(date(2020, 1, 1), {(spec.slug, spec.current.version)})

        assert told == ()

    def test_only_pages_nobody_signs_come_through_here(self) -> None:
        """The signed ones are ``notices_for``'s answer, and a document
        arriving from both would be announced twice."""
        specs = reference_notices_for(date(2020, 1, 1), set())

        assert specs
        assert all(not spec.signable for spec in specs)
