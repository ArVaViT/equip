import { afterEach, describe, expect, it } from "vitest"
import { activeViewAs, clearViewAs, refuseWhileViewingAs, setViewAs, ViewAsReadOnlyError } from "../viewAs"

const person = { id: "p1", email: "dima@example.com", full_name: "Dima", role: "director" }

describe("viewAs", () => {
  afterEach(() => clearViewAs())

  it("is off by default and lets writes through", () => {
    expect(activeViewAs()).toBeNull()
    expect(() => refuseWhileViewingAs()).not.toThrow()
  })

  it("refuses writes while a view is on", () => {
    setViewAs({ id: "v1", expires_at: new Date(Date.now() + 60_000).toISOString(), person })
    expect(activeViewAs()?.person.email).toBe("dima@example.com")
    expect(() => refuseWhileViewingAs()).toThrow(ViewAsReadOnlyError)
  })

  it("drops a view that has run out", () => {
    setViewAs({ id: "v1", expires_at: new Date(Date.now() - 1).toISOString(), person })
    expect(activeViewAs()).toBeNull()
    expect(() => refuseWhileViewingAs()).not.toThrow()
  })
})
