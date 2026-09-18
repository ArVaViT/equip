"""Shapes for the complaints ledger."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas._request import RequestModel

#: Mirrors ``chk_dmca_complaints_status`` and ``DmcaComplaintStatus``.
DmcaStatusLiteral = Literal["received", "upheld", "rejected", "withdrawn"]

#: The statuses a human may set. ``received`` is where a row starts and is not
#: somewhere it can be put back: un-deciding a complaint would erase a strike
#: that an account closure may already have been based on.
DmcaDecisionLiteral = Literal["upheld", "rejected", "withdrawn"]


class DmcaComplaintCreate(RequestModel):
    """A notice as it arrived, transcribed by whoever opened the email.

    Deliberately not a public form. § 512(c)(3) wants a signature and a
    statement made under penalty of perjury, and a web form that collects
    neither produces something that looks like a notice and is not one. The
    published procedure says to write to the address on ``/dmca``; this is
    where that letter is written down.
    """

    complainant_name: str = Field(min_length=1, max_length=200)
    complainant_email: EmailStr
    complainant_organization: str | None = Field(default=None, max_length=200)
    #: 512(c)(3)(A)(ii) — the work claimed.
    work_described: str = Field(min_length=1, max_length=4000)
    #: 512(c)(3)(A)(iii) — where the material is.
    material_location: str = Field(min_length=1, max_length=2000)
    #: Who put it there, when it can be worked out.
    uploaded_by: UUID | None = None


class DmcaComplaintDecision(RequestModel):
    """What was decided, and whether the uploader has been told."""

    status: DmcaDecisionLiteral
    resolution_note: str | None = Field(default=None, max_length=4000)
    #: Setting this stamps "the uploader was told" at the current time. It is
    #: a flag rather than a timestamp because the only honest value is now:
    #: a date typed in by hand is a claim, not a record.
    uploader_notified: bool = False


class DmcaComplaintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    received_at: datetime
    complainant_name: str
    complainant_email: str
    complainant_organization: str | None
    work_described: str
    material_location: str
    uploaded_by: UUID | None
    uploader_name: str | None = None
    uploader_notified_at: datetime | None
    status: DmcaStatusLiteral
    resolved_at: datetime | None
    resolved_by: UUID | None
    resolution_note: str | None
    strike_number: int | None
    #: How many upheld complaints this uploader has now, in total. The column
    #: says where this one sat in the sequence; this says where they stand
    #: today, which is the number somebody deciding the next one needs.
    uploader_upheld_count: int = 0
    #: Whether that count has passed the published threshold. Computed rather
    #: than stored so the answer cannot drift from the rule.
    uploader_account_closed: bool = False
