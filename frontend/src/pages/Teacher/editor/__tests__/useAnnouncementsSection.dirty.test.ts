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
import type { Announcement } from "@/types"
import { useAnnouncementsSection } from "../useAnnouncementsSection"

const posted: Announcement = {
  id: "a1",
  title: "Занятие переносится",
  content: "На четверг.",
  course_id: "c1",
  created_by: "t",
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
}

/**
 * What «close without saving?» is asked about. A blank form has nothing to
 * lose; a typed one does; an announcement opened for editing and left as it
 * was has nothing to lose either.
 */
describe("useAnnouncementsSection — dirty", () => {
  const confirm = vi.fn(async () => true)
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(coursesService, "getAnnouncementsForEdit").mockResolvedValue([posted])
  })

  it("is clean on a blank form and on whitespace alone", () => {
    const { result } = renderHook(() => useAnnouncementsSection("c1", confirm))
    expect(result.current.dirty).toBe(false)
    act(() => result.current.setContent("   "))
    expect(result.current.dirty).toBe(false)
  })

  it("is dirty once something is typed, and clean again after the form is reset", () => {
    const { result } = renderHook(() => useAnnouncementsSection("c1", confirm))
    act(() => result.current.setTitle("Экзамен"))
    expect(result.current.dirty).toBe(true)
    act(() => result.current.resetForm())
    expect(result.current.dirty).toBe(false)
  })

  it("is clean on an edit opened and left as it was, dirty once the text changes", async () => {
    const { result } = renderHook(() => useAnnouncementsSection("c1", confirm))
    await waitFor(() => expect(result.current.announcements).toHaveLength(1))
    act(() => result.current.startEdit(posted))
    expect(result.current.dirty).toBe(false)
    act(() => result.current.setContent("На пятницу."))
    expect(result.current.dirty).toBe(true)
  })
})
