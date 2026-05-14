from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: str
    details: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: str | None = Query(None),
    resource_type: str | None = Query(None),
    action: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(AuditLog)

    if user_id:
        # The column is a typed UUID; a malformed query-string value
        # would raise ``invalid input syntax for type uuid`` from
        # Postgres and surface as a 500. Validate up-front and 400
        # so clients get an actionable error.
        try:
            parsed_user_id = UUID(user_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id must be a valid UUID",
            ) from exc
        q = q.filter(AuditLog.user_id == parsed_user_id)
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if action:
        q = q.filter(AuditLog.action == action)
    if date_from:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to:
        q = q.filter(AuditLog.created_at <= date_to)

    total = q.count()
    items = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # Return a plain dict so FastAPI hydrates ``AuditLogPage`` via
    # ``from_attributes``; constructing the Pydantic envelope directly
    # would need an explicit ``model_validate`` to pass mypy.
    return {"items": items, "total": total, "page": page, "page_size": page_size}
