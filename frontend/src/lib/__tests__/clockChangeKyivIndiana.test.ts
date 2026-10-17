/**
 * Kyiv goes back an hour on October 25, 2026; Indianapolis on November 1.
 * For that one week a class at 19:00 in Indiana is at 01:00 in Kyiv instead
 * of 02:00. Every instant is stored in UTC and shown on the reader's clock
 * (profile zone, else browser), so the week takes care of itself — these
 * pin that it does, on both dates and in between, whatever zone the
 * browser itself runs in.
 */
import { afterEach, describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { isoToLocalInput, localInputToIso } from "@/i18n/format"
import { setDisplayTimeZone, zonedDayKey } from "@/i18n/timeZone"
import { formatEventTimeRange } from "@/components/calendar/eventTimeFormat"
import { eventDayKey, seriesLastDay } from "@/lib/eventTime"
import { eventToIcs } from "@/lib/ics"
import type { CalendarEvent } from "@/types"

const INDY = "America/Indiana/Indianapolis"
const KYIV = "Europe/Kyiv"

// Saturdays at 19:00 in Indianapolis, as the server stores them.
const INDY_SATURDAYS = [
  "2026-10-17T23:00:00Z", // before both changes
  "2026-10-24T23:00:00Z", // the night Kyiv changes (at 01:00Z on the 25th)
  "2026-10-31T23:00:00Z", // the week between
  "2026-11-08T00:00:00Z", // after both (19:00 EST)
]

const lesson = (iso: string) => ({ event_date: iso, event_type: "live_session" as const, duration_minutes: 90 })

describe("the week between Kyiv's and Indiana's clock changes", () => {
  afterEach(async () => {
    setDisplayTimeZone(null)
    await i18n.changeLanguage("en")
  })

  it("shows an Indiana class at 19:00 in Indiana and an hour earlier in Kyiv only that week", async () => {
    await i18n.changeLanguage("uk")
    setDisplayTimeZone(INDY)
    expect(INDY_SATURDAYS.map((d) => formatEventTimeRange(lesson(d)))).toEqual([
      "19:00–20:30",
      "19:00–20:30",
      "19:00–20:30",
      "19:00–20:30",
    ])
    setDisplayTimeZone(KYIV)
    expect(INDY_SATURDAYS.map((d) => formatEventTimeRange(lesson(d)))).toEqual([
      "02:00–03:30",
      "02:00–03:30",
      "01:00–02:30",
      "02:00–03:30",
    ])
  })

  it("files the class under the reader's own day", () => {
    setDisplayTimeZone(KYIV)
    expect(INDY_SATURDAYS.map((d) => eventDayKey({ event_date: d }))).toEqual([
      "2026-10-18",
      "2026-10-25",
      "2026-11-01",
      "2026-11-08",
    ])
    setDisplayTimeZone(INDY)
    expect(INDY_SATURDAYS.map((d) => eventDayKey({ event_date: d }))).toEqual([
      "2026-10-17",
      "2026-10-24",
      "2026-10-31",
      "2026-11-07",
    ])
  })

  it("turns 19:00 typed in either zone into the right instant on every date", () => {
    expect(["2026-10-17", "2026-10-24", "2026-10-31", "2026-11-07"].map((d) => localInputToIso(`${d}T19:00`, INDY))).toEqual(
      INDY_SATURDAYS.map((d) => new Date(d).toISOString()),
    )
    expect(["2026-10-21", "2026-10-28", "2026-11-04"].map((d) => localInputToIso(`${d}T19:00`, KYIV))).toEqual([
      "2026-10-21T16:00:00.000Z",
      "2026-10-28T17:00:00.000Z",
      "2026-11-04T17:00:00.000Z",
    ])
  })

  it("reads a time inside the repeated hour as its first occurrence", () => {
    expect(localInputToIso("2026-10-25T03:30", KYIV)).toBe("2026-10-25T00:30:00.000Z")
    expect(localInputToIso("2026-11-01T01:30", INDY)).toBe("2026-11-01T05:30:00.000Z")
    // The second 01:30 shows as 01:30 too — which is why the editor sends
    // an untouched date back as the instant it received.
    expect(isoToLocalInput("2026-11-01T06:30:00Z", INDY)).toBe("2026-11-01T01:30")
  })

  it("counts a series' last day on the calendar, not in hours", () => {
    expect(seriesLastDay("2026-10-17T19:00", 1, 4)).toBe("2026-11-07")
  })

  it("turns the reader's day at their midnight on a 25-hour day", () => {
    // Kyiv's October 25 runs from 21:00Z on the 24th to 22:00Z on the 25th.
    expect(zonedDayKey(new Date("2026-10-24T20:59:00Z"), KYIV)).toBe("2026-10-24")
    expect(zonedDayKey(new Date("2026-10-24T21:00:00Z"), KYIV)).toBe("2026-10-25")
    expect(zonedDayKey(new Date("2026-10-25T21:59:00Z"), KYIV)).toBe("2026-10-25")
    expect(zonedDayKey(new Date("2026-10-25T22:00:00Z"), KYIV)).toBe("2026-10-26")
    // Indiana's November 1 runs from 04:00Z to 05:00Z the next day.
    expect(zonedDayKey(new Date("2026-11-01T03:59:00Z"), INDY)).toBe("2026-10-31")
    expect(zonedDayKey(new Date("2026-11-02T04:59:00Z"), INDY)).toBe("2026-11-01")
    expect(zonedDayKey(new Date("2026-11-02T05:00:00Z"), INDY)).toBe("2026-11-02")
  })

  it("puts the UTC instant in the .ics, which every calendar shows on its own clock", () => {
    const event = {
      id: "e1",
      title: "Урок",
      event_type: "live_session",
      event_date: INDY_SATURDAYS[2],
      duration_minutes: 90,
      course_id: "c",
      source: "course_event",
    } as unknown as CalendarEvent
    const ics = eventToIcs(event, new Date("2026-10-20T00:00:00Z"))
    expect(ics).toContain("DTSTART:20261031T230000Z")
    expect(ics).not.toContain("TZID")
    expect(ics).not.toContain("RRULE")
  })
})
