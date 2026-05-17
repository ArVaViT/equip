from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.http import get_client_ip
from app.models.audit_log import AuditLog

if TYPE_CHECKING:
    from uuid import UUID

    from fastapi import Request
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_action(
    db: Session,
    user_id: str | UUID,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, object] | None = None,
    request: Request | None = None,
) -> None:
    """Persist an audit log entry inside a SAVEPOINT so it never
    interferes with the caller's transaction.

    Failure here is non-fatal — audit-log writes must not crash the
    request that triggered them. The ``with db.begin_nested()`` block
    rolls the savepoint back on its own if the INSERT raises, leaving
    the caller's outer transaction intact.
    """
    ip_address: str | None = None
    user_agent: str | None = None
    if request is not None:
        ip_address = get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")[:500]

    try:
        with db.begin_nested():
            db.add(
                AuditLog(
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=str(resource_id),
                    details=details,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            db.flush()
    except Exception:
        logger.exception("Failed to write audit log")
