import { describe, expect, it } from "vitest"
import { returnPathFrom } from "@/lib/authRedirect"

/**
 * Where a sign-in sends the person afterwards.
 *
 * `Gate` writes the refused route into router state; the login gate reads
 * it back. Whatever is read back must be one of our own pages — a value
 * that could send a fresh sign-in off-site is worse than the dashboard.
 */
describe("returnPathFrom", () => {
  it("returns the internal path the gate recorded", () => {
    expect(returnPathFrom({ from: "/courses/abc?tab=modules" })).toBe("/courses/abc?tab=modules")
  })

  it("has nothing to say when there is no state or no path in it", () => {
    expect(returnPathFrom(null)).toBeNull()
    expect(returnPathFrom(undefined)).toBeNull()
    expect(returnPathFrom({})).toBeNull()
    expect(returnPathFrom({ from: 42 })).toBeNull()
    expect(returnPathFrom("/courses")).toBeNull()
  })

  it("refuses anything that would leave the site", () => {
    expect(returnPathFrom({ from: "https://evil.example/" })).toBeNull()
    expect(returnPathFrom({ from: "//evil.example/" })).toBeNull()
    expect(returnPathFrom({ from: "courses" })).toBeNull()
  })
})
