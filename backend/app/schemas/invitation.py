from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas._request import RequestModel

# Mirrors the Postgres CHECK constraints on invitations.role / .status
# (see supabase/migrations/20260707120000_add_invitations_table.sql) and
# the SQLAlchemy model's CheckConstraints. Deliberately excludes "admin" --
# an invite can never grant admin, only the manual role-change route can.
InvitationRoleLiteral = Literal["teacher", "student"]
InvitationStatusLiteral = Literal["pending", "accepted", "revoked"]
# Mirrors chk_invitations_scope. What accepting grants: an account, a
# membership, or a membership plus a seat on one course.
InvitationScopeLiteral = Literal["platform", "organization", "course"]


class InvitationCreate(RequestModel):
    email: EmailStr
    role: InvitationRoleLiteral
    #: Defaults to the shape every invitation had before scopes existed,
    #: so a client that predates this field keeps working unchanged.
    scope: InvitationScopeLiteral = "organization"
    course_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _course_matches_scope(self) -> "InvitationCreate":
        """Reject the two shapes the database would reject anyway.

        Doing it here turns a 500 from a CHECK violation into a 422 that
        names the field, and keeps the contract honest in the OpenAPI
        document rather than only in Postgres.
        """
        if self.scope == "course" and not self.course_id:
            raise ValueError("course_id is required when scope is 'course'")
        if self.scope != "course" and self.course_id is not None:
            raise ValueError("course_id is only meaningful when scope is 'course'")
        return self


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: InvitationRoleLiteral
    scope: InvitationScopeLiteral
    course_id: str | None
    status: InvitationStatusLiteral
    invited_by: UUID | None
    created_at: datetime | None
    accepted_at: datetime | None
    expires_at: datetime
    # Derived, not stored -- a 'pending' row past its expiry is treated as
    # expired at read time rather than requiring a cron to flip a stored
    # status. Only meaningful when status == "pending".
    is_expired: bool


class InvitationPreview(BaseModel):
    """Public, token-scoped preview shown on the accept-invite page.

    Deliberately excludes ``id`` / ``invited_by`` -- the token alone
    should not let a caller enumerate other fields of the invite.

    ``course_title`` is the one piece of course data that crosses this
    line, and only for a course invitation: a person deciding whether to
    accept is entitled to know what they are being invited to, and the
    title is already public on a published course. The id stays out --
    it buys the reader nothing and it is a handle into other routes.
    """

    email: str
    role: InvitationRoleLiteral
    scope: InvitationScopeLiteral
    course_title: str | None = None
    status: InvitationStatusLiteral
    is_expired: bool


class InvitationAcceptRequest(RequestModel):
    token: str = Field(min_length=1, max_length=128)


class InvitationAcceptResponse(BaseModel):
    role: InvitationRoleLiteral
    #: What the acceptance actually did, so the page can say "you are
    #: enrolled" rather than guessing from the scope it asked for.
    scope: InvitationScopeLiteral
    enrolled_course_id: str | None = None
