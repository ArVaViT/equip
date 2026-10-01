import { describe, expect, it } from "vitest"
import type { CalendarEvent } from "@/types"
import { escapeText, eventToIcs, foldLine, formatUtc, icsFileName } from "../ics"

const event = (over: Partial<CalendarEvent> = {}): CalendarEvent => ({
  id: "e1",
  title: "Тематическая проповедь",
  description: null,
  event_type: "course_event",
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

  it("gives the start as a UTC instant and no length, like the feed", () => {
    const ics = eventToIcs(event())
    expect(ics).toContain("DTSTART:20261011T130000Z")
    expect(ics).toContain("DURATION:PT0S")
    expect(formatUtc(new Date("2026-01-02T03:04:05.678Z"))).toBe("20260102T030405Z")
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
