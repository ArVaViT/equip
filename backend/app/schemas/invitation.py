from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas._request import RequestModel

# Mirrors the Postgres CHECK constraints on invitations.role / .status
# (see supabase/migrations/20260707120000_add_invitations_table.sql) and
# the SQLAlchemy model's CheckConstraints. Deliberately excludes "admin" --
# an invite can never grant admin, only the manual role-change route can.
InvitationRoleLiteral = Literal["teacher", "student"]
InvitationStatusLiteral = Literal["pending", "accepted", "revoked"]


class InvitationCreate(RequestModel):
    email: EmailStr
    role: InvitationRoleLiteral


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: InvitationRoleLiteral
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
    """

    email: str
    role: InvitationRoleLiteral
    status: InvitationStatusLiteral
    is_expired: bool


class InvitationAcceptRequest(RequestModel):
    token: str = Field(min_length=1, max_length=128)


class InvitationAcceptResponse(BaseModel):
    role: InvitationRoleLiteral
