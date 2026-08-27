from typing import cast

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, organization_of, require_director
from app.core.database import get_db
from app.models.invitation import Invitation
from app.models.user import User
from app.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationPreview,
    InvitationResponse,
    InvitationRoleLiteral,
    InvitationStatusLiteral,
)
from app.services.invitation_service import (
    accept_invitation,
    create_or_resend_invitation,
    get_invitation_by_token,
    is_invitation_expired,
    list_invitations,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])


def _to_response(invitation: Invitation) -> InvitationResponse:
    is_expired = invitation.status == "pending" and is_invitation_expired(invitation)
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=cast("InvitationRoleLiteral", invitation.role),
        status=cast("InvitationStatusLiteral", invitation.status),
        invited_by=invitation.invited_by,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
        expires_at=invitation.expires_at,
        is_expired=is_expired,
    )


@router.post("", response_model=InvitationResponse, status_code=201)
def create_invitation(
    body: InvitationCreate,
    request: Request,
    director: User = Depends(require_director),
    db: Session = Depends(get_db),
) -> InvitationResponse:
    """Admin-only: invite an email to join as teacher or student.

    Idempotent on re-invite while a prior invitation for the same
    (email, role) is still pending and unexpired -- see
    ``create_or_resend_invitation`` for the dedupe/resend contract.
    """
    invitation, _is_new = create_or_resend_invitation(
        db,
        email=body.email,
        role=body.role,
        invited_by=director.id,
        organization_id=organization_of(director),
        request=request,
    )
    return _to_response(invitation)


@router.get("", response_model=list[InvitationResponse])
def list_invitations_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    role: str | None = Query(None),
    invite_status: str | None = Query(None, alias="status"),
    director: User = Depends(require_director),
    db: Session = Depends(get_db),
) -> list[InvitationResponse]:
    rows = list_invitations(db, skip=skip, limit=limit, role=role, status_filter=invite_status)
    return [_to_response(r) for r in rows]


@router.get("/token/{token}", response_model=InvitationPreview)
def preview_invitation(
    token: str = Path(..., max_length=128),
    db: Session = Depends(get_db),
) -> InvitationPreview:
    """Unauthenticated preview of an invite, for the accept-invite page
    to render "you've been invited as a teacher" copy before the visitor
    has signed in. Deliberately returns 200 with ``is_expired``/``status``
    rather than 404/410 for a stale token, so the accept page can render
    a clear "this invite expired" state instead of a generic not-found.
    """
    invitation = get_invitation_by_token(db, token)
    return InvitationPreview(
        email=invitation.email,
        role=cast("InvitationRoleLiteral", invitation.role),
        status=cast("InvitationStatusLiteral", invitation.status),
        is_expired=invitation.status == "pending" and is_invitation_expired(invitation),
    )


@router.post("/accept", response_model=InvitationAcceptResponse)
def accept_invitation_route(
    body: InvitationAcceptRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvitationAcceptResponse:
    """Redeem an invite token for the signed-in caller.

    The caller must already have an account (self-registered as student,
    or logged in via Google) under the exact email the invite was sent
    to -- see the migration docstring for why the backend doesn't mint
    the Supabase Auth user itself.
    """
    invitation = accept_invitation(
        db,
        token=body.token,
        current_user_id=current_user.id,
        current_user_email=current_user.email,
        request=request,
    )
    return InvitationAcceptResponse(role=cast("InvitationRoleLiteral", invitation.role))
