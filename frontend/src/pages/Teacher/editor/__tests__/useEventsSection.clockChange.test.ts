import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

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

import { setDisplayTimeZone } from "@/i18n/timeZone"
import { coursesService } from "@/services/courses"
import type { CourseEvent } from "@/types"
import { useEventsSection } from "../useEventsSection"

const lesson = (id: string, date: string): CourseEvent => ({
  id, course_id: "c1", title: "Урок", description: null, event_type: "live_session",
  event_date: date, meeting_url: null, recording_url: null, duration_minutes: 60,
  series_id: null, created_by: "t", created_at: "2026-10-01T00:00:00Z",
})

describe("useEventsSection — the hour a clock change repeats", () => {
  const confirm = vi.fn(async () => true)
  beforeEach(() => {
    vi.restoreAllMocks()
    setDisplayTimeZone("America/Indiana/Indianapolis")
  })
  afterEach(() => setDisplayTimeZone(null))

  it("saving a new title leaves a class at the second 01:30 where it is", async () => {
    // 06:30Z on November 1 is 01:30 EST — the second 01:30 that night. The
    // form shows 01:30, which read back is the first one (05:30Z).
    const late = lesson("a", "2026-11-01T06:30:00Z")
    vi.spyOn(coursesService, "getCourseEventsForEdit").mockResolvedValue([late])
    const update = vi.spyOn(coursesService, "updateCourseEvent").mockResolvedValue({ ...late, title: "Урок 2" })
    const { result } = renderHook(() => useEventsSection("c1", confirm))
    await waitFor(() => expect(result.current.events).toHaveLength(1))
    act(() => result.current.startEdit(late))
    expect(result.current.form.event_date).toBe("2026-11-01T01:30")
    act(() => result.current.setForm({ ...result.current.form, title: "Урок 2" }))
    await act(() => result.current.save())
    expect(update.mock.calls[0]?.[2]?.event_date).toBe("2026-11-01T06:30:00Z")
  })

  it("a date the teacher did change is read from the field", async () => {
    const late = lesson("a", "2026-11-01T06:30:00Z")
    vi.spyOn(coursesService, "getCourseEventsForEdit").mockResolvedValue([late])
    const update = vi.spyOn(coursesService, "updateCourseEvent").mockResolvedValue(late)
    const { result } = renderHook(() => useEventsSection("c1", confirm))
    await waitFor(() => expect(result.current.events).toHaveLength(1))
    act(() => result.current.startEdit(late))
    act(() => result.current.setForm({ ...result.current.form, event_date: "2026-11-07T19:00" }))
    await act(() => result.current.save())
    expect(update.mock.calls[0]?.[2]?.event_date).toBe("2026-11-08T00:00:00.000Z")
  })
})
