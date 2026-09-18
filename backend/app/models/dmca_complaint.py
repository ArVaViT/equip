"""Who complained, about what, what was decided, and who was told.

§ 512's safe harbour is not a status a platform has; it is a set of things a
platform does, and one of them is 512(i)(1)(A) — adopt a policy for repeat
infringers, tell people about it, and **reasonably implement it**. The third
clause is the one that is lost.

BMG v. Cox (4th Cir. 2018) is the case. Cox had a written policy with thirteen
graduated steps ending in termination, and the court took the safe harbour
away anyway, because the record showed the last step was essentially never
taken: the policy existed and was not implemented. The test is not whether the
document is good.

Ventura Content v. Motherless (9th Cir. 2018) is the other side, and the more
useful one here. A site run by one person, with no ticketing system and no
compliance department, kept the safe harbour: the operator had a simple
procedure, followed it, and could show a record of what he had done. Small was
not the problem. Unrecorded would have been.

This table is that record. One row per complaint, carrying the four things a
court asked Cox for and did not get: who complained, about which material, what
was decided, and whether the person who uploaded it was told. Plus the strike
number, because the policy this platform publishes is a count — more than two
upheld complaints against one person and the account closes — and a count that
nobody writes down is not a count.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DmcaComplaintStatus(enum.StrEnum):
    """What has been decided about one complaint.

    Deliberately four values and not a workflow. Nine teachers and a handful
    of complaints a year do not need states for "triaged" and "awaiting
    legal"; they need to be able to say, of any complaint, whether it was
    agreed with.
    """

    #: Arrived; nobody has decided yet.
    RECEIVED = "received"
    #: Agreed with. The material came down and this counts as a strike.
    UPHELD = "upheld"
    #: Not agreed with. Counts toward nothing — a complaint that was wrong
    #: must not close somebody's account, which is the failure mode of
    #: counting notices instead of findings.
    REJECTED = "rejected"
    #: The complainant took it back, or sent it to the wrong platform.
    WITHDRAWN = "withdrawn"


#: The published rule. More than two upheld complaints against one person and
#: the account closes — so the third upheld complaint is the one that does it.
#:
#: A number rather than a judgement, on purpose. Cox's policy was a judgement
#: at every step and the judgement was always "not yet"; the point of writing
#: the threshold into the code is that nobody has to decide it while looking
#: at a particular person they like.
UPHELD_COMPLAINTS_BEFORE_CLOSURE = 2


class DmcaComplaint(Base):
    """One notice of claimed infringement, and what became of it."""

    __tablename__ = "dmca_complaints"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'upheld', 'rejected', 'withdrawn')",
            name="chk_dmca_complaints_status",
        ),
        # A decision with no decider, or a decider with no decision, leaves
        # the record unable to answer the question it is kept for.
        CheckConstraint(
            "(resolved_at IS NULL) = (resolved_by IS NULL)",
            name="chk_dmca_complaints_resolved_together",
        ),
        # A strike is the position of an upheld complaint in one person's
        # sequence. Anything else having one would make the count meaningless.
        CheckConstraint(
            "(strike_number IS NULL) OR (status = 'upheld')",
            name="chk_dmca_complaints_strike_is_upheld",
        ),
        Index("ix_dmca_complaints_uploaded_by", "uploaded_by"),
        Index("ix_dmca_complaints_received_at", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    #: Who complained. Stored as they gave it, because a notice under
    #: 512(c)(3) has to be signed by a person and the record is of what that
    #: person said. Not a foreign key: a complainant is almost never a user.
    complainant_name: Mapped[str] = mapped_column(Text)
    complainant_email: Mapped[str] = mapped_column(Text)
    #: The publisher or rights-holder they act for, when it is not themselves.
    complainant_organization: Mapped[str | None] = mapped_column(Text, default=None)

    #: The work they say is theirs — 512(c)(3)(A)(ii).
    work_described: Mapped[str] = mapped_column(Text)
    #: Where on Equip the material sits — 512(c)(3)(A)(iii). Free text rather
    #: than a foreign key into content, because a complaint frequently names
    #: something already deleted, and a row that cannot be written because its
    #: target is gone is a record that fails exactly when it is needed.
    material_location: Mapped[str] = mapped_column(Text)

    #: The person who put it there, when it can be worked out. Nullable and
    #: ``SET NULL``: a complaint about material nobody can be tied to is still
    #: a complaint worth having on file, it just counts toward nobody.
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"), default=None)
    #: When that person was told. § 512(g) turns on the uploader being able to
    #: answer, and they cannot answer a complaint nobody mentioned to them.
    uploader_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    status: Mapped[str] = mapped_column(Text, default=DmcaComplaintStatus.RECEIVED.value, server_default="received")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"), default=None)
    #: Why, in the words of whoever decided. Short, and the only free-form
    #: field a reader of this table will actually rely on later.
    resolution_note: Mapped[str | None] = mapped_column(Text, default=None)

    #: Which strike this was for ``uploaded_by`` — 1 for their first upheld
    #: complaint, 2 for the second, and so on. Stamped when it is upheld and
    #: never recomputed: the count at the moment of the decision is what the
    #: decision was made on, and a later withdrawal must not quietly renumber
    #: the history.
    strike_number: Mapped[int | None] = mapped_column(Integer, default=None)
