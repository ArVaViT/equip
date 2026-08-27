import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base

# JSONB in Postgres, plain JSON on the SQLite test backend — the model has to
# materialize on both (conftest builds the schema from these models).
JSONVariant = JSONB().with_variant(JSON(), "sqlite")

# Shipped defaults, mirrored in migration 20260806140314. ``letter`` bands are
# the ones grade_calculator has applied all along; the five-point scale comes
# from the redesign research (RU/UA «5 от 90», «3» at the pass line).
DEFAULT_GRADE_BANDS: dict[str, list[list]] = {
    "letter": [[90, "A"], [80, "B"], [70, "C"], [60, "D"], [0, "F"]],
    "five_point": [[90, "5"], [75, "4"], [70, "3"], [0, "2"]],
}


class OrgSettings(Base):
    """School-wide settings — a deliberate single row.

    Holds what the institution decides rather than what a teacher picks: the
    default grading scheme new courses inherit, the pass threshold, the band
    boundaries behind each scheme, and the identity fields printed on the
    ведомость header.

    Why a table and not constants: RU/UA five-point conversions genuinely vary
    between schools («5 от 85» is as common in UA practice as «5 от 90»).
    Hardcoding bands would make onboarding every new school a code change.

    One row per organization. It used to be one row for the platform: a
    boolean primary key constrained to ``True``, the idiom that makes a
    second row impossible. That comment predicted its own replacement —
    "the boolean becomes an org id and every other column travels
    unchanged" — and on 2026-08-27 it did exactly that.
    """

    __tablename__ = "org_settings"
    __table_args__ = (
        CheckConstraint(
            "default_grading_scheme IN ('pass_fail', 'percent', 'five_point', 'letter')",
            name="org_settings_default_grading_scheme_check",
        ),
        CheckConstraint(
            "default_pass_threshold >= 0 AND default_pass_threshold <= 100",
            name="org_settings_default_pass_threshold_check",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )

    school_name_ru: Mapped[str | None] = mapped_column()
    school_name_en: Mapped[str | None] = mapped_column()
    city: Mapped[str | None] = mapped_column()

    # Inherited by new courses (D1). Changing a course away from the default is
    # an admin action — if every teacher picked independently, one school's
    # transcript would mix «зачёт», «4 (хорошо)» and «B».
    default_grading_scheme: Mapped[str] = mapped_column(default="letter", server_default="letter")
    default_pass_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("70"), server_default="70")

    # Admin-editable, app-validated (monotonic, bounded, five_point «3» floor
    # consistent with the threshold). Teachers never see this surface.
    grade_bands: Mapped[dict] = mapped_column(JSONVariant, default=dict, server_default="{}")

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
