import { describe, expect, it } from "vitest"
import { isoToLocalInput, localInputToIso } from "../format"

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
