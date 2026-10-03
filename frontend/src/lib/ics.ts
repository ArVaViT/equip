/**
 * One calendar event as an `.ics` file — the "add to calendar" next to a
 * single deadline or live session.
 *
 * The same shape as the subscription feed (`backend/app/services/
 * calendar_ical.py`), on purpose: the same `UID`, so a reader who both
 * subscribed and added the event by hand sees it once, not twice; the
 * same duration — the event's own length when it has one, otherwise zero
 * for a deadline and an hour for a live session or an exam; the same
 * half-hour alarm for a class; and both
 * `LOCATION` and `URL` for a meeting link, because Google reads only the
 * first and Apple only the second.
 *
 * One difference: lines fold at 75 *octets* of UTF-8, as RFC 5545 §3.1
 * says, never inside a character. A Cyrillic title is two bytes a letter,
 * so folding by characters (as the feed does) leaves lines past the limit.
 */
import type { CalendarEvent } from "@/types"

const DOMAIN = "equipbible.com"
const PRODID = "-//Equip//Calendar//EN"

/** RFC 5545 §3.3.11 — TEXT values escape backslash, `;`, `,` and newlines. */
export function escapeText(text: string): string {
  return text
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\r\n|\r|\n/g, "\\n")
}

const encoder = new TextEncoder()

/** RFC 5545 §3.1 — at most 75 octets a line; continuations start with a space. */
export function foldLine(line: string): string {
  if (encoder.encode(line).length <= 75) return line
  const parts: string[] = []
  let current = ""
  let size = 0
  for (const char of line) {
    const bytes = encoder.encode(char).length
    // The first line holds 75 octets; a continuation holds 74 after its space.
    const limit = parts.length === 0 ? 75 : 74
    if (size + bytes > limit) {
      parts.push(current)
      current = ""
      size = 0
    }
    current += char
    size += bytes
  }
  parts.push(current)
  return parts.join("\r\n ")
}

/** `YYYYMMDDTHHMMSSZ` — the UTC instant, which every client shows in its own zone. */
export function formatUtc(date: Date): string {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z")
}

function takesTimeOfDay(eventType: string): boolean {
  return eventType === "live_session" || eventType === "exam"
}

/** The event's own length; without one, an hour for a class or an exam and none for a deadline. */
export function icsDuration(event: Pick<CalendarEvent, "event_type" | "duration_minutes">): string {
  if (event.duration_minutes) return `PT${event.duration_minutes}M`
  return takesTimeOfDay(event.event_type) ? "PT1H" : "PT0S"
}

export function eventToIcs(event: CalendarEvent, now: Date = new Date(), recordingLabel?: string): string {
  const start = new Date(event.event_date)
  const recording = event.recording_url ? `${recordingLabel ?? "Recording"}: ${event.recording_url}` : null
  const description = [event.course_title, event.description, recording].filter(Boolean).join("\n")
  const lines = [
    "BEGIN:VCALENDAR",
    `PRODID:${PRODID}`,
    "VERSION:2.0",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    foldLine(`UID:${event.source}-${event.id}@${DOMAIN}`),
    `DTSTAMP:${formatUtc(now)}`,
    `DTSTART:${formatUtc(start)}`,
    `DURATION:${icsDuration(event)}`,
    foldLine(`SUMMARY:${escapeText(event.title)}`),
  ]
  if (description) lines.push(foldLine(`DESCRIPTION:${escapeText(description)}`))
  if (event.meeting_url) {
    // URL is a URI, not TEXT: escaping a comma inside a query string would
    // break the address. The server already refused control characters.
    lines.push(foldLine(`LOCATION:${escapeText(event.meeting_url)}`))
    lines.push(foldLine(`URL:${event.meeting_url}`))
  }
  lines.push(`CATEGORIES:${escapeText(event.event_type)}`)
  if (takesTimeOfDay(event.event_type)) {
    // The feed's alarm, the same half hour: a phone that has the event
    // should say something before the class, not at it.
    lines.push("BEGIN:VALARM", "ACTION:DISPLAY", foldLine(`DESCRIPTION:${escapeText(event.title)}`), "TRIGGER:-PT30M", "END:VALARM")
  }
  lines.push("END:VEVENT", "END:VCALENDAR")
  return lines.join("\r\n") + "\r\n"
}

/** A file name a phone will keep: letters, digits and dashes from the title. */
export function icsFileName(event: CalendarEvent): string {
  const slug = event.title
    .replace(/[^\p{L}\p{M}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
  return `${slug || "event"}.ics`
}

/**
 * The same event as a Google Calendar "add" link — for the reader whose
 * calendar is Google on an Android phone or in a browser, where an `.ics`
 * download lands in Files and goes no further.
 */
export function googleCalendarUrl(event: CalendarEvent, recordingLabel?: string): string {
  const start = new Date(event.event_date)
  const minutes = event.duration_minutes ?? (takesTimeOfDay(event.event_type) ? 60 : 0)
  const end = new Date(start.getTime() + minutes * 60_000)
  const recording = event.recording_url ? `${recordingLabel ?? "Recording"}: ${event.recording_url}` : null
  const details = [event.course_title, event.description, event.meeting_url, recording].filter(Boolean).join("\n")
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: event.title,
    dates: `${formatUtc(start)}/${formatUtc(end)}`,
  })
  if (details) params.set("details", details)
  if (event.meeting_url) params.set("location", event.meeting_url)
  return `https://calendar.google.com/calendar/render?${params.toString()}`
}
