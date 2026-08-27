import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: The bucket id standing in for «без потока» in the partial unique index.
#: NULL is a real value here — a sheet for the students with no cohort — and a
#: plain unique index would let that bucket be closed any number of times.
NO_COHORT_SENTINEL = "00000000-0000-0000-0000-000000000000"


class GradeSheet(Base):
    """A closed ведомость: what a director signed, frozen (D11).

    Everything the sheet is computed from stays editable afterwards — a teacher
    can re-mark an essay, lift an exemption, or hand-set a grade months later.
    A document rendered from live data would change in the filing cabinet, so
    closing takes a snapshot and the printable reads only from that.

    Cohort-scoped from the first day rather than deferred: the moment a school
    runs the same course a second year, an unscoped sheet mixes two поток into
    one signed page and nothing afterwards can tell them apart.
    """

    __tablename__ = "grade_sheets"
    __table_args__ = (
        Index("ix_grade_sheets_course", "course_id"),
        # Postgres only: the expression carries a `::uuid` cast and a partial
        # WHERE, neither of which SQLite can parse — and the test suite runs on
        # SQLite. Prod gets the index from the migration; declaring it here
        # keeps the CI schema-smoke job (real Postgres) honest about the shape.
        Index(
            "uq_grade_sheets_active",
            "course_id",
            text(f"COALESCE(cohort_id, '{NO_COHORT_SENTINEL}'::uuid)"),
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ).ddl_if(dialect="postgresql"),
        # A sheet cannot have been reopened before it was closed, and a
        # reopening with no reason is exactly what the reason exists to stop.
        CheckConstraint(
            "reopened_at IS NULL OR (reopened_at >= finalized_at AND reopen_reason IS NOT NULL)",
            name="ck_grade_sheets_reopen_is_deliberate",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    #: NULL is «без потока» — a bucket for solo students, not a missing value,
    #: which is why this is RESTRICT. Nulling it on a signed sheet does not
    #: forget the cohort: it moves the document into the «без потока» bucket,
    #: where it shadows that bucket's own page and collides with the unique
    #: index. A поток with a signed ведомость is not deletable.
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohorts.id", ondelete="RESTRICT"))
    #: The поток's name as it was, so the printed heading survives a rename.
    #: Resolved in the sheet's own ``locale``, not by "whichever translation
    #: was entered first" — that put an English поток name on a Russian page.
    cohort_name: Mapped[str | None] = mapped_column(Text)
    #: The course title as it read at closing, in the sheet's language.
    course_title: Mapped[str | None] = mapped_column(Text)
    #: The language this document was closed in. The interface locale belongs
    #: to the reader and changes per session; a signed document's language
    #: belongs to the document — printed, signed and filed, that paper stays in
    #: the language it was printed in.
    locale: Mapped[str] = mapped_column(Text, default="en", server_default="en")

    # --- The rest of the letterhead, frozen for the same reason -----------
    #
    # Every one of these is editable in a live table. Read at print time, a
    # school rename or a course restructure would rewrite the heading of every
    # document already signed and filed.
    school_name: Mapped[str | None] = mapped_column(Text)
    school_city: Mapped[str | None] = mapped_column(Text)
    teacher_name: Mapped[str | None] = mapped_column(Text)
    academic_hours: Mapped[int | None] = mapped_column()
    cohort_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cohort_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: The rules in force at closing. A school that moves its scale later must
    #: not move what this document says it certified.
    grading_scheme: Mapped[str] = mapped_column(Text)
    pass_threshold: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    reopen_reason: Mapped[str | None] = mapped_column(Text)
    #: Set when a later closing replaces this one. The old sheet is kept, so
    #: the history of what was signed survives a correction.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When this sheet replaced a reopened one — the «была переоткрыта» mark,
    #: carried onto the document that people will actually print. Stamping only
    #: the superseded page marks the copy nobody looks at again.
    corrects_sheet_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grade_sheets.id", ondelete="SET NULL"))
    correction_reason: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<GradeSheet course={self.course_id} cohort={self.cohort_id}>"


class GradeSheetRow(Base):
    """One student's line on a closed sheet."""

    __tablename__ = "grade_sheet_rows"
    __table_args__ = (
        # At most one of the two, exactly as `student_grades` and
        # `certificates` already have it. CASE rather than `num_nonnulls` so
        # SQLite can materialise it for the test suite.
        CheckConstraint(
            "(CASE WHEN official_code IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN official_score IS NULL THEN 0 ELSE 1 END) <= 1",
            name="ck_grade_sheet_rows_one_grade",
        ),
        CheckConstraint(
            "result_state IN ('pass', 'fail', 'completion_pass', 'not_attested')",
            name="grade_sheet_rows_result_state_check",
        ),
    )

    sheet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grade_sheets.id", ondelete="CASCADE"), primary_key=True)
    student_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    #: A result, not a computation state. The calculator's vocabulary answers
    #: "why is there no number"; a signed document answers "what did this
    #: person get", and those are different questions.
    result_state: Mapped[str] = mapped_column(Text)
    official_code: Mapped[str | None] = mapped_column(Text)
    official_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    #: The director-visible glyph: set by hand, not computed. A signing
    #: director should see that at a glance rather than have to ask.
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    #: The name the document was signed under. Read live, a student who marries
    #: and changes her surname rewrites a page already in the filing cabinet.
    student_name: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<GradeSheetRow student={self.student_id} {self.result_state}>"
