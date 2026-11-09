import { afterEach, describe, expect, it, vi } from "vitest"
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

describe("direct Supabase writes run as the admin, so a view refuses them", () => {
  afterEach(() => clearViewAs())

  it("profile, mail and password writes are refused; the zone report writes nothing", async () => {
    const { usersService } = await import("@/services/users")
    const { supabase } = await import("@/lib/supabase")
    const from = vi.spyOn(supabase, "from")
    setViewAs({ id: "v1", expires_at: new Date(Date.now() + 60_000).toISOString(), person })
    await expect(usersService.updateProfile({ full_name: "x" })).rejects.toBeInstanceOf(ViewAsReadOnlyError)
    await expect(usersService.setEmailKind("announcements" as never, false)).rejects.toBeInstanceOf(ViewAsReadOnlyError)
    await expect(usersService.reportDetectedTimeZone("Europe/Kyiv")).resolves.toBeNull()
    expect(from).not.toHaveBeenCalled()
  })
})
