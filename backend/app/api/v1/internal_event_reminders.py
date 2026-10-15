"""Cron-driven sweep: remind each class an hour before it starts.

Not user-facing. Vercel Cron calls it every five minutes with the shared
worker secret (``require_worker_secret``, the same as the translation
worker). The work itself is ``services/event_reminders.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session  # noqa: TC002 — used by FastAPI Depends at runtime

from app.api.dependencies import require_worker_secret
from app.core.database import get_db
from app.services.event_reminders import send_due_reminders

router = APIRouter(prefix="/internal", tags=["internal"])


class RemindersResponse(BaseModel):
    reminded: int


_RESPONSES: dict[int | str, dict[str, str]] = {
    200: {"description": "The sweep ran; ``reminded`` is how many events it announced."},
    401: {"description": "Worker secret missing or wrong"},
    503: {"description": "TRANSLATION_WORKER_SECRET is not configured on this deployment"},
}


@router.post("/event-reminders", response_model=RemindersResponse, responses=_RESPONSES)
def event_reminders_post(
    db: Session = Depends(get_db),
    _: None = Depends(require_worker_secret),
) -> RemindersResponse:
    return RemindersResponse(reminded=send_due_reminders(db))


@router.get("/event-reminders", response_model=RemindersResponse, responses=_RESPONSES)
def event_reminders_get(
    db: Session = Depends(get_db),
    _: None = Depends(require_worker_secret),
) -> RemindersResponse:
    """Vercel Cron Jobs send GET — same as POST."""
    return RemindersResponse(reminded=send_due_reminders(db))
