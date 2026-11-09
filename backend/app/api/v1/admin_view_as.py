"""Start and end a read-only "view as" (see ``app.services.view_as``).

Platform admins only. Starting one names the person by email and says
why; both land in the audit log with the moment it runs out.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.user import User
from app.schemas._request import RequestModel
from app.services import view_as

router = APIRouter(prefix="/admin/view-as", tags=["admin-view-as"])


class ViewAsStart(RequestModel):
    email: str = Field(..., min_length=3, max_length=320)
    reason: str = Field(..., min_length=3, max_length=500)


class ViewAsPerson(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str


class ViewAsSession(BaseModel):
    id: str
    expires_at: datetime
    person: ViewAsPerson


@router.post("", response_model=ViewAsSession, status_code=status.HTTP_201_CREATED)
def start_view_as(
    data: ViewAsStart,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ViewAsSession:
    target = db.query(User).filter(func.lower(User.email) == data.email.strip().lower()).first()
    if target is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No account with this email",
            context={"resource_type": "user"},
        )
    row = view_as.start(db, admin, target, data.reason.strip())
    return ViewAsSession(
        id=str(row.id),
        expires_at=view_as.expires_at(row),
        person=ViewAsPerson(id=str(target.id), email=target.email, full_name=target.full_name, role=target.role),
    )


@router.post("/{view_id}/end", status_code=status.HTTP_204_NO_CONTENT)
def end_view_as(
    view_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    view_as.end(db, admin, view_id)
