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
# ``fulfilled``: the person got what the invitation offered another way
# (migration 20260917023526); ``accepted``: they used the link.
InvitationStatusLiteral = Literal["pending", "accepted", "revoked", "fulfilled"]
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
    #: The inviter's statement that this person is thirteen or older.
    #:
    #: Required, and required to be ``True``: a default would make it
    #: something the client can leave out, and an attestation nobody made is
    #: not an attestation. The client shows the sentence next to an unticked
    #: box; this is the server refusing to take the word for granted.
    #:
    #: Not a date of birth. Asking one would collect a piece of personal data
    #: about a child in order to protect children, and the platform has no
    #: use for it afterwards. What it needs is somebody who knows the family
    #: saying so, and a record of who — see ``invitations.age_attested_by``.
    age_attested: bool

    @model_validator(mode="after")
    def _the_age_is_attested(self) -> "InvitationCreate":
        """Refuse an invitation whose sender did not make the statement.

        ``False`` and "absent" are the same answer to the only question
        being asked, and both are refused rather than recorded.
        """
        if not self.age_attested:
            raise ValueError("age_attested must be true: the invitation states that this person is 13 or older")
        return self

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
    fulfilled_at: datetime | None = None
    expires_at: datetime
    #: When the sender stated this person is 13 or older. ``None`` on an
    #: invitation written before the statement was asked for.
    age_attested_at: datetime | None = None
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


class InvitationPreviewRequest(RequestModel):
    """The token, in a body rather than a path, so no request log holds it."""

    token: str = Field(min_length=1, max_length=128)


class InvitationAcceptRequest(RequestModel):
    token: str = Field(min_length=1, max_length=128)


class InvitationAcceptResponse(BaseModel):
    role: InvitationRoleLiteral
    #: What the acceptance actually did, so the page can say "you are
    #: enrolled" rather than guessing from the scope it asked for.
    scope: InvitationScopeLiteral
    enrolled_course_id: str | None = None
