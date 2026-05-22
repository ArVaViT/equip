import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"

// ``services/api`` (transitively imported by ``services/courseReadiness``)
// reads ``VITE_SUPABASE_URL`` / ``VITE_SUPABASE_ANON_KEY`` at module load
// to spin up the supabase client. Mock the supabase module before any
// other import so this test never depends on the real env vars. The
// auth surface only needs to expose the calls api.ts attaches at boot.
vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      refreshSession: vi.fn(),
      signOut: vi.fn(),
      onAuthStateChange: vi
        .fn()
        .mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
    },
  },
}))

import { useCourseReadiness } from "@/pages/Teacher/editor/useCourseReadiness"
import { courseReadinessService } from "@/services/courseReadiness"

/**
 * The course editor renders the readiness card by piping
 * ``useCourseReadiness(courseId)`` straight into ``CourseReadinessCard``,
 * so the hook's three observable behaviours — initial fetch, refresh,
 * and silent-failure-on-error — are the entire contract the rest of
 * the editor relies on.
 */
describe("useCourseReadiness", () => {
  const report = {
    course_id: "c-1",
    total: 5,
    passing: 4,
    critical_failing: 0,
    score: 80,
    checks: [],
  }

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it("returns null/loading until the fetch resolves, then surfaces the report", async () => {
    const get = vi
      .spyOn(courseReadinessService, "get")
      .mockResolvedValue(report)

    const { result } = renderHook(() => useCourseReadiness("c-1"))

    expect(result.current.loading).toBe(true)
    expect(result.current.report).toBeNull()

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(get).toHaveBeenCalledWith("c-1")
    expect(result.current.report).toEqual(report)
  })

  it("does not fetch when courseId is undefined", async () => {
    const get = vi
      .spyOn(courseReadinessService, "get")
      .mockResolvedValue(report)

    const { result } = renderHook(() => useCourseReadiness(undefined))

    // Give the effect a tick to settle.
    await new Promise((r) => setTimeout(r, 0))

    expect(get).not.toHaveBeenCalled()
    // ``load`` early-returns without flipping ``loading`` back to false
    // — the editor only renders the card once a courseId is in hand.
    expect(result.current.loading).toBe(true)
    expect(result.current.report).toBeNull()
  })

  it("re-fetches when courseId changes", async () => {
    const get = vi
      .spyOn(courseReadinessService, "get")
      .mockImplementation(async (id: string) => ({ ...report, course_id: id }))

    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useCourseReadiness(id),
      { initialProps: { id: "c-1" } },
    )

    await waitFor(() => expect(result.current.report?.course_id).toBe("c-1"))
    expect(get).toHaveBeenCalledTimes(1)

    rerender({ id: "c-2" })

    await waitFor(() => expect(result.current.report?.course_id).toBe("c-2"))
    expect(get).toHaveBeenLastCalledWith("c-2")
  })

  it("silently swallows fetch errors and surfaces report=null", async () => {
    // Per the docstring: "the card hides itself when ``report === null``
    // — a transient backend blip shouldn't break the editor."
    vi.spyOn(courseReadinessService, "get").mockRejectedValue(new Error("backend down"))

    const { result } = renderHook(() => useCourseReadiness("c-1"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.report).toBeNull()
  })

  it("refresh() re-runs the fetch with the same id", async () => {
    let attempt = 0
    const get = vi
      .spyOn(courseReadinessService, "get")
      .mockImplementation(async () => {
        attempt += 1
        return { ...report, passing: attempt }
      })

    const { result } = renderHook(() => useCourseReadiness("c-1"))

    await waitFor(() => expect(result.current.report?.passing).toBe(1))

    await act(async () => {
      await result.current.refresh()
    })

    expect(get).toHaveBeenCalledTimes(2)
    expect(result.current.report?.passing).toBe(2)
  })

  it("refresh() after a previous error recovers and shows the new report", async () => {
    const get = vi.spyOn(courseReadinessService, "get")
    get.mockRejectedValueOnce(new Error("transient"))
    get.mockResolvedValueOnce(report)

    const { result } = renderHook(() => useCourseReadiness("c-1"))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.report).toBeNull()

    await act(async () => {
      await result.current.refresh()
    })

    expect(result.current.report).toEqual(report)
  })
})
