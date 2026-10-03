import { describe, expect, it } from "vitest"
import { eventEnd, isJoinableNow, isOver, minutesUntil, seriesLastDay } from "../eventTime"

const start = "2026-10-25T00:00:00Z"
const t = (iso: string) => Date.parse(iso)

describe("event time", () => {
  it("ends after its own length", () => {
    const e = { event_date: start, event_type: "live_session" as const, duration_minutes: 90 }
    expect(eventEnd(e)?.toISOString()).toBe("2026-10-25T01:30:00.000Z")
    expect(isOver(e, t("2026-10-25T01:29:00Z"))).toBe(false)
    expect(isOver(e, t("2026-10-25T01:30:00Z"))).toBe(true)
  })

  it("without a length is over three hours after the start, as before", () => {
    const e = { event_date: start, event_type: "live_session" as const }
    expect(eventEnd(e)).toBeNull()
    expect(isOver(e, t("2026-10-25T02:59:00Z"))).toBe(false)
    expect(isOver(e, t("2026-10-25T03:01:00Z"))).toBe(true)
  })

  it("can be joined from fifteen minutes before the start until it ends", () => {
    const e = { event_date: start, event_type: "live_session" as const, duration_minutes: 60 }
    expect(isJoinableNow(e, t("2026-10-24T23:44:00Z"))).toBe(false)
    expect(isJoinableNow(e, t("2026-10-24T23:45:00Z"))).toBe(true)
    expect(isJoinableNow(e, t("2026-10-25T00:59:00Z"))).toBe(true)
    expect(isJoinableNow(e, t("2026-10-25T01:00:00Z"))).toBe(false)
  })

  it("counts whole minutes until the start, and none once it began", () => {
    const e = { event_date: start, event_type: "live_session" as const }
    expect(minutesUntil(e, t("2026-10-24T23:00:30Z"))).toBe(60)
    expect(minutesUntil(e, t("2026-10-25T00:00:00Z"))).toBeNull()
  })

  it("puts the last class of a series on the right day, across a month end", () => {
    expect(seriesLastDay("2026-10-24T20:00", 1, 8)).toBe("2026-12-12")
    expect(seriesLastDay("2026-10-24T20:00", 2, 3)).toBe("2026-11-21")
    expect(seriesLastDay("2026-10-24T20:00", 1, 1)).toBe("2026-10-24")
    expect(seriesLastDay("garbage", 1, 4)).toBeNull()
  })
})
