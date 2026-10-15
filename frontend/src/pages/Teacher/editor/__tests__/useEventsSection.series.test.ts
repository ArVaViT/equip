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
import { EMPTY_EVENT_FORM } from "../types"
import { useEventsSection } from "../useEventsSection"

const lesson = (id: string, date: string): CourseEvent => ({
  id, course_id: "c1", title: "Урок", description: null, event_type: "live_session",
  event_date: date, meeting_url: null, recording_url: null, duration_minutes: 90,
  series_id: "s1", created_by: "t", created_at: "2026-10-01T00:00:00Z",
})

describe("useEventsSection — a series", () => {
  const confirm = vi.fn(async () => true)
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it("does not send a repeat for a deadline whose hidden repeat controls still hold one", async () => {
    vi.spyOn(coursesService, "getCourseEventsForEdit").mockResolvedValue([])
    const create = vi.spyOn(coursesService, "createCourseEvent").mockResolvedValue(lesson("n", "2099-10-24T00:00:00Z"))
    const { result } = renderHook(() => useEventsSection("c1", confirm))
    act(() =>
      result.current.setForm({
        ...EMPTY_EVENT_FORM,
        title: "Эссе",
        event_type: "deadline",
        event_date: "2099-10-24T20:00",
        repeat_every: "1",
        repeat_count: "8",
      }),
    )
    await act(() => result.current.save())
    expect(create).toHaveBeenCalledTimes(1)
    expect(create.mock.calls[0]?.[1]).not.toHaveProperty("repeat")
    expect(create.mock.calls[0]?.[1]?.duration_minutes).toBeNull()
  })

  it("closes the form when the lesson open in it was deleted with the rest of the series", async () => {
    const a = lesson("a", "2099-10-24T00:00:00Z")
    const b = lesson("b", "2099-10-31T00:00:00Z")
    const list = vi.spyOn(coursesService, "getCourseEventsForEdit").mockResolvedValueOnce([a, b])
    vi.spyOn(coursesService, "deleteCourseEvent").mockResolvedValue(undefined)
    const { result } = renderHook(() => useEventsSection("c1", confirm))
    await waitFor(() => expect(result.current.events).toHaveLength(2))
    act(() => result.current.startEdit(b))
    expect(result.current.editingId).toBe("b")
    await act(() => result.current.remove("a"))
    expect(result.current.pendingScope).toEqual({ action: "delete", eventId: "a" })
    list.mockResolvedValueOnce([])
    await act(async () => result.current.chooseScope("all"))
    await waitFor(() => expect(result.current.editingId).toBeNull())
  })
})
