"""Cron-driven sweep: tell senders about invitations nobody has answered.

Not user-facing. Vercel Cron calls it hourly with the shared worker secret
(``require_worker_secret``, the same as the other internal workers). The work
itself is ``services/invitation_watch.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session  # noqa: TC002 — used by FastAPI Depends at runtime

from app.api.dependencies import require_worker_secret
from app.core.database import get_db
from app.services.invitation_watch import notice_unanswered

router = APIRouter(prefix="/internal", tags=["internal"])


class InvitationWatchResponse(BaseModel):
    noticed: int


_RESPONSES: dict[int | str, dict[str, str]] = {
    200: {"description": "The sweep ran; ``noticed`` is how many senders were told about an invitation."},
    401: {"description": "Worker secret missing or wrong"},
    503: {"description": "TRANSLATION_WORKER_SECRET is not configured on this deployment"},
}


@router.post("/invitation-watch", response_model=InvitationWatchResponse, responses=_RESPONSES)
def invitation_watch_post(
    db: Session = Depends(get_db),
    _: None = Depends(require_worker_secret),
) -> InvitationWatchResponse:
    return InvitationWatchResponse(noticed=notice_unanswered(db))


@router.get("/invitation-watch", response_model=InvitationWatchResponse, responses=_RESPONSES)
def invitation_watch_get(
    db: Session = Depends(get_db),
    _: None = Depends(require_worker_secret),
) -> InvitationWatchResponse:
    """Vercel Cron Jobs send GET — same as POST."""
    return InvitationWatchResponse(noticed=notice_unanswered(db))
