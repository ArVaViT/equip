import { describe, expect, it } from "vitest"

import {
  addMonths,
  buildMonthMatrix,
  parseYmd,
  startOfMonth,
  weekdayMonStart,
  ymdKey,
} from "../calendar"

describe("ymdKey", () => {
  it("formats local Y-M-D with zero padding (no UTC drift)", () => {
    expect(ymdKey(new Date(2026, 0, 5))).toBe("2026-01-05") // month is 0-indexed
    expect(ymdKey(new Date(2026, 11, 31))).toBe("2026-12-31")
  })

  it("uses local date parts even just after midnight", () => {
    expect(ymdKey(new Date(2026, 2, 1, 0, 30))).toBe("2026-03-01")
  })
})

describe("parseYmd", () => {
  it("parses a strict YYYY-MM-DD into local Y/M/D", () => {
    const d = parseYmd("2026-02-28")
    expect(d).not.toBeNull()
    expect([d!.getFullYear(), d!.getMonth(), d!.getDate()]).toEqual([2026, 1, 28])
  })

  it("round-trips with ymdKey", () => {
    expect(ymdKey(parseYmd("2026-07-04")!)).toBe("2026-07-04")
  })

  it("rejects malformed input", () => {
    for (const bad of ["", "2026-2-4", "2026/02/04", "26-02-04", "garbage", "2026-02-4"]) {
      expect(parseYmd(bad)).toBeNull()
    }
  })
})

describe("weekdayMonStart", () => {
  it("maps Monday to 0 and Sunday to 6", () => {
    expect(weekdayMonStart(new Date(2024, 0, 1))).toBe(0) // 2024-01-01 was a Monday
    expect(weekdayMonStart(new Date(2024, 0, 7))).toBe(6) // the following Sunday
  })
})

describe("startOfMonth", () => {
  it("collapses to day 1 of the same month", () => {
    expect(ymdKey(startOfMonth(new Date(2026, 5, 23)))).toBe("2026-06-01")
  })
})

describe("addMonths", () => {
  it("moves to the first of the target month without day overflow", () => {
    expect(ymdKey(addMonths(new Date(2026, 0, 31), 1))).toBe("2026-02-01") // Jan 31 + 1m, no Mar bleed
    expect(ymdKey(addMonths(new Date(2026, 0, 15), -1))).toBe("2025-12-01") // crosses year backwards
    expect(ymdKey(addMonths(new Date(2026, 11, 10), 1))).toBe("2027-01-01") // crosses year forwards
  })
})

describe("buildMonthMatrix", () => {
  const grid = buildMonthMatrix(new Date(2026, 1, 15)) // February 2026

  it("returns exactly 42 cells (6 weeks)", () => {
    expect(grid).toHaveLength(42)
  })

  it("starts on a Monday and runs as consecutive days", () => {
    expect(weekdayMonStart(grid[0]!)).toBe(0)
    for (let i = 1; i < grid.length; i++) {
      const deltaDays = Math.round((grid[i]!.getTime() - grid[i - 1]!.getTime()) / 86_400_000)
      expect(deltaDays).toBe(1) // round() absorbs 23h/25h DST transitions
    }
  })

  it("contains every day of the anchor month", () => {
    const keys = new Set(grid.map(ymdKey))
    for (let day = 1; day <= 28; day++) {
      expect(keys.has(`2026-02-${String(day).padStart(2, "0")}`)).toBe(true)
    }
  })

  it("includes leading/trailing days from adjacent months", () => {
    const months = new Set(grid.map((d) => d.getMonth()))
    expect(months.size).toBeGreaterThan(1)
  })

  it("places the 1st of the anchor month at its Mon-start offset", () => {
    const first = new Date(2026, 2, 1) // 1 March 2026
    const march = buildMonthMatrix(first)
    expect(march).toHaveLength(42)
    expect(weekdayMonStart(march[0]!)).toBe(0)
    expect(ymdKey(march[weekdayMonStart(first)]!)).toBe("2026-03-01")
  })
})
