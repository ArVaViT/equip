"""Regression test for the audit-log persistence bug.

Background
----------
``audit_service.log_action`` used to wrap its INSERT in a SAVEPOINT and
return without committing. Most call sites invoke ``log_action`` *after*
their own ``db.commit()``, which leaves the session with no open
transaction. The savepoint then auto-began a new implicit transaction —
which FastAPI's ``get_db`` teardown silently rolled back on
``db.close()``, dropping the audit row.

The other tests in the suite use ``conftest`` fixtures that share a
single session between the route and the assertion, so the
unflushed-but-uncommitted row is still visible from the same session
before teardown. They cannot catch the production regression.

This test creates two independent sessions on the test engine: one to
emulate the route, one to verify durability from a fresh connection
after the first session is closed.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.services.audit_service import log_action
from tests.conftest import TestSessionFactory

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_log_action_survives_session_close_after_commit():
    """Pattern A: route does db.commit() then log_action(). The audit row
    must be visible from a fresh session after the route's session closes.
    """
    user_id = uuid.uuid4()

    # Route-side session: seed a user + simulate the route's own commit,
    # then call log_action just like the broken pattern.
    route_session: Session = TestSessionFactory()
    try:
        route_session.add(
            User(
                id=user_id,
                email=f"{user_id}@example.com",
                full_name="Pattern A Tester",
                role=UserRole.STUDENT.value,
            )
        )
        route_session.commit()

        log_action(
            db=route_session,
            user_id=user_id,
            action="test_action",
            resource_type="test_resource",
            resource_id=str(user_id),
            details={"pattern": "A"},
        )
    finally:
        route_session.close()

    # Fresh session — emulates "next request reads what the previous
    # request wrote". Must see the audit row.
    verifier: Session = TestSessionFactory()
    try:
        row = (
            verifier.query(AuditLog)
            .filter(
                AuditLog.action == "test_action",
                AuditLog.resource_id == str(user_id),
            )
            .first()
        )
        assert row is not None, "Audit row was lost on session close — log_action did not commit."
        assert row.details == {"pattern": "A"}
    finally:
        verifier.close()


def test_log_action_survives_session_close_before_caller_commit():
    """Pattern B: route calls log_action() with pending writes, then commits.
    With the fix, log_action's commit also commits the caller's pending
    writes — both the audit row and the caller's row must be durable.
    """
    user_id = uuid.uuid4()

    route_session: Session = TestSessionFactory()
    try:
        # Caller has pending writes when log_action is invoked.
        route_session.add(
            User(
                id=user_id,
                email=f"{user_id}@example.com",
                full_name="Pattern B Tester",
                role=UserRole.STUDENT.value,
            )
        )
        log_action(
            db=route_session,
            user_id=user_id,
            action="test_action_b",
            resource_type="test_resource",
            resource_id=str(user_id),
            details={"pattern": "B"},
        )
        # Caller's own commit is now a no-op because log_action already
        # promoted everything. This must not raise.
        route_session.commit()
    finally:
        route_session.close()

    verifier: Session = TestSessionFactory()
    try:
        row = verifier.query(AuditLog).filter(AuditLog.action == "test_action_b").first()
        assert row is not None
        assert row.details == {"pattern": "B"}

        user_row = verifier.query(User).filter(User.id == user_id).first()
        assert user_row is not None, "Caller's pending write was lost."
    finally:
        verifier.close()
