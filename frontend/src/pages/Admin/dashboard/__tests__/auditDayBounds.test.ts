import { afterEach, describe, expect, it } from "vitest"
import { setDisplayTimeZone } from "@/i18n/timeZone"
import { dayEndUtc, dayStartUtc } from "../useAdminAudit"

/**
 * The audit filter's days are the reader's, the same calendar the table
 * prints its timestamps in. They were the browser's: an admin whose profile
 * says Tokyo, on a laptop still set to Indiana, asked for the 30th and got
 * rows the table itself dates the 29th and the 1st.
 */
describe("the audit filter's day", () => {
  afterEach(() => setDisplayTimeZone(null))

  it("starts and ends at the reader's midnight", () => {
    setDisplayTimeZone("Asia/Tokyo")
    expect(dayStartUtc("2026-09-30").toISOString()).toBe("2026-09-29T15:00:00.000Z")
    expect(dayEndUtc("2026-09-30").toISOString()).toBe("2026-09-30T14:59:59.999Z")
  })

  it("crosses a month end", () => {
    setDisplayTimeZone("America/Indiana/Indianapolis")
    expect(dayEndUtc("2026-10-31").toISOString()).toBe("2026-11-01T03:59:59.999Z")
  })

  it("is 25 hours long on the day the clocks go back", () => {
    setDisplayTimeZone("America/Indiana/Indianapolis")
    const start = dayStartUtc("2026-11-01")
    const end = dayEndUtc("2026-11-01")
    expect(start.toISOString()).toBe("2026-11-01T04:00:00.000Z")
    expect(end.toISOString()).toBe("2026-11-02T04:59:59.999Z")
  })
})
