"""The complaints ledger, and the threshold that is actually enforced.

The published policy is a count: more than two upheld complaints against one
person and the account closes. This module is the only place that count is
kept and the only place it is acted on, so the two cannot disagree.

Acting on it is the part that matters. BMG v. Cox lost the safe harbour with
a thirteen-step written policy in hand, because the record showed the last
step was never taken — the document was fine and nothing implemented it.
Ventura v. Motherless kept it with a one-person operation, a simple procedure
and a record of having followed it. So the closure here is not a button
somebody remembers to press: upholding the third complaint deactivates the
account in the same transaction, and the row says which strike did it.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.dmca_complaint import (
    UPHELD_COMPLAINTS_BEFORE_CLOSURE,
    DmcaComplaint,
    DmcaComplaintStatus,
)
from app.models.user import User
from app.schemas.dmca import (
    DmcaComplaintCreate,
    DmcaComplaintDecision,
    DmcaComplaintOut,
    DmcaStatusLiteral,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/admin/dmca", tags=["admin-dmca"])


def upheld_count(db: Session, user_id: uuid.UUID) -> int:
    """How many complaints against this person have been upheld."""
    rows = db.scalars(
        select(DmcaComplaint.id).where(
            DmcaComplaint.uploaded_by == user_id,
            DmcaComplaint.status == DmcaComplaintStatus.UPHELD.value,
        )
    ).all()
    return len(rows)


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    if not ids:
        return {}
    return {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(ids))).all()}


def _one_name(db: Session, user_id: uuid.UUID | None) -> str | None:
    """The uploader's name, or ``None`` when there is no uploader to name."""
    if user_id is None:
        return None
    return _names(db, {user_id}).get(user_id)


def _to_out(complaint: DmcaComplaint, *, uploader_name: str | None, upheld: int) -> DmcaComplaintOut:
    return DmcaComplaintOut(
        id=complaint.id,
        received_at=complaint.received_at,
        complainant_name=complaint.complainant_name,
        complainant_email=complaint.complainant_email,
        complainant_organization=complaint.complainant_organization,
        work_described=complaint.work_described,
        material_location=complaint.material_location,
        uploaded_by=complaint.uploaded_by,
        uploader_name=uploader_name,
        uploader_notified_at=complaint.uploader_notified_at,
        status=complaint.status,  # type: ignore[arg-type]
        resolved_at=complaint.resolved_at,
        resolved_by=complaint.resolved_by,
        resolution_note=complaint.resolution_note,
        strike_number=complaint.strike_number,
        uploader_upheld_count=upheld,
        uploader_account_closed=upheld > UPHELD_COMPLAINTS_BEFORE_CLOSURE,
    )


@router.get("/complaints", response_model=list[DmcaComplaintOut])
def list_complaints(
    status_filter: DmcaStatusLiteral | None = Query(default=None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[DmcaComplaintOut]:
    """Every complaint, newest first, each carrying its uploader's running count.

    The count travels with the row because that is the question somebody
    reading this screen is actually asking: not "what happened to this one"
    but "how many times has this been this person".
    """
    query = select(DmcaComplaint).order_by(DmcaComplaint.received_at.desc())
    if status_filter is not None:
        query = query.where(DmcaComplaint.status == status_filter)
    complaints = list(db.scalars(query.offset(skip).limit(limit)).all())

    uploader_ids = {row.uploaded_by for row in complaints if row.uploaded_by is not None}
    names = _names(db, uploader_ids)
    counts = {user_id: upheld_count(db, user_id) for user_id in uploader_ids}
    return [
        _to_out(
            row,
            uploader_name=names.get(row.uploaded_by) if row.uploaded_by else None,
            upheld=counts.get(row.uploaded_by, 0) if row.uploaded_by else 0,
        )
        for row in complaints
    ]


@router.post("/complaints", response_model=DmcaComplaintOut, status_code=status.HTTP_201_CREATED)
def record_complaint(
    body: DmcaComplaintCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> DmcaComplaintOut:
    """Write down a notice that arrived.

    Transcribed from the letter rather than submitted through a form: a
    notice under 512(c)(3) carries a signature and a statement made under
    penalty of perjury, and a web form that collects neither would produce
    something shaped like a notice that is not one.
    """
    if body.uploaded_by is not None and db.get(User, body.uploaded_by) is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No such account",
            context={"resource_type": "user", "resource_id": str(body.uploaded_by)},
        )

    complaint = DmcaComplaint(
        complainant_name=body.complainant_name,
        complainant_email=body.complainant_email,
        complainant_organization=body.complainant_organization,
        work_described=body.work_described,
        material_location=body.material_location,
        uploaded_by=body.uploaded_by,
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    log_action(
        db,
        admin.id,
        "create",
        "dmca_complaint",
        str(complaint.id),
        details={"material_location": body.material_location, "uploaded_by": str(body.uploaded_by or "")},
    )

    upheld = upheld_count(db, complaint.uploaded_by) if complaint.uploaded_by else 0
    return _to_out(complaint, uploader_name=_one_name(db, complaint.uploaded_by), upheld=upheld)


@router.patch("/complaints/{complaint_id}", response_model=DmcaComplaintOut)
def decide_complaint(
    complaint_id: uuid.UUID,
    body: DmcaComplaintDecision,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> DmcaComplaintOut:
    """Record what was decided — and, on the third upheld one, close the account.

    Deciding is one-way. A complaint that has been upheld cannot be un-upheld
    here: a strike may already have closed an account, and silently
    renumbering the history afterwards would leave the ledger unable to
    explain a closure it caused. A mistake is corrected by a new row and a
    note, the way a mistake in any other ledger is.
    """
    complaint = db.get(DmcaComplaint, complaint_id)
    if complaint is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No such complaint",
            context={"resource_type": "dmca_complaint", "resource_id": str(complaint_id)},
        )
    if complaint.status != DmcaComplaintStatus.RECEIVED.value:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message="This complaint has already been decided",
            context={"resource_type": "dmca_complaint", "current_status": complaint.status},
        )

    now = datetime.now(UTC)
    complaint.status = body.status
    complaint.resolved_at = now
    complaint.resolved_by = admin.id
    complaint.resolution_note = body.resolution_note
    if body.uploader_notified:
        complaint.uploader_notified_at = now

    closed = False
    if body.status == DmcaComplaintStatus.UPHELD.value and complaint.uploaded_by is not None:
        # Counted before this row is committed, then stamped: the strike
        # number is this complaint's position in the person's sequence.
        complaint.strike_number = upheld_count(db, complaint.uploaded_by) + 1
        if complaint.strike_number > UPHELD_COMPLAINTS_BEFORE_CLOSURE:
            uploader = db.get(User, complaint.uploaded_by)
            if uploader is not None and uploader.deactivated_at is None:
                # In the same transaction as the decision, on purpose. A
                # closure that depends on somebody remembering to do it
                # afterwards is the policy Cox had.
                uploader.deactivated_at = now
                closed = True

    db.commit()
    db.refresh(complaint)

    log_action(
        db,
        admin.id,
        "update",
        "dmca_complaint",
        str(complaint.id),
        details={
            "status": complaint.status,
            "strike_number": complaint.strike_number,
            "uploader_notified": body.uploader_notified,
            "account_closed": closed,
        },
    )

    upheld = upheld_count(db, complaint.uploaded_by) if complaint.uploaded_by else 0
    return _to_out(complaint, uploader_name=_one_name(db, complaint.uploaded_by), upheld=upheld)
