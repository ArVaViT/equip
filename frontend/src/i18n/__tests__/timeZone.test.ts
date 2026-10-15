import { afterEach, describe, expect, it } from "vitest"

import { formatDate, formatDateTime, isoToLocalInput, localInputToIso } from "../format"
import {
  getDisplayTimeZone,
  isValidTimeZone,
  setDisplayTimeZone,
  timeZoneLabel,
  timeZoneOffsetMinutes,
  timeZoneOptionLabel,
  zonedDayKey,
  zonedParts,
  zonedWallTimeToUtc,
} from "../timeZone"

/**
 * UTC is the one truth; each reader sees it in their own zone. These pin the
 * owner's example — a teacher in Indiana sets a live lesson for 8:00 — and
 * the DST edges, independent of the zone the machine running them is in.
 */
describe("one instant, read in each person's zone", () => {
  afterEach(() => setDisplayTimeZone(null))

  it("a teacher in Indiana typing 08:00 stores the instant, not the wall clock", () => {
    // October: Indiana is on EDT (UTC-4).
    expect(localInputToIso("2026-10-05T08:00", "America/Indiana/Indianapolis")).toBe("2026-10-05T12:00:00.000Z")
    // January: EST (UTC-5).
    expect(localInputToIso("2027-01-11T08:00", "America/Indiana/Indianapolis")).toBe("2027-01-11T13:00:00.000Z")
  })

  it("students elsewhere see that lesson in their own time", () => {
    const lesson = "2026-10-05T12:00:00.000Z"
    expect(isoToLocalInput(lesson, "America/Los_Angeles")).toBe("2026-10-05T05:00")
    expect(isoToLocalInput(lesson, "America/New_York")).toBe("2026-10-05T08:00")
    expect(isoToLocalInput(lesson, "Europe/Berlin")).toBe("2026-10-05T14:00")
    expect(isoToLocalInput(lesson, "Europe/Kyiv")).toBe("2026-10-05T15:00")
  })

  it("the profile's zone wins over the browser's once set", () => {
    setDisplayTimeZone("Asia/Tokyo")
    expect(getDisplayTimeZone()).toBe("Asia/Tokyo")
    expect(formatDateTime("2026-10-05T12:00:00Z")).toBe("2026-10-05 21:00:00")
    // The calendar day can differ from UTC's.
    expect(formatDate("2026-10-05T20:00:00Z")).toBe("2026-10-06")
  })

  it("an unknown zone is ignored rather than trusted", () => {
    setDisplayTimeZone("Mars/Olympus")
    expect(isValidTimeZone("Mars/Olympus")).toBe(false)
    expect(getDisplayTimeZone()).not.toBe("Mars/Olympus")
  })

  it("round-trips a picker value in the same zone", () => {
    for (const tz of ["America/Denver", "Europe/Kyiv", "Pacific/Auckland", "Asia/Kolkata"]) {
      expect(isoToLocalInput(localInputToIso("2026-03-20T19:45", tz), tz)).toBe("2026-03-20T19:45")
    }
  })

  it("a wall time skipped by the spring change lands on the clock that happened", () => {
    // 2027-03-14 02:30 does not exist in New York (02:00 → 03:00).
    const d = zonedWallTimeToUtc(2027, 3, 14, 2, 30, 0, "America/New_York")
    expect(isoToLocalInput(d.toISOString(), "America/New_York")).toBe("2027-03-14T03:30")
  })

  it("a wall time doubled by the autumn change takes the earlier one", () => {
    // 2026-11-01 01:30 happens twice in New York; the first is EDT (UTC-4).
    expect(zonedWallTimeToUtc(2026, 11, 1, 1, 30, 0, "America/New_York").toISOString()).toBe(
      "2026-11-01T05:30:00.000Z",
    )
  })

  it("takes the earlier of a doubled wall time east of Greenwich too", () => {
    // 2026-10-25: Berlin 02:30 happens at 00:30Z (CEST) and 01:30Z (CET);
    // Kyiv 03:30 at 00:30Z (EEST) and 01:30Z (EET).
    expect(zonedWallTimeToUtc(2026, 10, 25, 2, 30, 0, "Europe/Berlin").toISOString()).toBe("2026-10-25T00:30:00.000Z")
    expect(zonedWallTimeToUtc(2026, 10, 25, 3, 30, 0, "Europe/Kyiv").toISOString()).toBe("2026-10-25T00:30:00.000Z")
  })

  it("moves a skipped spring wall time forward east of Greenwich too", () => {
    // 2027-03-28: Berlin 02:30 does not happen (02:00 → 03:00 CEST).
    const d = zonedWallTimeToUtc(2027, 3, 28, 2, 30, 0, "Europe/Berlin")
    expect(isoToLocalInput(d.toISOString(), "Europe/Berlin")).toBe("2027-03-28T03:30")
  })

  it("an instant read on the wall and back is the same instant, all year, on both sides of Greenwich", () => {
    for (const tz of ["America/Los_Angeles", "America/Indiana/Indianapolis", "Europe/Berlin", "Europe/Kyiv", "Australia/Sydney"]) {
      for (let t = Date.UTC(2026, 0, 1); t < Date.UTC(2027, 0, 1); t += 7 * 3600 * 1000) {
        const p = zonedParts(new Date(t), tz)
        const back = zonedWallTimeToUtc(p.year, p.month, p.day, p.hour, p.minute, p.second, tz).getTime()
        // A doubled autumn hour gives back the earlier of its two instants.
        expect(back === t || back === t - 3600 * 1000, `${tz} ${new Date(t).toISOString()}`).toBe(true)
      }
    }
  })

  it("a date-only value is midnight in the reader's zone, not in UTC", () => {
    expect(localInputToIso("2026-10-01", "America/Indiana/Indianapolis")).toBe("2026-10-01T04:00:00.000Z")
  })

  it("groups by the reader's calendar day", () => {
    const late = new Date("2026-10-06T02:30:00Z")
    expect(zonedDayKey(late, "America/Los_Angeles")).toBe("2026-10-05")
    expect(zonedDayKey(late, "Europe/Berlin")).toBe("2026-10-06")
  })

  it("names the zone so nobody wonders whose 8:00 it is", () => {
    expect(timeZoneLabel("en-US", "America/New_York", new Date("2026-10-05T12:00:00Z"))).toBe("EDT")
    expect(timeZoneLabel("en-US", "UTC", new Date("2026-10-05T12:00:00Z"))).toBe("UTC")
  })

  it("names a zone for a person, in their language, and knows its offset", () => {
    const at = new Date("2026-10-05T12:00:00Z")
    expect(timeZoneOptionLabel("ru-RU", "Europe/Kyiv", at)).toMatch(/^Kyiv — Восточная Европа · GMT\+3$/)
    expect(timeZoneOptionLabel("en-US", "America/Indiana/Indianapolis", at)).toBe("Indianapolis — Eastern Time · EDT")
    expect(timeZoneOffsetMinutes("America/Los_Angeles", at)).toBe(-420)
    expect(timeZoneOffsetMinutes("Asia/Kolkata", at)).toBe(330)
  })

})
