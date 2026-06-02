"""Coverage tests for ``app.services.audit_service.log_action`` —
specifically the except-branch (lines 67-70) that swallows database
errors so an audit-log write failure can NEVER take down the
request path it was logging.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.services.audit_service import log_action

if TYPE_CHECKING:
    import pytest


class TestLogActionSwallowsExceptions:
    def test_db_flush_failure_does_not_propagate(self, caplog: pytest.LogCaptureFixture) -> None:
        """If the audit write raises ``OperationalError`` (lock
        timeout, dead connection), ``log_action`` MUST swallow it +
        rollback + log.exception. The caller's request path must
        not see the audit failure surface."""

        db = MagicMock()
        # Simulate a session whose nested begin works but flush
        # blows up — the common "DB hiccup mid-write" shape.
        nested_cm = MagicMock()
        nested_cm.__enter__ = MagicMock(return_value=nested_cm)
        nested_cm.__exit__ = MagicMock(return_value=False)
        db.begin_nested.return_value = nested_cm
        db.flush.side_effect = OperationalError("lock timeout", None, Exception("dead"))

        # No assertion needed — the test asserts log_action does
        # NOT raise. The ``logger.exception`` call below is also
        # captured via caplog so we can confirm the failure was
        # observable in logs.
        with caplog.at_level(logging.ERROR, logger="app.services.audit_service"):
            log_action(
                db,
                user_id="00000000-0000-0000-0000-000000000000",
                action="test_action",
                resource_type="test",
                resource_id="r-1",
            )
        # ``logger.exception`` lands at ERROR level with a stack.
        # The implementation message is "Failed to write audit log".
        relevant = [r for r in caplog.records if "audit log" in r.getMessage().lower()]
        assert relevant, "expected the 'Failed to write audit log' line"

    def test_rollback_swallow_is_idempotent(self) -> None:
        """``contextlib.suppress`` inside the except clause means a
        second-order rollback failure (e.g. the session is already
        deassociated) must also be swallowed silently. Pin so a
        refactor that removes the suppress doesn't surface as a
        500 here."""
        db = MagicMock()
        nested_cm = MagicMock()
        nested_cm.__enter__ = MagicMock(return_value=nested_cm)
        nested_cm.__exit__ = MagicMock(return_value=False)
        db.begin_nested.return_value = nested_cm
        db.flush.side_effect = OperationalError("lock", None, Exception("dead"))
        db.rollback.side_effect = RuntimeError("session detached, cannot rollback")
        # Should still not raise.
        log_action(
            db,
            user_id="00000000-0000-0000-0000-000000000000",
            action="t",
            resource_type="t",
            resource_id="r",
        )
