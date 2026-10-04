"""Weekly series of course events, as wall-clock times in a zone.

"Every Saturday at 20:00" means 20:00 on the teacher's clock — not
the same UTC instant every week. A class in Indianapolis at 20:00 EDT
is 00:00 UTC in October and 01:00 UTC after the clocks go back on
November 1; adding seven days of seconds would move it to 19:00 for
everyone. So occurrences are stepped on the wall clock of the zone
the teacher scheduled in and only then turned into instants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Session

    from app.models.course_event import CourseEvent

#: A school year of weekly classes. Past it, a typo in the end date
#: ("2027" for "2026") would quietly write hundreds of rows.
MAX_OCCURRENCES = 52


class SeriesRejected(ValueError):
    """The series cannot be built; ``reason`` is a stable identifier."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def zone_or_utc(name: str | None) -> ZoneInfo:
    """The IANA zone by that name, or UTC when there is none or it is unknown."""
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _at_wall_time(day: date, wall: datetime, zone: ZoneInfo) -> datetime:
    """``day`` at the wall-clock time of ``wall``, in ``zone``, as a UTC instant.

    A wall time that does not exist (inside the spring-forward gap) comes
    out an hour later, and an ambiguous one (the autumn repeat) takes its
    first reading — ``fold=0`` — which is what a person means by "20:00".
    """
    local = datetime(day.year, day.month, day.day, wall.hour, wall.minute, wall.second, tzinfo=zone)
    return local.astimezone(UTC)


@dataclass(frozen=True)
class WeeklySeries:
    first: datetime
    every_weeks: int
    until: date
    zone: ZoneInfo

    def occurrences(self) -> list[datetime]:
        """Every start, as UTC instants, from ``first`` through ``until``.

        ``until`` is a day on the zone's calendar and is inclusive: a
        series "until December 19" holds a class on December 19.
        """
        if self.every_weeks < 1:
            raise SeriesRejected("interval")
        first_local = self.first.astimezone(self.zone)
        if self.until < first_local.date():
            raise SeriesRejected("until_before_start")
        out: list[datetime] = []
        day = first_local.date()
        step = timedelta(weeks=self.every_weeks)
        while day <= self.until:
            if len(out) == MAX_OCCURRENCES:
                raise SeriesRejected("too_many")
            out.append(_at_wall_time(day, first_local, self.zone))
            day += step
        return out


def shift_on_wall_clock(instant: datetime, *, old_anchor: datetime, new_anchor: datetime, zone: ZoneInfo) -> datetime:
    """Move ``instant`` the way the anchor moved, measured on the wall clock.

    Editing "this and the following" lessons from 20:00 to 19:00 moves each
    of them to 19:00 on its own day, across a clock change; moving the
    anchor from Saturday to Sunday moves each one a day. The difference is
    taken between the anchor's two local readings, not between instants.
    """
    old_local = old_anchor.astimezone(zone).replace(tzinfo=None)
    new_local = new_anchor.astimezone(zone).replace(tzinfo=None)
    delta = new_local - old_local
    moved = instant.astimezone(zone).replace(tzinfo=None) + delta
    return moved.replace(tzinfo=zone).astimezone(UTC)


def series_positions(db: Session, events: Iterable[CourseEvent]) -> dict[str, tuple[int, int]]:
    """``{event_id: (index, count)}`` — each lesson's place in its series, 1-based.

    Eight Saturday lessons all read «Урок»; a student opening the fourth
    could not tell it from the first. The whole series is asked of the
    database rather than of ``events``: a course page has every lesson of
    the course, but a filtered calendar or a single saved lesson may not,
    and «3 из 3» for the third of eight would be a lie.
    """
    from app.models.course_event import CourseEvent

    series_ids = {e.series_id for e in events if e.series_id}
    if not series_ids:
        return {}
    rows = (
        db.query(CourseEvent.id, CourseEvent.series_id)
        .filter(CourseEvent.series_id.in_(series_ids))
        # The tie-break keeps the order stable when two lessons share an instant.
        .order_by(CourseEvent.series_id, CourseEvent.event_date, CourseEvent.id)
        .all()
    )
    by_series: dict[object, list[str]] = {}
    for event_id, series_id in rows:
        by_series.setdefault(series_id, []).append(str(event_id))
    positions: dict[str, tuple[int, int]] = {}
    for members in by_series.values():
        for index, event_id in enumerate(members, start=1):
            positions[event_id] = (index, len(members))
    return positions
