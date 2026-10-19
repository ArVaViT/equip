import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      refreshSession: vi.fn(),
      signOut: vi.fn(),
      onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
    },
  },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import { coursesService } from "@/services/courses"
import type { CourseEvent } from "@/types"
import { useEventsSection } from "../useEventsSection"

const lesson = (id: string): CourseEvent => ({
  id, course_id: "c1", title: "Урок", description: null, event_type: "live_session",
  event_date: "2099-10-24T00:00:00Z", meeting_url: null, recording_url: null, duration_minutes: 90,
  series_id: null, created_by: "t", created_at: "2026-10-01T00:00:00Z",
})

/**
 * What «close without saving?» is asked about. A blank form — or one the
 * calendar prefilled — has nothing to lose; a typed one does; an event
 * opened for editing and left as it was has nothing to lose either.
 */
describe("useEventsSection — dirty", () => {
  const confirm = vi.fn(async () => true)
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(coursesService, "getCourseEventsForEdit").mockResolvedValue([lesson("a")])
  })

  it("is clean on a blank form, even one the calendar prefilled", async () => {
    // One object across renders, as the calendar's `useMemo` hands it over.
    const prefilled = { event_type: "live_session", duration_minutes: "90" }
    const { result } = renderHook(() => useEventsSection("c1", confirm, prefilled))
    await waitFor(() => expect(result.current.events).toHaveLength(1))
    expect(result.current.dirty).toBe(false)
  })

  it("is dirty once something is typed, and clean again after the form is reset", async () => {
    const { result } = renderHook(() => useEventsSection("c1", confirm))
    act(() => result.current.setForm({ ...result.current.form, title: "Разбор Деяний" }))
    expect(result.current.dirty).toBe(true)
    act(() => result.current.resetForm())
    expect(result.current.dirty).toBe(false)
  })

  it("is clean on an edit opened and left as it was, dirty once a field changes", async () => {
    const { result } = renderHook(() => useEventsSection("c1", confirm))
    await waitFor(() => expect(result.current.events).toHaveLength(1))
    act(() => result.current.startEdit(result.current.events[0]!))
    expect(result.current.dirty).toBe(false)
    act(() => result.current.setForm({ ...result.current.form, meeting_url: "https://zoom.us/j/1" }))
    expect(result.current.dirty).toBe(true)
  })
})
