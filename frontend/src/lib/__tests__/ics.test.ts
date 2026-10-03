import { describe, expect, it } from "vitest"
import type { CalendarEvent } from "@/types"
import { escapeText, eventToIcs, foldLine, formatUtc, googleCalendarUrl, icsFileName } from "../ics"

const event = (over: Partial<CalendarEvent> = {}): CalendarEvent => ({
  id: "e1",
  title: "Тематическая проповедь",
  description: null,
  event_type: "live_session",
  event_date: "2026-10-11T13:00:00Z",
  meeting_url: null,
  course_id: "c1",
  course_title: "Курс проповеди — I",
  source: "course_event",
  ...over,
} as CalendarEvent)

const octets = (s: string) => new TextEncoder().encode(s).length

describe("one event as an .ics file", () => {
  it("carries the feed's UID, so an event added by hand and by subscription is one event", () => {
    expect(eventToIcs(event())).toContain("UID:course_event-e1@equipbible.com")
  })

  it("gives the start as a UTC instant and the feed's length: an hour for a session, none for a deadline", () => {
    const ics = eventToIcs(event())
    expect(ics).toContain("DTSTART:20261011T130000Z")
    expect(ics).toContain("DURATION:PT1H")
    expect(eventToIcs(event({ source: "assignment_deadline", event_type: "deadline" }))).toContain("DURATION:PT0S")
    // A teacher's own course event can be a deadline too: it stays a moment.
    expect(eventToIcs(event({ event_type: "deadline" }))).toContain("DURATION:PT0S")
    expect(formatUtc(new Date("2026-01-02T03:04:05.678Z"))).toBe("20260102T030405Z")
  })

  it("uses the event's own length and rings half an hour before a class, never before a deadline", () => {
    const ics = eventToIcs(event({ duration_minutes: 90 }))
    expect(ics).toContain("DURATION:PT90M")
    expect(ics).toContain("TRIGGER:-PT30M")
    expect(eventToIcs(event({ event_type: "deadline" }))).not.toContain("VALARM")
  })

  it("escapes text so a comma does not swallow the rest of the title", () => {
    expect(escapeText("a, b; c\\d\ne")).toBe("a\\, b\\; c\\\\d\\ne")
    expect(eventToIcs(event({ title: "Урок 1, часть 2" }))).toContain("SUMMARY:Урок 1\\, часть 2")
  })

  it("folds at 75 octets, never inside a Cyrillic letter", () => {
    const line = "SUMMARY:" + "Проповедь ".repeat(20)
    const folded = foldLine(line)
    for (const part of folded.split("\r\n")) expect(octets(part)).toBeLessThanOrEqual(75)
    expect(folded.split("\r\n").map((p, i) => (i ? p.slice(1) : p)).join("")).toBe(line)
    expect(folded).not.toContain("�")
  })

  it("puts a meeting link where both Google and Apple will find it, unescaped as a URL", () => {
    const ics = eventToIcs(event({ meeting_url: "https://zoom.us/j/1?pwd=a,b" }))
    expect(ics).toContain("LOCATION:https://zoom.us/j/1?pwd=a\\,b")
    expect(ics).toContain("URL:https://zoom.us/j/1?pwd=a,b")
  })

  it("names the file after the event", () => {
    expect(icsFileName(event())).toBe("Тематическая-проповедь.ics")
    expect(icsFileName(event({ title: "!!!" }))).toBe("event.ics")
  })
})

describe("a recording on the event", () => {
  it("goes into the description, under its label", () => {
    const ics = eventToIcs(
      {
        id: "e1",
        title: "Live class",
        description: null,
        event_type: "live_session",
        event_date: "2026-09-28T18:00:00Z",
        meeting_url: null,
        recording_url: "https://youtu.be/abc",
        course_id: "c1",
        course_title: "Acts",
        source: "course_event",
      },
      new Date("2026-10-01T00:00:00Z"),
      "Запись занятия",
    )
    expect(ics.replace(/\r\n /g, "")).toContain("DESCRIPTION:Acts\\nЗапись занятия: https://youtu.be/abc")
  })

  it("builds a Google add link with the class's span and its meeting", () => {
    const url = new URL(googleCalendarUrl(event({ duration_minutes: 90, meeting_url: "https://zoom.us/j/1" })) ?? "")
    expect(url.origin + url.pathname).toBe("https://calendar.google.com/calendar/render")
    expect(url.searchParams.get("action")).toBe("TEMPLATE")
    expect(url.searchParams.get("dates")).toBe("20261011T130000Z/20261011T143000Z")
    expect(url.searchParams.get("location")).toBe("https://zoom.us/j/1")
    // A deadline is a moment: start and end are the same instant.
    const ddl = new URL(googleCalendarUrl(event({ event_type: "deadline" })) ?? "")
    expect(ddl.searchParams.get("dates")).toBe("20261011T130000Z/20261011T130000Z")
    // No readable start: no link rather than a thrown RangeError mid-render.
    expect(googleCalendarUrl(event({ event_date: "" }))).toBeNull()
  })
})
