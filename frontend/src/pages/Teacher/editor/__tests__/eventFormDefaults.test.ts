import { act, renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

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
import { EMPTY_EVENT_FORM, withEventType } from "../types"
import { useEventsSection } from "../useEventsSection"

describe("the event form's defaults", () => {
  it("gives a live session the usual 90 minutes when no length was chosen, and keeps one that was", () => {
    expect(withEventType(EMPTY_EVENT_FORM, "live_session").duration_minutes).toBe("90")
    expect(withEventType({ ...EMPTY_EVENT_FORM, duration_minutes: "60" }, "live_session").duration_minutes).toBe("60")
    // A deadline has no length to default; whatever was there is left for the
    // save to drop (see useEventsSection).
    expect(withEventType(EMPTY_EVENT_FORM, "deadline").duration_minutes).toBe("")
    expect(withEventType(EMPTY_EVENT_FORM, "exam").event_type).toBe("exam")
  })

  it("starts, and restarts, the form from what the caller hands in", async () => {
    vi.spyOn(coursesService, "getCourseEventsForEdit").mockResolvedValue([])
    const confirm = vi.fn(async () => true)
    const defaults = { event_type: "live_session", duration_minutes: "75", meeting_url: "https://zoom.us/j/1" }
    const { result } = renderHook(() => useEventsSection("c1", confirm, defaults))
    expect(result.current.form).toEqual({ ...EMPTY_EVENT_FORM, ...defaults })
    act(() => result.current.setForm({ ...result.current.form, title: "Урок", duration_minutes: "60" }))
    act(() => result.current.resetForm())
    expect(result.current.form).toEqual({ ...EMPTY_EVENT_FORM, ...defaults })
  })

  it("keeps what the teacher typed when the defaults change under it", async () => {
    // Another course picked in the calendar's dialog, or the calendar
    // loading after the dialog opened: only untouched fields follow.
    vi.spyOn(coursesService, "getCourseEventsForEdit").mockResolvedValue([])
    const confirm = vi.fn(async () => true)
    const a = { event_type: "live_session", duration_minutes: "90", meeting_url: "https://zoom.us/j/1" }
    const b = { event_type: "live_session", duration_minutes: "60", meeting_url: "https://zoom.us/j/2" }
    const { result, rerender } = renderHook(({ d }) => useEventsSection("c1", confirm, d), { initialProps: { d: a } })
    act(() => result.current.setForm({ ...result.current.form, title: "Разбор проповеди", duration_minutes: "45" }))
    rerender({ d: b })
    expect(result.current.form.title).toBe("Разбор проповеди")
    expect(result.current.form.duration_minutes).toBe("45")
    expect(result.current.form.meeting_url).toBe("https://zoom.us/j/2")
  })
})
