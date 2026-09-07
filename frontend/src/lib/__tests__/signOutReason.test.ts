import { beforeEach, describe, expect, it } from "vitest"
import { rememberSignOutReason, takeSignOutReason } from "@/lib/signOutReason"

describe("the reason for an unasked-for sign-out", () => {
  beforeEach(() => {
    window.sessionStorage.clear()
  })

  it("is handed over exactly once", () => {
    rememberSignOutReason("session_expired")
    expect(takeSignOutReason()).toBe("session_expired")
    // Read, and therefore gone: a reload of the login page says it once.
    expect(takeSignOutReason()).toBeNull()
  })

  it("is nothing when nothing happened", () => {
    expect(takeSignOutReason()).toBeNull()
  })

  it("ignores a value it did not write", () => {
    window.sessionStorage.setItem("equip.auth.sign-out-reason", "<script>")
    expect(takeSignOutReason()).toBeNull()
  })
})
