"""An invitation whose person arrived without using its link.

The database closes such an invitation as ``fulfilled`` (migration
20260917023526): enrolling on the course, joining the organization or
signing up fires a trigger that runs one function. That rule is exercised
on a real Postgres by ``supabase/ci/invitation_fulfilment_assertions.sql``
in the schema-replay job -- these tests run on SQLite, which has no such
trigger, so here the row is put into the state the trigger leaves and the
application's side of the contract is pinned:

* the invitee can still use the link, because for a platform invitation
  signing up from the link *is* what fulfils it, moments before Accept;
* nobody else can;
* it cannot be revoked, for the same reason an accepted one cannot;
* the four places the status value is declared agree.
"""

from __future__ import annotations

import re
import typing
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.invitation import Invitation, InvitationScope, InvitationStatus
from app.models.user import User, UserRole
from app.schemas.invitation import InvitationStatusLiteral
from app.services.invitation_service import accept_invitation, revoke_invitation
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

REPO = Path(__file__).resolve().parents[2]
INVITEE_ID = uuid.UUID("f0f0f0f0-1111-2222-3333-f0f0f0f0f0f0")
INVITEE_EMAIL = "arrived@example.com"
COURSE_ID = "fulfilled-course"


def _invitee(db: Session) -> User:
    user = User(id=INVITEE_ID, email=INVITEE_EMAIL, full_name="Arrived", role=UserRole.STUDENT.value)
    db.add(user)
    db.commit()
    # The conftest hook files every new row under the test organization;
    # this person joined a public course by themselves and belongs nowhere.
    db.query(User).filter(User.id == INVITEE_ID).update({User.organization_id: None})
    db.commit()
    return user


def _course(db: Session) -> Course:
    course = Course(
        id=COURSE_ID,
        status="published",
        access_mode="public",
        created_by=ADMIN_ID,
        source_locale="en",
        organization_id=TEST_ORGANIZATION_ID,
    )
    db.add(course)
    db.commit()
    return course


def _fulfilled_course_invitation(db: Session) -> Invitation:
    """The row as the trigger leaves it: the person enrolled on their own."""
    db.add(Enrollment(id=str(uuid.uuid4()), user_id=INVITEE_ID, course_id=COURSE_ID, progress=0))
    invitation = Invitation(
        email=INVITEE_EMAIL,
        role=UserRole.STUDENT.value,
        scope=InvitationScope.COURSE.value,
        course_id=COURSE_ID,
        token=uuid.uuid4().hex,
        invited_by=ADMIN_ID,
        organization_id=TEST_ORGANIZATION_ID,
        status=InvitationStatus.FULFILLED.value,
        fulfilled_at=datetime.now(UTC),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


class TestTheInviteeCanStillUseTheLink:
    def test_accepting_grants_what_is_missing_and_keeps_the_status(self, db: Session, admin: User) -> None:
        _invitee(db)
        _course(db)
        invitation = _fulfilled_course_invitation(db)

        result = accept_invitation(
            db, token=invitation.token, current_user_id=INVITEE_ID, current_user_email=INVITEE_EMAIL
        )

        # Still "fulfilled": that is how the person actually arrived.
        assert result.status == InvitationStatus.FULFILLED.value
        assert result.accepted_at is None
        person = db.query(User).filter(User.id == INVITEE_ID).one()
        # The membership the course invitation also offered, which
        # enrolling on a public course by themselves did not give them.
        assert person.organization_id == TEST_ORGANIZATION_ID
        # And no second seat on the course.
        assert db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).count() == 1

    def test_somebody_else_cannot(self, db: Session, admin: User) -> None:
        _invitee(db)
        _course(db)
        invitation = _fulfilled_course_invitation(db)

        with pytest.raises(HTTPException) as exc:
            accept_invitation(
                db,
                token=invitation.token,
                current_user_id=INVITEE_ID,
                current_user_email="someone-else@example.com",
            )

        assert exc.value.status_code == 403


class TestTheSenderSeesIt:
    def test_it_cannot_be_revoked(self, db: Session, admin: User) -> None:
        _invitee(db)
        _course(db)
        invitation = _fulfilled_course_invitation(db)

        with pytest.raises(HTTPException) as exc:
            revoke_invitation(db, invitation_id=invitation.id, actor=admin, organization_id=None)

        assert exc.value.status_code == 409
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.FULFILLED.value

    def test_the_list_says_fulfilled_and_when(self, admin_client: TestClient, db: Session) -> None:
        _invitee(db)
        _course(db)
        _fulfilled_course_invitation(db)

        rows = admin_client.get("/api/v1/invitations", params={"status": "fulfilled"}).json()

        assert [r["email"] for r in rows] == [INVITEE_EMAIL]
        assert rows[0]["status"] == "fulfilled"
        assert rows[0]["fulfilled_at"] is not None
        assert rows[0]["accepted_at"] is None
        assert rows[0]["is_expired"] is False

    def test_the_status_and_its_timestamp_agree(self, db: Session, admin: User) -> None:
        _invitee(db)
        _course(db)
        invitation = _fulfilled_course_invitation(db)

        invitation.fulfilled_at = None
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestOneValueInFourPlaces:
    """AGENTS.md: a persisted enum value lives in the CHECK constraint, the
    Python enum and Literal, and the TypeScript union and accessor."""

    def test_every_declaration_names_the_same_statuses(self) -> None:
        python_enum = {s.value for s in InvitationStatus}
        python_literal = set(typing.get_args(InvitationStatusLiteral))

        schema = (REPO / "supabase" / "schema.sql").read_text(encoding="utf-8")
        check = re.search(r"CONSTRAINT invitations_status_check CHECK \(\(status = ANY \(ARRAY\[(.*?)\]\)\)\)", schema)
        assert check, "invitations_status_check not found in supabase/schema.sql"
        postgres = set(re.findall(r"'(\w+)'::text", check.group(1)))

        types_ts = (REPO / "frontend" / "src" / "types" / "index.ts").read_text(encoding="utf-8")
        union = re.search(r"export type InvitationStatus = ([^\n]+)", types_ts)
        assert union
        typescript = set(re.findall(r"'(\w+)'", union.group(1)))
        accessor = re.search(r"export const INVITATION_STATUSES = \{(.*?)\}", types_ts, re.DOTALL)
        assert accessor, "INVITATION_STATUSES accessor missing from frontend/src/types/index.ts"
        typescript_const = set(re.findall(r"'(\w+)'", accessor.group(1)))

        assert "fulfilled" in python_enum
        assert python_enum == python_literal == postgres == typescript == typescript_const

    def test_schema_sql_carries_the_rule_and_its_triggers(self) -> None:
        """schema.sql is hand-kept alongside the migration; this is the part
        of it the replay job's assertions depend on."""
        schema = (REPO / "supabase" / "schema.sql").read_text(encoding="utf-8")
        for name in (
            "FUNCTION public.fulfil_pending_invitations(p_profile_id uuid)",
            "FUNCTION public.fulfil_invitations_after_change()",
            "TRIGGER trg_enrollments_fulfil_invitations",
            "TRIGGER trg_profiles_created_fulfil_invitations",
            "TRIGGER trg_profiles_changed_fulfil_invitations",
            "TRIGGER trg_invitations_created_fulfil",
        ):
            assert name in schema, name
