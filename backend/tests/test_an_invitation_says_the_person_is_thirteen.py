"""Below thirteen the platform does not want the account, and says so out loud.

The Privacy Policy has always said you can register yourself from 16 and that
anyone younger comes in through a school administrator. It set no floor under
the second half, so as written an administrator could open an account for a
nine-year-old and nothing in the product would notice.

The owner's decision of 2026-09-17 puts the floor at thirteen. Under thirteen
turns COPPA on, and COPPA is verifiable parental consent, a parental
records-access duty, a deletion duty and a direct-notice duty — real
obligations with a real process behind them, and there is no process here.
There are nine teachers. Refusing the account is the honest answer and also
the cheap one.

What is collected is not a date of birth. Asking one would mean holding a
piece of personal data about a child in order to protect children, and there
is no second use for it. What is collected is the statement of somebody who
knows the family, and a record of who made it.

These tests pin: the statement is required, "false" is refused as firmly as
"absent", the record names who and when, and a resend re-states rather than
echoing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.invitation import Invitation

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

INVITATIONS = "/api/v1/invitations"


def _invite(client: TestClient, email: str, **extra: object):
    body: dict[str, object] = {"email": email, "role": "student", "age_attested": True}
    body.update(extra)
    return client.post(INVITATIONS, json=body)


def test_an_invitation_without_the_statement_is_refused(admin_client: TestClient) -> None:
    response = admin_client.post(INVITATIONS, json={"email": "child@example.com", "role": "student"})

    assert response.status_code == 422, response.text


def test_saying_no_is_refused_as_firmly_as_saying_nothing(admin_client: TestClient) -> None:
    """The two are the same answer to the only question being asked.

    A ``False`` that was quietly recorded would leave a row asserting an
    invitation was written for somebody the sender would not vouch for.
    """
    response = _invite(admin_client, "child@example.com", age_attested=False)

    assert response.status_code == 422, response.text


def test_the_record_names_who_said_it_and_when(admin_client: TestClient, db: Session, admin: User) -> None:
    before = datetime.now(UTC)

    response = _invite(admin_client, "student@example.com")
    assert response.status_code == 201, response.text

    row = db.query(Invitation).filter(Invitation.email == "student@example.com").one()
    assert row.age_attested_by == admin.id
    assert row.age_attested_at is not None
    assert row.age_attested_at >= before.replace(tzinfo=row.age_attested_at.tzinfo)


def test_no_date_of_birth_is_asked_for_or_kept() -> None:
    """The one column shape this must never grow into.

    A birthday would be personal data about a child, collected to protect
    children, with no other use — and it would have to be held for as long as
    the account lives. The attestation answers the same question and holds
    nothing about the child at all.
    """
    columns = {column.name for column in Invitation.__table__.columns}

    assert not [name for name in columns if "birth" in name or name in {"age", "dob"}]


def test_the_response_carries_the_attestation_back(admin_client: TestClient) -> None:
    body = _invite(admin_client, "student@example.com").json()

    assert body["age_attested_at"] is not None


def test_a_resend_is_a_fresh_statement_by_whoever_clicked_it(
    admin_client: TestClient, db: Session, admin: User, teacher: User
) -> None:
    """Not an echo of the first one, and not necessarily the same person.

    What is stored is who last stood behind the invitation that is live —
    the only answer that is true at the moment somebody asks.
    """
    first = _invite(admin_client, "again@example.com")
    assert first.status_code == 201, first.text
    row = db.query(Invitation).filter(Invitation.email == "again@example.com").one()
    db.query(Invitation).filter(Invitation.id == row.id).update(
        {"age_attested_at": datetime(2020, 1, 1, tzinfo=UTC), "age_attested_by": teacher.id}
    )
    db.commit()

    second = _invite(admin_client, "again@example.com")

    assert second.status_code == 201, second.text
    db.expire_all()
    row = db.query(Invitation).filter(Invitation.email == "again@example.com").one()
    assert row.age_attested_by == admin.id
    assert row.age_attested_at is not None
    assert row.age_attested_at.year > 2020


def test_a_teacher_inviting_onto_their_own_course_states_it_too(client: TestClient, db: Session, teacher: User) -> None:
    """The floor is not an administrator's rule. Whoever writes the invitation
    is the person who knows the family, and is the person who says so."""
    from app.models.course import Course

    db.add(Course(id="age-course", status="published", created_by=teacher.id))
    db.commit()

    refused = client.post(
        INVITATIONS,
        json={"email": "pupil@example.com", "role": "student", "scope": "course", "course_id": "age-course"},
    )
    assert refused.status_code == 422, refused.text

    allowed = _invite(client, "pupil@example.com", scope="course", course_id="age-course")
    assert allowed.status_code == 201, allowed.text
    assert db.query(Invitation).filter(Invitation.email == "pupil@example.com").one().age_attested_by == teacher.id


def test_the_audit_log_keeps_the_statement_too(admin_client: TestClient, db: Session) -> None:
    """A column can be dropped by a migration; the audit line survives it."""
    from app.models.audit_log import AuditLog

    _invite(admin_client, "audited@example.com")

    row = (
        db.query(AuditLog)
        .filter(AuditLog.resource_type == "invitation", AuditLog.action == "create")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert row is not None
    assert row.details is not None
    assert row.details.get("age_attested") is True


def test_half_an_attestation_cannot_be_stored(db: Session) -> None:
    """An attestation with no attester answers "who said so" with silence,
    which is the one question the record is kept to answer."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    db.add(
        Invitation(
            email="half@example.com",
            role="student",
            token="half-token",
            age_attested_at=datetime.now(UTC),
            age_attested_by=None,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
