import { beforeEach, describe, expect, it } from "vitest"

import { rememberReturnPath, takeReturnPath } from "../authRedirect"

/**
 * Google sign-in and an emailed link come back through /auth/callback in a
 * fresh page, where router state is gone; the course a visitor was heading
 * for was lost there (2026-09-30 review).
 */
describe("the way back survives a full page load", () => {
  beforeEach(() => sessionStorage.clear())

  it("is kept, and handed back once", () => {
    rememberReturnPath({ from: "/courses/c-1?ref=pastor" })
    expect(takeReturnPath()).toBe("/courses/c-1?ref=pastor")
    expect(takeReturnPath()).toBeNull()
  })

  it("never keeps a way off the site", () => {
    rememberReturnPath({ from: "//evil.example/x" })
    rememberReturnPath({ from: "https://evil.example/x" })
    expect(takeReturnPath()).toBeNull()
  })
})
