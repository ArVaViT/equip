"""iCal (RFC 5545) export for a user's course-calendar events.

Students subscribe to a feed URL from Google Calendar / Apple Calendar
/ Outlook to see Equip module deadlines + course events + assignment
due dates without opening the dashboard. The feed is read-only — we
don't accept ICS uploads or bidirectional sync. Two-way Google
Calendar OAuth sync is a separate task that needs Google API
credentials.

Auth model
----------
The feed URL carries an HMAC-signed token (``?token=...``) bound to
the user's id with a long expiry. The token is issued by
``POST /calendar/ical/token``; rotation revokes the previous token
because the JWT ``iat`` is part of the signed payload.

ICS shape
---------
- One ``VEVENT`` per Equip ``CalendarEvent`` (module deadlines,
  assignments, course events).
- ``UID`` = ``"<source>-<id>@equipbible.com"`` so re-subscribing
  updates the existing entries rather than duplicating.
- ``DTSTART`` is the UTC instant from the event row; deadlines have
  no duration (``DURATION:PT0S``).
- Times are emitted in UTC (``...Z``); the client renders in the
  user's timezone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.calendar import CalendarEvent


_PRODID = "-//Equip//Calendar//EN"
_DOMAIN = "equipbible.com"


def _escape(text: str) -> str:
    """RFC 5545 §3.3.11 — escape commas, semicolons, and newlines.
    Apple Calendar / Google Calendar are strict about unescaped
    commas; an unescaped ``,`` swallows the rest of the property."""
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 §3.1 — fold lines longer than 75 octets across CRLF +
    leading space. Most calendar clients tolerate unfolded lines but
    spec compliance avoids surprises on Outlook in particular."""
    if len(line) <= 75:
        return line
    parts: list[str] = []
    while line:
        parts.append(line[:75])
        line = line[75:]
        if line:
            line = " " + line
    return "\r\n".join(parts)


def _format_dt(value: datetime) -> str:
    """UTC instant in ICS form: ``YYYYMMDDTHHMMSSZ``. Inputs from the
    ORM are timezone-aware; naive datetimes are treated as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def render_calendar(events: list[CalendarEvent], *, user_email: str | None = None) -> str:
    """Serialize ``events`` to an RFC 5545 VCALENDAR.

    ``user_email`` shows up in the ``X-WR-CALNAME`` so the user sees
    "Equip Calendar (foo@example.com)" in their client's calendar
    list — useful when they subscribe from multiple accounts."""
    now_stamp = _format_dt(datetime.now(UTC))
    calname = "Equip Calendar"
    if user_email:
        calname = f"{calname} ({user_email})"

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        f"PRODID:{_PRODID}",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _fold(f"X-WR-CALNAME:{_escape(calname)}"),
        "X-WR-TIMEZONE:UTC",
    ]

    for event in events:
        uid = f"{event.source}-{event.id}@{_DOMAIN}"
        summary = event.title
        description_parts: list[str] = []
        if event.course_title:
            description_parts.append(event.course_title)
        if event.description:
            description_parts.append(event.description)
        description = "\n".join(description_parts)

        lines.extend(
            [
                "BEGIN:VEVENT",
                _fold(f"UID:{uid}"),
                f"DTSTAMP:{now_stamp}",
                f"DTSTART:{_format_dt(event.event_date)}",
                # Deadline-style events: 0-duration so the client renders
                # a single dot, not a multi-hour block.
                "DURATION:PT0S",
                _fold(f"SUMMARY:{_escape(summary)}"),
            ]
        )
        if description:
            lines.append(_fold(f"DESCRIPTION:{_escape(description)}"))
        if event.meeting_url:
            # Both properties, because no single one of them works in
            # both clients a student actually subscribes from.
            #
            # Apple Calendar shows URL as a "URL" row in the inspector
            # and makes it clickable; it does not linkify LOCATION.
            # Google Calendar is the mirror image — it ignores the URL
            # property on an imported event entirely, and renders a
            # LOCATION that parses as a URL as a link. Zoom's and
            # Teams' own .ics exports emit both for exactly this
            # reason, so this is the shape those clients are tuned for.
            #
            # LOCATION is TEXT (RFC 5545 §3.8.1.7), so its commas and
            # semicolons are escaped like any other text value. URL's
            # value type is URI (§3.8.4.6) and must NOT be text-escaped:
            # a backslash in front of a comma inside a query string is
            # part of the address as far as the client is concerned, and
            # it would hand the student a broken link. Written bare
            # rather than as ``URL;VALUE=URI:`` — URI is already the
            # default type, and the bare form is what the RFC's own
            # example and every exporter in the wild emit, so it is the
            # form parsers are actually tested against.
            #
            # The value is safe to emit raw because
            # ``normalize_meeting_url`` has already refused every
            # newline and control character. Without that, a link could
            # close this line and write properties of its own into the
            # feed.
            lines.append(_fold(f"LOCATION:{_escape(event.meeting_url)}"))
            lines.append(_fold(f"URL:{event.meeting_url}"))
        lines.append(f"CATEGORIES:{_escape(event.event_type)}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


__all__ = ["render_calendar"]
