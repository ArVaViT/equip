import { beforeEach, describe, expect, it, vi } from "vitest"
import { timeAgo } from "../notificationMeta"

/**
 * Regression suite for the notification bell's relative-time helper.
 *
 * Pre-fix the function hardcoded English strings (``just now`` /
 * ``5m ago`` / ``2d ago``) in a bilingual product, leaving the
 * Russian side broken. It now takes the translator from
 * ``useTranslation().t`` and renders keys under
 * ``notifications.timeAgo.*``.
 *
 * Tests use a fake translator so they don't have to wire up i18next.
 */
describe("timeAgo", () => {
  // Capture (key, count) calls so we can assert the right bucket
  // was reached and the right count was passed for pluralization.
  const fakeT = vi.fn(
    (key: string, options?: { count?: number }) =>
      options?.count !== undefined ? `${key}:${options.count}` : key,
  )

  beforeEach(() => {
    fakeT.mockClear()
  })

  it("'just now' for sub-minute diffs", () => {
    const recent = new Date(Date.now() - 30_000).toISOString()
    expect(timeAgo(recent, fakeT)).toBe("notifications.timeAgo.justNow")
  })

  it("minutesAgo with count for sub-hour diffs", () => {
    const fiveMin = new Date(Date.now() - 5 * 60_000).toISOString()
    expect(timeAgo(fiveMin, fakeT)).toBe("notifications.timeAgo.minutesAgo:5")
  })

  it("hoursAgo with count for sub-day diffs", () => {
    const threeHr = new Date(Date.now() - 3 * 60 * 60_000).toISOString()
    expect(timeAgo(threeHr, fakeT)).toBe("notifications.timeAgo.hoursAgo:3")
  })

  it("daysAgo with count for sub-week diffs", () => {
    const twoDay = new Date(Date.now() - 2 * 24 * 60 * 60_000).toISOString()
    expect(timeAgo(twoDay, fakeT)).toBe("notifications.timeAgo.daysAgo:2")
  })

  it("falls back to YYYY-MM-DD past 7 days", () => {
    const old = new Date("2026-01-15T10:00:00Z").toISOString()
    // 2026-01-15 in browser local — the helper uses formatDate which
    // is local-zone canonical, so we recompute the same way.
    const d = new Date(old)
    const expected =
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
    expect(timeAgo(old, fakeT)).toBe(expected)
  })

  it("returns em-dash for unparseable input", () => {
    expect(timeAgo("not-a-date", fakeT)).toBe("—")
  })
})
