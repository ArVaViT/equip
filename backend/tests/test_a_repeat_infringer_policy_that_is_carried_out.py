"""The policy is a count, and the count is enforced by the code that keeps it.

§ 512(i)(1)(A) asks for three things: a repeat-infringer policy, notice of it,
and reasonable implementation. The third is the one platforms lose.

BMG v. Cox (4th Cir. 2018): a written thirteen-step policy ending in
termination, and the safe harbour taken away anyway, because the record showed
the last step was essentially never taken. The document was fine.

Ventura Content v. Motherless (9th Cir. 2018): one person, no ticketing
system, no compliance department, safe harbour kept — because there was a
simple procedure, it was followed, and there was a record of having followed
it. Small was never the problem.

So these tests are about the third clause. The published rule is that more
than two upheld complaints against one person closes the account; what is
pinned here is that the third upheld complaint actually closes it, in the same
transaction as the decision, without anybody remembering to.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from app.core.errors import ErrorCode, equip_error
from app.models.user import User, UserRole

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

COMPLAINTS = "/api/v1/admin/dmca/complaints"


def _an_uploader(db: Session, email: str = "uploader@example.com") -> User:
    user = User(id=uuid.uuid4(), email=email, full_name="Teacher Who Uploaded", role=UserRole.TEACHER.value)
    db.add(user)
    db.commit()
    return user


def _notice(uploader: User | None = None, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "complainant_name": "Jane Rightsholder",
        "complainant_email": "jane@publisher.example",
        "complainant_organization": "Example Press",
        "work_described": "The Cross of Christ, chapter 4",
        "material_location": "https://equipbible.com/courses/acts/lesson-3",
    }
    if uploader is not None:
        body["uploaded_by"] = str(uploader.id)
    body.update(extra)
    return body


def _uphold(client: TestClient, complaint_id: str, **extra: object):
    body: dict[str, object] = {"status": "upheld", "uploader_notified": True}
    body.update(extra)
    return client.patch(f"{COMPLAINTS}/{complaint_id}", json=body)


class TestTheRecord:
    def test_a_complaint_keeps_who_complained_about_what(self, admin_client: TestClient, db: Session) -> None:
        uploader = _an_uploader(db)

        response = admin_client.post(COMPLAINTS, json=_notice(uploader))

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["complainant_name"] == "Jane Rightsholder"
        assert body["work_described"] == "The Cross of Christ, chapter 4"
        assert body["material_location"].endswith("/lesson-3")
        assert body["uploaded_by"] == str(uploader.id)
        assert body["status"] == "received"

    def test_it_also_records_that_the_uploader_was_told(self, admin_client: TestClient, db: Session) -> None:
        """§ 512(g) turns on the uploader being able to answer, and they
        cannot answer a complaint nobody mentioned to them."""
        uploader = _an_uploader(db)
        created = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()

        decided = _uphold(admin_client, created["id"]).json()

        assert decided["uploader_notified_at"] is not None

    def test_a_decision_names_the_person_who_made_it(self, admin_client: TestClient, db: Session, admin) -> None:
        created = admin_client.post(COMPLAINTS, json=_notice(_an_uploader(db))).json()

        decided = _uphold(admin_client, created["id"], resolution_note="Agreed; the extract came down.").json()

        assert decided["resolved_by"] == str(admin.id)
        assert decided["resolved_at"] is not None
        assert decided["resolution_note"] == "Agreed; the extract came down."

    def test_a_complaint_about_material_nobody_can_be_tied_to_is_still_filed(self, admin_client: TestClient) -> None:
        """It counts toward nobody, and it is still worth having on file."""
        response = admin_client.post(COMPLAINTS, json=_notice(None))

        assert response.status_code == 201, response.text
        assert response.json()["uploaded_by"] is None

    def test_the_ledger_is_not_a_public_surface(self, student_client: TestClient, anon_client: TestClient) -> None:
        """The rows name a complainant and a member of the school."""
        assert student_client.get(COMPLAINTS).status_code == 403
        assert anon_client.get(COMPLAINTS).status_code in (401, 403)


class TestTheCount:
    def test_each_upheld_complaint_gets_its_place_in_the_sequence(self, admin_client: TestClient, db: Session) -> None:
        uploader = _an_uploader(db)

        strikes = []
        for _ in range(2):
            created = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()
            strikes.append(_uphold(admin_client, created["id"]).json()["strike_number"])

        assert strikes == [1, 2]

    def test_a_rejected_complaint_counts_toward_nothing(self, admin_client: TestClient, db: Session) -> None:
        """Counting notices rather than findings is how somebody's account is
        closed by three complaints that were all wrong."""
        uploader = _an_uploader(db)
        created = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()

        decided = admin_client.patch(
            f"{COMPLAINTS}/{created['id']}",
            json={"status": "rejected", "resolution_note": "Public domain."},
        ).json()

        assert decided["strike_number"] is None
        assert decided["uploader_upheld_count"] == 0

    def test_the_running_count_travels_with_every_row(self, admin_client: TestClient, db: Session) -> None:
        """The question somebody reading this screen is asking is not "what
        happened to this one" but "how many times has this been this person"."""
        uploader = _an_uploader(db)
        first = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()
        _uphold(admin_client, first["id"])
        admin_client.post(COMPLAINTS, json=_notice(uploader))

        rows = admin_client.get(COMPLAINTS).json()

        assert {row["uploader_upheld_count"] for row in rows} == {1}


class TestTheThreshold:
    def test_two_upheld_complaints_do_not_close_the_account(self, admin_client: TestClient, db: Session) -> None:
        uploader = _an_uploader(db)

        for _ in range(2):
            created = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()
            _uphold(admin_client, created["id"])

        db.expire_all()
        assert db.get(User, uploader.id).deactivated_at is None

    def test_the_third_one_closes_it_without_anybody_pressing_a_button(
        self, admin_client: TestClient, db: Session
    ) -> None:
        """This is the whole exercise.

        Cox had a policy whose last step was never taken. The difference here
        is that the closure happens in the same transaction as the decision —
        there is no later step for anybody to not take.
        """
        uploader = _an_uploader(db)

        for _ in range(3):
            created = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()
            decided = _uphold(admin_client, created["id"]).json()

        assert decided["strike_number"] == 3
        assert decided["uploader_account_closed"] is True
        db.expire_all()
        assert db.get(User, uploader.id).deactivated_at is not None

    def test_the_closure_is_the_one_the_auth_gate_already_refuses(self, admin_client: TestClient, db: Session) -> None:
        """A closure that leaves the session working is a label, not a closure.

        ``deactivated_at`` is the column ``get_current_user`` checks before it
        hands back a user — see ``test_api_dependencies``. This test is here so
        that the path which closes an account keeps writing the column that
        gate reads, rather than inventing a second kind of closed.
        """
        uploader = _an_uploader(db)
        for _ in range(3):
            created = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()
            _uphold(admin_client, created["id"])

        db.expire_all()
        with pytest.raises(HTTPException) as caught:
            _as_the_gate_sees_it(db.get(User, uploader.id))
        assert caught.value.detail["code"] == ErrorCode.ACCOUNT_DEACTIVATED.value

    def test_three_complaints_against_different_people_close_nobody(
        self, admin_client: TestClient, db: Session
    ) -> None:
        """The count is per person. It reads as obvious and it is the bug a
        global counter would have."""
        uploaders = [_an_uploader(db, f"up{index}@example.com") for index in range(3)]

        for uploader in uploaders:
            created = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()
            _uphold(admin_client, created["id"])

        db.expire_all()
        assert [db.get(User, one.id).deactivated_at for one in uploaders] == [None, None, None]


class TestTheLedgerCannotBeQuietlyRewritten:
    def test_a_decided_complaint_cannot_be_decided_again(self, admin_client: TestClient, db: Session) -> None:
        """A strike may already have closed an account. Renumbering the
        history afterwards would leave the ledger unable to explain a closure
        it caused; a mistake is corrected by a new row and a note."""
        created = admin_client.post(COMPLAINTS, json=_notice(_an_uploader(db))).json()
        _uphold(admin_client, created["id"])

        again = admin_client.patch(f"{COMPLAINTS}/{created['id']}", json={"status": "rejected"})

        assert again.status_code == 409, again.text

    def test_the_strike_number_stays_where_it_was_stamped(self, admin_client: TestClient, db: Session) -> None:
        uploader = _an_uploader(db)
        first = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()
        _uphold(admin_client, first["id"])
        second = admin_client.post(COMPLAINTS, json=_notice(uploader)).json()
        _uphold(admin_client, second["id"])

        rows = {row["id"]: row["strike_number"] for row in admin_client.get(COMPLAINTS).json()}

        assert rows[first["id"]] == 1
        assert rows[second["id"]] == 2

    def test_a_complaint_naming_an_account_that_does_not_exist_is_refused(self, admin_client: TestClient) -> None:
        response = admin_client.post(COMPLAINTS, json=_notice(None, uploaded_by=str(uuid.uuid4())))

        assert response.status_code == 404, response.text

    def test_the_decision_is_in_the_audit_log(self, admin_client: TestClient, db: Session) -> None:
        """A table can be dropped by a migration. The audit line survives it."""
        from app.models.audit_log import AuditLog

        created = admin_client.post(COMPLAINTS, json=_notice(_an_uploader(db))).json()
        _uphold(admin_client, created["id"])

        row = (
            db.query(AuditLog)
            .filter(AuditLog.resource_type == "dmca_complaint", AuditLog.action == "update")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        assert row is not None
        assert row.details["status"] == "upheld"
        assert row.details["strike_number"] == 1


def _as_the_gate_sees_it(user: User) -> User:
    """The one check ``get_current_user`` makes about a closed account.

    Copied rather than called because the dependency also needs a signed
    token and a Supabase round trip, and neither is what this is about.
    ``test_api_dependencies`` covers the gate itself.
    """
    if user.deactivated_at is not None:
        raise equip_error(
            ErrorCode.ACCOUNT_DEACTIVATED,
            status_code=403,
            message="This account has been deactivated",
        )
    return user
