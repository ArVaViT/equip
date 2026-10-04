import { beforeEach, describe, expect, it } from "vitest"
import { RETURN_PATH_TTL_MS, peekReturnPath, rememberReturnPath, returnPathFrom, takeReturnPath } from "@/lib/authRedirect"

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

/**
 * The path across a full page load — and across the tab the confirmation
 * mail opens, which has none of the first tab's session storage.
 */
describe("returnPathFrom — the backslash form", () => {
  it("refuses «/\\host», which a URL parser reads as «//host»", () => {
    expect(returnPathFrom({ from: "/\\evil.com" })).toBeNull()
    expect(returnPathFrom({ from: "/courses\\x" })).toBeNull()
    expect(returnPathFrom({ from: "/courses/c-1/chapters/ch-2?x=1" })).toBe("/courses/c-1/chapters/ch-2?x=1")
  })
})

describe("rememberReturnPath / takeReturnPath", () => {
  const LESSON = "/courses/c1/chapters/ch2"
  const T0 = 1_700_000_000_000

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it("comes back in the same tab, once", () => {
    rememberReturnPath({ from: LESSON }, T0)
    expect(takeReturnPath(T0 + 1000)).toBe(LESSON)
    expect(takeReturnPath(T0 + 2000)).toBeNull()
  })

  it("comes back in a fresh tab — the one the confirmation mail opened", () => {
    rememberReturnPath({ from: LESSON }, T0)
    // A new tab shares localStorage and nothing else.
    sessionStorage.clear()
    expect(takeReturnPath(T0 + 10 * 60 * 1000)).toBe(LESSON)
  })

  it("but not after an hour", () => {
    rememberReturnPath({ from: LESSON }, T0)
    sessionStorage.clear()
    expect(takeReturnPath(T0 + RETURN_PATH_TTL_MS)).toBeNull()
    // And the stale copy is gone, not merely ignored.
    expect(localStorage.getItem("equip:returnTo")).toBeNull()
  })

  it("prefers the tab's own path to the browser-wide one, and clears both", () => {
    rememberReturnPath({ from: "/courses/old" }, T0)
    sessionStorage.clear()
    rememberReturnPath({ from: LESSON }, T0)
    // Another tab remembered something else since.
    localStorage.setItem("equip:returnTo", JSON.stringify({ path: "/courses/other", until: T0 + RETURN_PATH_TTL_MS }))
    expect(takeReturnPath(T0 + 1000)).toBe(LESSON)
    expect(localStorage.getItem("equip:returnTo")).toBeNull()
    expect(takeReturnPath(T0 + 2000)).toBeNull()
  })

  it("remembers nothing that would leave the site, and trusts nothing it finds in storage", () => {
    rememberReturnPath({ from: "https://evil.example/" }, T0)
    expect(sessionStorage.getItem("equip:returnTo")).toBeNull()
    expect(localStorage.getItem("equip:returnTo")).toBeNull()

    // Storage is writable by anything on the origin: a planted value is
    // validated on the way out exactly as router state is.
    localStorage.setItem("equip:returnTo", JSON.stringify({ path: "//evil.example/", until: T0 + 1000 }))
    expect(takeReturnPath(T0)).toBeNull()
    localStorage.setItem("equip:returnTo", "not json at all")
    expect(takeReturnPath(T0)).toBeNull()
    expect(localStorage.getItem("equip:returnTo")).toBeNull()
  })

  it("can be looked at without being spent — a render may run twice", () => {
    rememberReturnPath({ from: "/courses/c-1/chapters/ch-2" })
    expect(peekReturnPath()).toBe("/courses/c-1/chapters/ch-2")
    expect(peekReturnPath()).toBe("/courses/c-1/chapters/ch-2")
    expect(takeReturnPath()).toBe("/courses/c-1/chapters/ch-2")
    expect(peekReturnPath()).toBeNull()
  })
})
