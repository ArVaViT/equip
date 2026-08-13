"""What a student says about their own work, at the moment they hand it in.

Design: `assessment-integrity-and-the-graders-day.md` §4.

Nothing here detects anything. AI detectors false-positive on writers whose
English is a second language — most of this school — and false-negative on
anything lightly edited, so a platform that renders «87% AI» has manufactured
an accusation it cannot support against the students least able to argue back.

What is supported by evidence is narrower: a 2023 double-blind randomised field
study of unproctored online exams found that a reminder before the work reduced
cheating when it carried three things together — the policy, an example of what
integrity means here, and the consequences. That is what this records, with the
text as displayed rather than a pointer to a row a teacher can edit afterwards.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: What a course allows. The default is disclosure rather than a ban: a ban
#: nobody can enforce is broken silently, and it teaches students to conceal
#: rather than to say.
AI_POLICIES = ("ai_forbidden", "ai_with_disclosure", "ai_open")


class SubmissionDeclaration(Base):
    """One statement about one piece of work.

    ``ai_use = "assisted"`` under ``ai_forbidden`` is a **disclosed breach**: a
    student telling the truth about a rule they broke. It is recorded and shown
    to the teacher, and the platform never refuses the work for it — refusing at
    the door teaches the next student to tick the other box, and the whole value
    of a declaration is that it is worth making honestly.
    """

    __tablename__ = "submission_declarations"
    __table_args__ = (
        UniqueConstraint("submission_id", name="uq_submission_declarations_submission"),
        CheckConstraint("ai_use IN ('none', 'assisted')", name="submission_declarations_ai_use_check"),
        CheckConstraint(
            "policy IN ('ai_forbidden', 'ai_with_disclosure', 'ai_open')",
            name="submission_declarations_policy_check",
        ),
        Index("ix_submission_declarations_submission", "submission_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignment_submissions.id", ondelete="CASCADE"))
    #: The policy as it stood when this was signed. Same principle as the
    #: ведомость and the certificate: what somebody agreed to has to survive
    #: the thing they agreed to being changed.
    policy: Mapped[str] = mapped_column(Text)
    #: The text as displayed to them, not a key into a catalogue.
    statement: Mapped[str] = mapped_column(Text)
    ai_use: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip: Mapped[str | None] = mapped_column(Text)
