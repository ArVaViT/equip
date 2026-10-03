import { afterEach, beforeEach, describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { setDisplayTimeZone } from "@/i18n/timeZone"
import { formatEventTimeRange } from "../eventTimeFormat"

const at = (iso: string, minutes?: number) => ({ event_date: iso, event_type: "live_session" as const, duration_minutes: minutes })

describe("a class's time range", () => {
  beforeEach(() => setDisplayTimeZone("Europe/Kyiv"))
  afterEach(async () => {
    setDisplayTimeZone(null)
    await i18n.changeLanguage("en")
  })

  it("reads 09:05 and 00:30 on a 24-hour clock", async () => {
    await i18n.changeLanguage("ru")
    expect(formatEventTimeRange(at("2026-10-05T06:05:00Z"))).toBe("09:05")
    expect(formatEventTimeRange(at("2026-10-05T20:00:00Z", 90))).toBe("23:00–00:30")
  })

  it("reads 9:05 AM, not 09:05 AM, on a 12-hour clock", async () => {
    await i18n.changeLanguage("en")
    expect(formatEventTimeRange(at("2026-10-05T06:05:00Z"))).toMatch(/^9:05\sAM$/)
  })
})
