"""View as: a platform admin sees Equip exactly as another person does, read-only.

Built 2026-11-08 for dogfooding: the only way to know what a teacher sees
when a student hands in work is to look with the teacher's eyes. Three
locks keep it from ever touching that person's account:

1. ``ViewAsReadOnlyMiddleware`` refuses every request that carries the
   header and is not GET / HEAD / OPTIONS, before any route runs.
2. The request's database session runs ``SET TRANSACTION READ ONLY`` on
   every transaction it opens, so a GET that happens to write (a quiz
   detail that creates an attempt, a calendar read that marks something)
   fails in Postgres instead of writing.
3. The frontend sends no writes at all while the mode is on.

Every start is an ``audit_logs`` row (who, whom, why, until when); the
header carries that row's id, so a view cannot outlive its 30 minutes and
an ended one cannot be reused. No new table and no new secret: the row is
the session.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import status
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, SessionTransaction
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import ErrorCode, equip_error
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole

HEADER = "X-View-As"
TTL = timedelta(minutes=30)
ACTION_START = "view_as_start"
ACTION_END = "view_as_end"
RESOURCE = "user"
_READ_ONLY = "equip_view_as_read_only"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _forbidden(message: str) -> Exception:
    return equip_error(ErrorCode.VIEW_AS_REFUSED, status_code=status.HTTP_403_FORBIDDEN, message=message)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def start(db: Session, admin: User, target: User, reason: str) -> AuditLog:
    """Open a view and record it. The row is committed before it is returned."""
    if admin.role != UserRole.ADMIN.value:
        raise _forbidden("Only platform admins can view as someone else")
    if target.id == admin.id:
        raise _forbidden("You are already yourself")
    expires_at = datetime.now(UTC) + TTL
    row = AuditLog(
        user_id=admin.id,
        action=ACTION_START,
        resource_type=RESOURCE,
        resource_id=str(target.id),
        details={"reason": reason, "target_email": target.email, "expires_at": expires_at.isoformat()},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def expires_at(row: AuditLog) -> datetime:
    return _aware(row.created_at) + TTL


def end(db: Session, admin: User, view_id: str) -> None:
    """Close a view early. Closing one that is already over is not an error."""
    row = _start_row(db, admin, view_id)
    if row is None or _ended(db, row):
        return
    db.add(AuditLog(user_id=admin.id, action=ACTION_END, resource_type=RESOURCE, resource_id=str(row.id), details=None))
    db.commit()


def _start_row(db: Session, admin: User, view_id: str) -> AuditLog | None:
    try:
        row_id = uuid.UUID(view_id)
    except ValueError:
        return None
    row = db.get(AuditLog, row_id)
    if row is None or row.action != ACTION_START or str(row.user_id) != str(admin.id):
        return None
    return row


def _ended(db: Session, row: AuditLog) -> bool:
    return (
        db.query(AuditLog.id).filter(AuditLog.action == ACTION_END, AuditLog.resource_id == str(row.id)).first()
        is not None
    )


def resolve(db: Session, caller: User, view_id: str) -> User:
    """The person ``caller`` is viewing as, with ``db`` switched to read-only.

    Refuses rather than falling back to the caller: a request that asked to
    be someone else and silently got the admin instead would show the admin
    a page they would take for the other person's.
    """
    if caller.role != UserRole.ADMIN.value:
        raise _forbidden("Only platform admins can view as someone else")
    row = _start_row(db, caller, view_id)
    if row is None:
        raise _forbidden("This view does not exist")
    if expires_at(row) <= datetime.now(UTC) or _ended(db, row):
        raise _forbidden("This view has ended")
    target = db.get(User, uuid.UUID(row.resource_id))
    if target is None:
        raise _forbidden("The person no longer has an account")
    make_read_only(db)
    return target


def make_read_only(db: Session) -> None:
    """Every transaction this session opens from now on is READ ONLY.

    The one already open (it only read the caller and the view row) is
    committed so the next statement starts a fresh, read-only one.
    """
    db.info[_READ_ONLY] = True
    if db.in_transaction():
        db.commit()


@event.listens_for(Session, "after_begin")
def _begin_read_only(session: Session, transaction: SessionTransaction, connection: Connection) -> None:
    if session.info.get(_READ_ONLY) and connection.dialect.name == "postgresql":
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")


def is_read_only_violation(exc: BaseException) -> bool:
    """A write Postgres refused because the transaction was READ ONLY (SQLSTATE 25006)."""
    orig: Any = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) == "25006" or getattr(orig, "pgcode", None) == "25006"


class ViewAsReadOnlyMiddleware:
    """Refuse every write that carries the view-as header, before routing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in _SAFE_METHODS:
            names = {name.lower() for name, _ in scope.get("headers", [])}
            if HEADER.lower().encode() in names:
                from starlette.responses import JSONResponse

                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": {
                            "code": ErrorCode.VIEW_AS_READ_ONLY.value,
                            "message": "Read-only view: nothing can be changed",
                            "context": {},
                        }
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
