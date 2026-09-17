from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from app.models.audit_log import AuditLog

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_action(
    db: Session,
    user_id: str | UUID,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, object] | None = None,
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

    Deliberately takes no ``Request``. The Privacy Policy promises that an
    IP address is kept at two moments only -- accepting a legal document
    (``legal_acceptances``) and handing in work (``submission_declarations``)
    -- so an audit row records who did what and when, never where from or
    with which browser. ``tests/test_audit_log_keeps_no_ip.py`` holds that.
    """

    try:
        with db.begin_nested():
            db.add(
                AuditLog(
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=str(resource_id),
                    details=details,
                )
            )
            db.flush()
        db.commit()
    except Exception:
        with contextlib.suppress(Exception):
            db.rollback()
        logger.exception("Failed to write audit log")
