"""The clock a school counts its days on.

The days a school puts its name to — the last day of an invitation link —
are days on the school's calendar. ``org_settings.time_zone`` holds it once
the school has said; until then the platform keeps the rule it had before
the column existed, which was the one school's zone written into the code.

The dates on a school's documents are read the same way — the day a
certificate was issued, the day a ведомость was closed — so a certificate
signed at 23:30 in Indianapolis is dated that day for everyone who reads it,
in Kyiv or in California, on paper and on the verification page.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
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


def day_on(zone: ZoneInfo, instant: datetime | None) -> date | None:
    """The calendar day ``instant`` falls on in ``zone`` (a naive value is UTC)."""
    if instant is None:
        return None
    aware = instant if instant.tzinfo is not None else instant.replace(tzinfo=UTC)
    return aware.astimezone(zone).date()


class SchoolClocks:
    """``school_time_zone`` for a page of rows, one lookup per school.

    A certificate list spans schools only rarely; asking once per row would
    still be one query per certificate.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._zones: dict[uuid.UUID | None, ZoneInfo] = {}

    def zone(self, organization_id: uuid.UUID | None) -> ZoneInfo:
        if organization_id not in self._zones:
            self._zones[organization_id] = school_time_zone(self._db, organization_id)
        return self._zones[organization_id]

    def day(self, organization_id: uuid.UUID | None, instant: datetime | None) -> date | None:
        """The school's day for ``instant`` — the date its documents print."""
        return day_on(self.zone(organization_id), instant)
