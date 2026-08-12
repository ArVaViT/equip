from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrgSettingsResponse(BaseModel):
    """What the school has decided about itself.

    The identity fields are printed on every ведомость; the grading fields are
    what new courses inherit and what every letter and «5» is resolved through.
    """

    model_config = ConfigDict(from_attributes=True)

    school_name_ru: str | None = None
    school_name_en: str | None = None
    city: str | None = None
    default_grading_scheme: str
    default_pass_threshold: Decimal
    #: ``{"letter": [[90, "A"], ...], "five_point": [[90, "5"], ...]}``.
    grade_bands: dict[str, Any] = {}
    updated_at: datetime | None = None
    updated_by: UUID | None = None


class OrgSettingsUpdate(BaseModel):
    """A partial edit: whatever is sent is written, the rest is left alone.

    Partial on purpose. A director fixing a typo in the city should not have to
    resend the band table, and a request that omitted it would otherwise wipe
    the school's scale — the one field on this row that silently re-labels every
    grade on the platform.
    """

    school_name_ru: str | None = Field(None, max_length=200)
    school_name_en: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=120)
    default_grading_scheme: Literal["pass_fail", "percent", "five_point", "letter"] | None = None
    default_pass_threshold: Decimal | None = Field(None, ge=0, le=100)
    #: Keyed by scheme. Validated in the route against the scheme it belongs to
    #: and against the pass line being written in the same request.
    grade_bands: dict[str, Any] | None = None
