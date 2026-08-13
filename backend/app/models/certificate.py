import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CertificateStatus(enum.StrEnum):
    """Certificate request → approve → issue state machine.

    ``pending`` — student requested. Teacher must approve first.
    ``teacher_approved`` — instructor signed off. Admin issues from here.
    ``approved`` — admin issued; ``certificate_number`` populated.
    ``rejected`` — either reviewer can reject before issuance.
    """

    PENDING = "pending"
    TEACHER_APPROVED = "teacher_approved"
    APPROVED = "approved"
    REJECTED = "rejected"


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (
        # The unique constraint already backs a B-tree on
        # ``(user_id, course_id)``; a separate identical index was pure
        # duplication (same columns, same order).
        UniqueConstraint("user_id", "course_id", name="uq_certificate_user_course"),
        Index("ix_certificates_status", "status"),
        # Mirror prod: status state machine (pending → teacher_approved → approved / rejected).
        CheckConstraint(
            "status IN ('pending', 'teacher_approved', 'approved', 'rejected')",
            name="certificates_status_check",
        ),
        # At most one of the two: a symbol or a percentage, never both. Written
        # with CASE rather than ``num_nonnulls`` so SQLite can materialise it
        # for the test suite.
        CheckConstraint(
            "(CASE WHEN official_code IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN official_score IS NULL THEN 0 ELSE 1 END) <= 1",
            name="ck_certificates_one_official_grade",
        ),
        CheckConstraint(
            "graded_via IS NULL OR graded_via IN ('computed', 'override', 'completion')",
            name="ck_certificates_graded_via",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column()
    # ``course_id`` is nullable so that deleting a course doesn't hard-delete
    # the certificate row — the FK fires ``ON DELETE SET NULL`` and a Postgres
    # trigger snapshots the course title into ``archived_course_title``,
    # leaving the verify endpoint with enough metadata to keep rendering the
    # credential after the source course is gone. See migration
    # ``20260516020225_certificates_course_set_null_with_archive.sql``.
    course_id: Mapped[str | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    archived_course_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    # No server_default: the previous ``func.now()`` populated this column
    # on certificate REQUEST (status='pending'), exposing a fake "issued"
    # datetime months before ``admin_approve`` actually issues the cert.
    # ``admin_approve`` is the only writer now; the column stays NULL for
    # pending / teacher_approved / rejected rows.
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certificate_number: Mapped[str | None] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    teacher_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    teacher_approved_by: Mapped[uuid.UUID | None] = mapped_column()
    admin_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_approved_by: Mapped[uuid.UUID | None] = mapped_column()
    # ``cohort_id`` carries an FK to ``cohorts.id`` with ``ON DELETE SET NULL``
    # — cohorts are metadata, not a load-bearing identity for the cert, so
    # deleting a cohort must not destroy issued certs. The constraint already
    # lives in prod; the model just never declared it, leaving the CI
    # schema-smoke job blind to the relationship. See migration
    # ``20260516021349_certificates_cohort_fk_ensure.sql``.
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True)

    # --- The grade this certificate was issued on (M6) ---------------------
    #
    # A certificate is a document: printed, signed, kept for twenty years.
    # Everything it was computed from is live and editable — the weights, the
    # school's bands, the pass line, the marks, even whether a piece of work was
    # excused. Recomputed on read, the paper stops matching the database the
    # first time a director nudges the band table, silently and for everyone who
    # ever graduated. Written once at issuance; never updated afterwards.
    #
    # NULL on every certificate issued before this existed. That is the honest
    # value: nobody recorded the rules those were issued under, and inventing a
    # snapshot for them would be writing history rather than keeping it.
    grading_scheme: Mapped[str | None] = mapped_column(Text)
    pass_threshold: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    #: The result in whichever form the scheme uses — a symbol or a percentage,
    #: never both, mirroring ``student_grades`` (D7).
    official_code: Mapped[str | None] = mapped_column(Text)
    #: The letterhead, captured at issuance and never re-read. A school that
    #: renames itself must not rewrite what it already certified, and a student
    #: who changes her surname must not have last year's document re-issued in
    #: a name she did not hold when she earned it. The grade was frozen for
    #: exactly this reason (M6); the words are the part a person reads.
    school_name: Mapped[str | None] = mapped_column(Text)
    school_city: Mapped[str | None] = mapped_column(Text)
    student_name: Mapped[str | None] = mapped_column(Text)
    teacher_name: Mapped[str | None] = mapped_column(Text)
    official_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    #: How the grade was decided — the question a director asks when two
    #: certificates from one course disagree. ``computed`` | ``override`` |
    #: ``completion``.
    graded_via: Mapped[str | None] = mapped_column(Text)
