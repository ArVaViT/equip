"""The clock a school counts its days on.

The days a school puts its name to — the last day of an invitation link —
are days on the school's calendar. ``org_settings.time_zone`` holds it once
the school has said; until then the platform keeps the rule it had before
the column existed, which was the one school's zone written into the code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

#: Where every school's clock was before a school could name its own.
DEFAULT_SCHOOL_TIME_ZONE = "America/Indiana/Indianapolis"


def school_time_zone(db: Session, organization_id: uuid.UUID | None) -> ZoneInfo:
    """The school's zone, else the platform default.

    Read without creating the settings row (``get_org_settings`` would):
    asking for a clock is not a reason to write anything.
    """
    from app.models.org_settings import OrgSettings

    name = None
    if organization_id is not None:
        name = db.query(OrgSettings.time_zone).filter(OrgSettings.organization_id == organization_id).scalar()
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            # The API refuses an unknown name; one written by hand that is
            # unknown falls back to the default, not to UTC.
            pass
    return ZoneInfo(DEFAULT_SCHOOL_TIME_ZONE)
