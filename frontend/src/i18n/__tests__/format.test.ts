import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "../config"
import {
  formatDate,
  formatDateLong,
  formatDateTime,
  formatDateTimeMs,
  isoToLocalInput,
  localInputToIso,
} from "../format"

/**
 * Regression suite for ``isoToLocalInput`` / ``localInputToIso``.
 *
 * The contract: the backend stores datetimes as **UTC** ISO strings,
 * the browser ``<input type="datetime-local">`` widget reads/writes
 * in the **local** timezone, and the round-trip helpers must preserve
 * the instant in time across read → display → save.
 *
 * Pre-fix, callsites used ``iso.slice(0, 16)`` to feed the input,
 * which silently displayed the UTC wall-clock as local — every
 * round-trip drifted by the local UTC offset.
 */
describe("isoToLocalInput / localInputToIso", () => {
  it("renders a UTC ISO in the browser's local timezone", () => {
    // Pick an instant and confirm the rendered string matches what
    // ``new Date(...)`` would compute for the local zone. We don't
    // hardcode the offset because the test runs in whatever tz the
    // CI machine is in — what matters is the helper agrees with
    // the JS Date API the browser uses.
    const iso = "2026-06-01T00:00:00.000Z"
    const expected = (() => {
      const d = new Date(iso)
      const pad = (n: number) => n.toString().padStart(2, "0")
      return (
        `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
        `T${pad(d.getHours())}:${pad(d.getMinutes())}`
      )
    })()
    expect(isoToLocalInput(iso)).toBe(expected)
  })

  it("returns '' for null/undefined/empty input", () => {
    expect(isoToLocalInput(null)).toBe("")
    expect(isoToLocalInput(undefined)).toBe("")
    expect(isoToLocalInput("")).toBe("")
  })

  it("returns '' for an unparseable ISO string", () => {
    expect(isoToLocalInput("not-a-date")).toBe("")
  })

  it("round-trips: ISO → local input → ISO preserves the instant", () => {
    const original = "2026-06-01T15:30:00.000Z"
    const local = isoToLocalInput(original)
    const back = localInputToIso(local)
    expect(back).not.toBeNull()
    // datetime-local truncates to minutes, so compare at that granularity.
    expect(new Date(back!).getTime()).toBe(new Date(original).getTime())
  })

  it("localInputToIso returns null for empty input", () => {
    expect(localInputToIso("")).toBeNull()
  })

  it("localInputToIso returns null for unparseable input", () => {
    expect(localInputToIso("garbage")).toBeNull()
  })

  it("localInputToIso treats input as local time (not UTC)", () => {
    // Whatever the local timezone, a local-time string should produce
    // an ISO whose getHours() matches the input — this is the
    // characteristic that makes the round-trip work.
    const local = "2026-06-01T09:15"
    const iso = localInputToIso(local)
    expect(iso).not.toBeNull()
    const d = new Date(iso!)
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(5)
    expect(d.getDate()).toBe(1)
    expect(d.getHours()).toBe(9)
    expect(d.getMinutes()).toBe(15)
  })
})

/**
 * Coverage for the canonical ISO-style formatters: ``formatDate``,
 * ``formatDateTime``, ``formatDateTimeMs``. These are the table-cell
 * timestamps the user sees in audit logs, last-activity columns,
 * "joined on", "created at", "submitted at" etc.
 *
 * The contract per ``format.ts``:
 *   * ``YYYY-MM-DD`` / ``YYYY-MM-DD HH:mm:ss`` / ``YYYY-MM-DD HH:mm:ss.SSS``
 *   * always in the browser's *local* timezone (we don't hard-code an
 *     offset; tests assert characters via local Date components so they
 *     pass under any CI tz)
 *   * identical across locales — EN and RU users see the same characters
 *   * ``null`` / ``undefined`` / empty / unparseable input → ``""``
 *
 * Padding is the most regression-prone part — every component (month,
 * day, hour, minute, second, ms) has its own ``pad`` call, easy to
 * forget one. We pick a date with single-digit components so a missing
 * pad call would surface as ``2026-1-2 3:4:5`` vs the contract.
 */
describe("formatDate / formatDateTime / formatDateTimeMs", () => {
  describe("formatDate", () => {
    it("returns YYYY-MM-DD with zero-padded month and day", () => {
      // 2026-Jan-05, a single-digit month + day in local time
      const d = new Date(2026, 0, 5, 12, 0, 0, 0)
      expect(formatDate(d)).toBe("2026-01-05")
    })

    it("pads every two-digit position consistently", () => {
      const d = new Date(2026, 8, 9, 0, 0, 0, 0)
      expect(formatDate(d)).toBe("2026-09-09")
    })

    it("accepts an ISO string", () => {
      // The exact day depends on the runner's tz, but the value must
      // match what new Date(iso) produces.
      const iso = "2026-06-01T12:00:00.000Z"
      const d = new Date(iso)
      const expected =
        `${d.getFullYear()}-` +
        `${(d.getMonth() + 1).toString().padStart(2, "0")}-` +
        `${d.getDate().toString().padStart(2, "0")}`
      expect(formatDate(iso)).toBe(expected)
    })

    it("accepts a numeric epoch milliseconds value", () => {
      const ms = Date.UTC(2026, 0, 1, 12, 0, 0, 0)
      const d = new Date(ms)
      const expected =
        `${d.getFullYear()}-` +
        `${(d.getMonth() + 1).toString().padStart(2, "0")}-` +
        `${d.getDate().toString().padStart(2, "0")}`
      expect(formatDate(ms)).toBe(expected)
    })

    it("returns '' for null / undefined / empty string / unparseable", () => {
      expect(formatDate(null)).toBe("")
      expect(formatDate(undefined)).toBe("")
      expect(formatDate("")).toBe("")
      expect(formatDate("not-a-date")).toBe("")
    })
  })

  describe("formatDateTime", () => {
    it("returns YYYY-MM-DD HH:mm:ss with every component zero-padded", () => {
      const d = new Date(2026, 0, 2, 3, 4, 5, 0)
      expect(formatDateTime(d)).toBe("2026-01-02 03:04:05")
    })

    it("handles end-of-day boundary correctly", () => {
      const d = new Date(2026, 11, 31, 23, 59, 59, 0)
      expect(formatDateTime(d)).toBe("2026-12-31 23:59:59")
    })

    it("returns '' for null / undefined / unparseable", () => {
      expect(formatDateTime(null)).toBe("")
      expect(formatDateTime(undefined)).toBe("")
      expect(formatDateTime("nope")).toBe("")
    })

    it("agrees with the browser's local-tz Date components for ISO input", () => {
      const iso = "2026-06-01T15:30:45.000Z"
      const d = new Date(iso)
      const pad = (n: number) => n.toString().padStart(2, "0")
      const expected =
        `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
        `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
      expect(formatDateTime(iso)).toBe(expected)
    })
  })

  describe("formatDateTimeMs", () => {
    it("returns YYYY-MM-DD HH:mm:ss.SSS with millisecond zero-padded to 3", () => {
      const d = new Date(2026, 0, 2, 3, 4, 5, 7) // 7 ms → ".007"
      expect(formatDateTimeMs(d)).toBe("2026-01-02 03:04:05.007")
    })

    it("zero-pads single-digit and double-digit millisecond values", () => {
      expect(formatDateTimeMs(new Date(2026, 0, 1, 0, 0, 0, 9))).toBe("2026-01-01 00:00:00.009")
      expect(formatDateTimeMs(new Date(2026, 0, 1, 0, 0, 0, 99))).toBe("2026-01-01 00:00:00.099")
      expect(formatDateTimeMs(new Date(2026, 0, 1, 0, 0, 0, 999))).toBe("2026-01-01 00:00:00.999")
    })

    it("returns '' for null / undefined / unparseable", () => {
      expect(formatDateTimeMs(null)).toBe("")
      expect(formatDateTimeMs(undefined)).toBe("")
      expect(formatDateTimeMs("garbage")).toBe("")
    })
  })

  describe("locale-independence of canonical formatters", () => {
    // The whole point of the canonical YYYY-MM-DD form is that EN and
    // RU users see the same string. Without this guarantee, audit logs
    // and table cells would shift between dot- and dash-separators
    // across locales — exactly the bug the canonical form prevents.
    let savedLanguage: string

    beforeEach(() => {
      savedLanguage = i18n.language
    })

    afterEach(async () => {
      await i18n.changeLanguage(savedLanguage)
    })

    it("formatDate output is identical under EN and RU", async () => {
      const d = new Date(2026, 4, 14, 9, 30, 0, 0)
      await i18n.changeLanguage("en")
      const enOut = formatDate(d)
      await i18n.changeLanguage("ru")
      const ruOut = formatDate(d)
      expect(enOut).toBe(ruOut)
      expect(enOut).toBe("2026-05-14")
    })

    it("formatDateTime output is identical under EN and RU", async () => {
      const d = new Date(2026, 4, 14, 9, 30, 0, 0)
      await i18n.changeLanguage("en")
      const enOut = formatDateTime(d)
      await i18n.changeLanguage("ru")
      const ruOut = formatDateTime(d)
      expect(enOut).toBe(ruOut)
      expect(enOut).toBe("2026-05-14 09:30:00")
    })

    it("formatDateTimeMs output is identical under EN and RU", async () => {
      const d = new Date(2026, 4, 14, 9, 30, 0, 250)
      await i18n.changeLanguage("en")
      const enOut = formatDateTimeMs(d)
      await i18n.changeLanguage("ru")
      const ruOut = formatDateTimeMs(d)
      expect(enOut).toBe(ruOut)
      expect(enOut).toBe("2026-05-14 09:30:00.250")
    })
  })

  describe("system-time isolation via fake timers", () => {
    // ``formatDate`` etc. don't read ``Date.now()``, but they do new
    // Date(value) for numeric / string inputs. Use vi.setSystemTime to
    // confirm the helpers ignore the system clock when given an
    // explicit value — the bug we'd be guarding against is someone
    // accidentally calling ``new Date()`` instead of ``new Date(value)``.
    beforeEach(() => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2000, 0, 1, 0, 0, 0, 0))
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it("formatDate of an explicit Date ignores the system clock", () => {
      const d = new Date(2026, 5, 20, 0, 0, 0, 0)
      expect(formatDate(d)).toBe("2026-06-20")
      // System clock is January 2000; formatDate(new Date()) would emit
      // "2000-01-01". Demonstrate the difference.
      expect(formatDate(new Date())).toBe("2000-01-01")
    })

    it("formatDateTime of explicit ISO ignores the system clock", () => {
      const d = new Date(2030, 10, 15, 4, 5, 6, 0)
      expect(formatDateTime(d)).toBe("2030-11-15 04:05:06")
    })
  })
})

/**
 * Coverage for ``formatDateLong`` — the editorial / ceremonial form.
 *
 * Unlike the canonical formatters, EN and RU intentionally produce
 * *different* strings here. We assert that:
 *   1. EN and RU produce different outputs for the same date.
 *   2. Default options yield the "year + month-name + day" shape.
 *   3. The ``options`` parameter merges with the defaults (allowing
 *      callers to add hour/minute/weekday on the same call).
 *   4. ``null`` / ``undefined`` / unparseable → ``""``.
 *   5. The function reads ``i18n.resolvedLanguage`` *at call time*, so
 *      a render after ``changeLanguage`` picks up the new locale.
 *
 * We assert against substrings the locale spec is stable on (year
 * digits, English month name, Russian abbreviation "г.") rather than
 * exact strings — ICU output varies subtly between Node versions and
 * the test would otherwise flake on a Node upgrade.
 */
describe("formatDateLong", () => {
  let savedLanguage: string

  beforeEach(() => {
    savedLanguage = i18n.language
  })

  afterEach(async () => {
    await i18n.changeLanguage(savedLanguage)
  })

  it("uses English long form under EN locale", async () => {
    await i18n.changeLanguage("en")
    const out = formatDateLong(new Date(2026, 4, 14))
    expect(out).toMatch(/2026/)
    // Different ICU builds emit "May 14, 2026" / "May 14, 2026" — both
    // contain the English month name. RU output contains the Cyrillic
    // form "мая".
    expect(out).toMatch(/May/i)
    expect(out).not.toMatch(/мая/)
  })

  it("uses Russian long form under RU locale", async () => {
    await i18n.changeLanguage("ru")
    const out = formatDateLong(new Date(2026, 4, 14))
    expect(out).toMatch(/2026/)
    expect(out).toMatch(/мая/) // "May" in Russian, lowercase by ICU spec
  })

  it("produces different strings under EN vs RU for the same date", async () => {
    const d = new Date(2026, 4, 14)
    await i18n.changeLanguage("en")
    const enOut = formatDateLong(d)
    await i18n.changeLanguage("ru")
    const ruOut = formatDateLong(d)
    expect(enOut).not.toBe(ruOut)
  })

  it("re-reads the locale on each call (no stale capture)", async () => {
    const d = new Date(2026, 4, 14)
    await i18n.changeLanguage("en")
    const first = formatDateLong(d)
    await i18n.changeLanguage("ru")
    const second = formatDateLong(d)
    expect(first).not.toBe(second)
  })

  it("merges custom options with the default year/month/day shape", async () => {
    await i18n.changeLanguage("en")
    // Adding hour + minute should produce a string containing both the
    // date AND a time component (": " is universal separator in ICU
    // long form). We don't assert exact format; just that the time
    // option was honored.
    const withTime = formatDateLong(new Date(2026, 4, 14, 9, 30), {
      hour: "numeric",
      minute: "2-digit",
    })
    expect(withTime).toMatch(/2026/)
    // 09:30 / 9:30 AM / etc — ICU varies but the minute digits are stable
    expect(withTime).toMatch(/30/)
  })

  it("returns '' for null / undefined / empty / unparseable", () => {
    expect(formatDateLong(null)).toBe("")
    expect(formatDateLong(undefined)).toBe("")
    expect(formatDateLong("not-a-date")).toBe("")
  })

  it("accepts a numeric epoch value (parallel to the other formatters)", async () => {
    await i18n.changeLanguage("en")
    const ms = new Date(2026, 4, 14).getTime()
    expect(formatDateLong(ms)).toMatch(/2026/)
  })
})
