import type { ReactNode } from "react"
import { renderHook, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"

let courseCount: { count: number | null; error: { message: string } | null }

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
    getAllUsers: () => Promise.resolve([]),
    getAdminPendingCerts: () => Promise.resolve([]),
  },
}))

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
