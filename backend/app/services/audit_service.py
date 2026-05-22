from __future__ import annotations

import contextlib
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
    """Persist an audit log entry, isolated via SAVEPOINT and then
    promoted with an explicit COMMIT.

    Failure here is non-fatal — audit-log writes must not crash the
    request that triggered them. The ``with db.begin_nested()`` block
    rolls the savepoint back on its own if the INSERT raises, leaving
    the caller's outer transaction intact.

    The trailing ``db.commit()`` is load-bearing: most callers invoke
    ``log_action`` AFTER their own ``db.commit()``, which leaves the
    session with no open transaction. The savepoint then auto-begins
    a new implicit transaction; without an explicit commit, FastAPI's
    ``get_db`` teardown (``db.close()``) rolls that transaction back
    and the audit row vanishes. Test suites don't catch this because
    the conftest shares a single session between the route and the
    assertion, so the unflushed-but-uncommitted row is still readable
    from the same session before teardown.
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
        db.commit()
    except Exception:
        with contextlib.suppress(Exception):
            db.rollback()
        logger.exception("Failed to write audit log")
