import { createElement, type ReactNode } from "react"
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

import { MemoryRouter } from "react-router-dom"

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import { useCourseData } from "@/pages/Teacher/editor/useCourseData"
import type { Chapter, Course } from "@/types"

/**
 * Deleting a module deletes a heading, not the lessons under it.
 *
 * The server settled that (`delete_module` clears `module_id` and writes no
 * `deleted_at`), and this hook has to agree twice over: the sentence it
 * shows before the deletion, and the state it keeps after one. It used to
 * promise the chapters would go — and then drop the module from local state
 * and stop, which took four live lessons off the screen. The teacher who
 * prompted this whole change lost work to exactly that cascade.
 */

const GROUPED: Chapter[] = [
  { id: "ch-1", module_id: "m-1", title: "Кто написал послание", order_index: 0 } as Chapter,
  { id: "ch-2", module_id: "m-1", title: "Рим в первом веке", order_index: 1 } as Chapter,
]

function makeCourse(): Course {
  return {
    id: "c-1",
    title: "Послание к Римлянам",
    description: null,
    image_url: null,
    status: "draft",
    access_mode: "public",
    created_by: "teacher-1",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: null,
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    chapters: [],
    modules: [
      {
        id: "m-1",
        course_id: "c-1",
        title: "Часть первая",
        order_index: 0,
        chapters: GROUPED,
      },
    ],
  } as unknown as Course
}

function withRouter({ children }: { children: ReactNode }) {
  return createElement(MemoryRouter, null, children)
}

describe("useCourseData.removeModule", () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await i18n.changeLanguage("ru")
  })

  async function renderLoaded(confirm: ReturnType<typeof vi.fn>) {
    vi.spyOn(coursesService, "getCourseForEdit").mockResolvedValue(makeCourse())
    const { result } = renderHook(
      () => useCourseData("c-1", confirm as unknown as Parameters<typeof useCourseData>[1]),
      { wrapper: withRouter },
    )
    await waitFor(() => expect(result.current.loading).toBe(false))
    return result
  }

  it("keeps the lessons in the course, ungrouped, once the module is gone", async () => {
    const confirm = vi.fn().mockResolvedValue(true)
    const del = vi.spyOn(coursesService, "deleteModule").mockResolvedValue(undefined)
    const result = await renderLoaded(confirm)

    await act(() => result.current.removeModule("m-1"))

    expect(del).toHaveBeenCalledWith("c-1", "m-1")
    // The heading is gone…
    expect(result.current.structure.groups.map((g) => g.moduleId)).toEqual([null])
    // …and both lessons are still there, in the course, in reading order.
    expect(result.current.structure.chapters.map((c) => c.id)).toEqual(["ch-1", "ch-2"])
    expect(result.current.structure.chapters.every((c) => c.module_id === null)).toBe(true)
  })

  it("does not promise that the lessons go with it", async () => {
    const confirm = vi.fn().mockResolvedValue(false)
    const result = await renderLoaded(confirm)

    await act(() => result.current.removeModule("m-1"))

    const description = confirm.mock.calls[0]?.[0]?.description as string
    // The old sentence — «Все главы внутри модуля также будут удалены» —
    // is now false. The new one has to say what actually happens.
    expect(description).toMatch(/останутся в курсе/i)
    expect(description).not.toMatch(/(?<!\p{L})удал\p{L}*/iu)
  })
})
