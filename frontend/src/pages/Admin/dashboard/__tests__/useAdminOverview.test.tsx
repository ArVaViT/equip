import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"

let courseCount: { count: number | null; error: { message: string } | null }
let users: unknown[] = []
let bulkResult: { updated: number; role: string; held_by_membership: string[] }
const toastSpy = vi.fn()

vi.mock("@/lib/supabase", () => ({
  supabase: {
    from: (table: string) => ({
      select: () =>
        Promise.resolve(table === "courses" ? courseCount : { count: 7, error: null }),
    }),
  },
}))

vi.mock("@/services/courses", () => ({
  coursesService: {
    getAllUsers: () => Promise.resolve(users),
    getAdminPendingCerts: () => Promise.resolve([]),
    bulkUpdateUserRoles: () => Promise.resolve(bulkResult),
  },
}))

vi.mock("@/lib/toast", () => ({ toast: (...args: unknown[]) => toastSpy(...args) }))

// The confirm dialog needs a provider; here the question is always answered yes.
vi.mock("@/components/ui/alert-dialog", () => ({ useConfirm: () => () => Promise.resolve(true) }))

import { useAdminOverview } from "../useAdminOverview"

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

/**
 * The overview's counts come straight from Supabase. A failed count
 * answered `count: null` beside an error, and `?? 0` turned that into a
 * confident "0 courses" (2026-09-30 audit, F5).
 */
describe("admin overview counts", () => {
  beforeEach(() => {
    courseCount = { count: 5, error: null }
  })

  it("shows the counts it got", async () => {
    const { result } = renderHook(() => useAdminOverview({ currentUserId: "a" }), { wrapper: Wrapper })
    await waitFor(() => expect(result.current.stats.courses).toBe(5))
    expect(result.current.stats.enrollments).toBe(7)
    expect(result.current.error).toBeNull()
  })

  it("says the load failed instead of showing zero", async () => {
    courseCount = { count: null, error: { message: "permission denied" } }
    const { result } = renderHook(() => useAdminOverview({ currentUserId: "a" }), { wrapper: Wrapper })
    await waitFor(() => expect(result.current.error).not.toBeNull())
    expect(result.current.stats.courses).toBe(0)
  })
})

/**
 * The bulk role action asks the server for one thing — platform staff or
 * not — and the server leaves alone anyone whose role is held by an
 * organization membership, naming them in ``held_by_membership``. Until
 * 2026-10-03 the client painted the asked-for role over every selected
 * row regardless, and the toast counted them as updated.
 */
describe("the bulk role action", () => {
  const rows = [
    { id: "a", email: "a@x", full_name: "Me", role: "admin", created_at: "", avatar_url: null, deactivated_at: null },
    { id: "d", email: "d@x", full_name: "Director", role: "director", created_at: "", avatar_url: null, deactivated_at: null },
    { id: "s", email: "s@x", full_name: "Student", role: "student", created_at: "", avatar_url: null, deactivated_at: null },
  ]

  beforeEach(() => {
    courseCount = { count: 5, error: null }
    users = rows
    bulkResult = { updated: 1, role: "admin", held_by_membership: ["d"] }
    toastSpy.mockClear()
  })

  it("changes only the rows the server changed, and says who was left", async () => {
    const { result } = renderHook(() => useAdminOverview({ currentUserId: "a" }), { wrapper: Wrapper })
    await waitFor(() => expect(result.current.users).toHaveLength(3))

    act(() => {
      result.current.setBulkRole("admin")
      result.current.toggleSelect("d")
      result.current.toggleSelect("s")
    })
    await act(() => result.current.handleBulkRoleChange())

    const byId = Object.fromEntries(result.current.users.map((u) => [u.id, u.role]))
    expect(byId).toEqual({ a: "admin", d: "director", s: "admin" })
    expect(result.current.selectedIds.size).toBe(0)
    expect(toastSpy).toHaveBeenCalledTimes(1)
    expect(toastSpy.mock.calls[0]?.[0]).toEqual({
      title: "Updated 1 user(s)",
      description: "1 user left as is: their role is held in an organization",
      variant: "warning",
    })
  })

  it("says nothing about holding when nobody was held", async () => {
    bulkResult = { updated: 2, role: "admin", held_by_membership: [] }
    const { result } = renderHook(() => useAdminOverview({ currentUserId: "a" }), { wrapper: Wrapper })
    await waitFor(() => expect(result.current.users).toHaveLength(3))

    act(() => {
      result.current.toggleSelect("d")
      result.current.toggleSelect("s")
    })
    await act(() => result.current.handleBulkRoleChange())

    expect(toastSpy.mock.calls[0]?.[0]).toEqual({
      title: "Updated 2 user(s)",
      description: undefined,
      variant: "success",
    })
  })
})
