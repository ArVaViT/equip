import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GradeExemption(Base):
    """A student excused from one piece of work (D6).

    The exemption removes the item from **both** denominators — the grade and
    the progress. Removing it from the grade alone is the trap the design flags
    twice: the student stays short of progress 100, so the certificate gate can
    never be satisfied, for exactly the sick teenager the feature exists for.

    Creating a row atomically marks the item's chapter complete with
    ``completion_type='excused'``; deleting one reverts only those rows, which
    is why the type is distinct from ``'teacher'``.
    """

    __tablename__ = "grade_exemptions"
    __table_args__ = (
        Index("ix_grade_exemptions_student_course", "student_id", "course_id"),
        # One exemption per student per item: waiving the same work twice is a
        # no-op, not a second row the inverse would only half revert.
        UniqueConstraint("student_id", "item_type", "item_id", name="uq_grade_exemptions_student_item"),
        CheckConstraint("item_type IN ('quiz', 'assignment')", name="grade_exemptions_item_type_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column()
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    item_type: Mapped[str] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    #: Optional, director-visible. Waiving work is a decision someone will be
    #: asked about — especially when it is the last thing between a student and
    #: a certificate.
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<GradeExemption student={self.student_id} {self.item_type}={self.item_id}>"
