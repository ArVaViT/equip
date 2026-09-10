import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

// ``services/api`` (reached through ``services/courses``) builds the
// supabase client at module load from ``VITE_SUPABASE_*``. Mock it before
// any other import so the test never depends on the real env vars.
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

vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import { createElement, type ReactNode } from "react"
import { MemoryRouter } from "react-router-dom"

import i18n from "@/i18n/config"
import { toast } from "@/lib/toast"
import { coursesService } from "@/services/courses"
import { useCourseData } from "@/pages/Teacher/editor/useCourseData"
import type { Course } from "@/types"

/**
 * The first publish of a course nobody has translated yet lands it in
 * ``publishing`` on the server: it is out, but the catalog waits until
 * every language has it. The editor used to ignore that answer and write
 * ``published`` locally from what it had *asked for*, so the badge said
 * PUBLISHED until a reload said DRAFT — and a teacher read that as lost
 * work. The hook must take the server's word for the resulting status.
 */

function makeCourse(over: Partial<Course> = {}): Course {
  return {
    id: "c-1",
    title: "Послание к Римлянам",
    description: null,
    image_url: null,
    status: "draft",
    access_mode: "public",
    created_by: "teacher-1",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    modules: [],
    ...over,
  }
}

const confirm = vi.fn().mockResolvedValue(true) as unknown as Parameters<typeof useCourseData>[1]

// The hook navigates now — adding a lesson opens it — so it needs a router
// around it the way the editor page gives it one.
function withRouter({ children }: { children: ReactNode }) {
  return createElement(MemoryRouter, null, children)
}

async function renderLoaded(course: Course) {
  vi.spyOn(coursesService, "getCourseForEdit").mockResolvedValue(course)
  const { result } = renderHook(() => useCourseData(course.id, confirm), {
    wrapper: withRouter,
  })
  await waitFor(() => expect(result.current.loading).toBe(false))
  return result
}

describe("useCourseData.togglePublish", () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    vi.mocked(toast).mockClear()
    await i18n.changeLanguage("ru")
  })

  it("reports 'publishing' when that is what the server answered", async () => {
    const draft = makeCourse()
    const update = vi
      .spyOn(coursesService, "updateCourse")
      .mockResolvedValue({ ...draft, status: "publishing" })
    const result = await renderLoaded(draft)

    await act(() => result.current.togglePublish())

    expect(update).toHaveBeenCalledWith("c-1", { status: "published" })
    expect(result.current.course?.status).toBe("publishing")
    expect(result.current.publishing).toBe(true)
    expect(result.current.published).toBe(false)

    // The toast tells the truth about what happens next, not "Published".
    const { title } = vi.mocked(toast).mock.calls[0]![0]
    expect(title).toMatch(/(?<!\p{L})готов на всех языках(?!\p{L})/u)
  })

  it("reports 'published' when the server said so", async () => {
    const draft = makeCourse()
    vi.spyOn(coursesService, "updateCourse").mockResolvedValue({
      ...draft,
      status: "published",
    })
    const result = await renderLoaded(draft)

    await act(() => result.current.togglePublish())

    expect(result.current.published).toBe(true)
    expect(result.current.publishing).toBe(false)
    const { title } = vi.mocked(toast).mock.calls[0]![0]
    expect(title).toBe("Опубликовано")
  })

  /**
   * Publishing takes a second or two on production and the button said
   * nothing while it did. On 2026-09-08 a teacher pressed it twice: the
   * audit log holds two `publish` events on the same course four seconds
   * apart, the second one already `old_status: publishing`.
   */
  it("ignores a second press while the first is still in the air", async () => {
    const draft = makeCourse()
    let release: ((c: Course) => void) | undefined
    const update = vi
      .spyOn(coursesService, "updateCourse")
      .mockImplementation(
        () => new Promise<Course>((resolve) => { release = resolve }),
      )
    const result = await renderLoaded(draft)

    let first: Promise<void> | undefined
    act(() => { first = result.current.togglePublish() })
    expect(result.current.publishPending).toBe(true)

    // The second press, while the first request is still unanswered.
    await act(() => result.current.togglePublish())
    expect(update).toHaveBeenCalledTimes(1)

    await act(async () => {
      release?.({ ...draft, status: "publishing" })
      await first
    })
    expect(result.current.publishPending).toBe(false)
    expect(update).toHaveBeenCalledTimes(1)
  })

  it("lets the next press through once the first has answered", async () => {
    const draft = makeCourse()
    const update = vi
      .spyOn(coursesService, "updateCourse")
      .mockResolvedValue({ ...draft, status: "published" })
    const result = await renderLoaded(draft)

    await act(() => result.current.togglePublish())
    await act(() => result.current.togglePublish())

    expect(update).toHaveBeenCalledTimes(2)
    expect(update).toHaveBeenNthCalledWith(2, "c-1", { status: "draft" })
  })

  it("takes a course that is still publishing back to draft, not to published again", async () => {
    const publishing = makeCourse({ status: "publishing" })
    const update = vi
      .spyOn(coursesService, "updateCourse")
      .mockResolvedValue({ ...publishing, status: "draft" })
    const result = await renderLoaded(publishing)

    await act(() => result.current.togglePublish())

    // The teacher already published it; the only sensible toggle from
    // here is to take it back.
    expect(update).toHaveBeenCalledWith("c-1", { status: "draft" })
    expect(result.current.course?.status).toBe("draft")
    expect(result.current.publishing).toBe(false)
  })
})
