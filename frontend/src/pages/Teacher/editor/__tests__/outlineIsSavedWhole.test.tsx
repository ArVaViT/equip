/**
 * The editor saves the course order in one request — the whole outline —
 * and shows what the server will hold. It used to send one request per row
 * in two number spaces, and a module moved without its lessons renumbered
 * could leave a loose lesson on the wrong side of it (2026-10-16).
 */
import type { ReactNode } from "react"
import { act, renderHook } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { DropResult } from "@hello-pangea/dnd"

import { coursesService } from "@/services/courses"
import type { Chapter, Course, Module } from "@/types"
import { useCourseChapters } from "../useCourseChapters"

const ch = (id: string, order: number, moduleId: string | null = null) =>
  ({ id, title: id, order_index: order, module_id: moduleId, chapter_type: "reading" }) as unknown as Chapter
const mod = (id: string, order: number, chapters: Chapter[]) =>
  ({ id, title: id, order_index: order, chapters }) as unknown as Module

// First (a1) · loose · Second (b1)
const course = {
  id: "k1",
  modules: [mod("first", 0, [ch("a1", 1, "first")]), mod("second", 3, [ch("b1", 4, "second")])],
  chapters: [ch("loose", 2)],
} as unknown as Course

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>
}

const drag = (from: number, to: number) =>
  ({ source: { index: from, droppableId: "outline" }, destination: { index: to, droppableId: "outline" } }) as DropResult

function setup() {
  const reload = vi.fn()
  let state: Course | null = course
  const setCourse = vi.fn((next: Course | null | ((prev: Course | null) => Course | null)) => {
    state = typeof next === "function" ? next(state) : next
  })
  const { result } = renderHook(() => useCourseChapters({ courseId: "k1", course, setCourse, reload }), { wrapper })
  return { result, reload, current: () => state }
}

afterEach(() => vi.restoreAllMocks())

describe("saving the course order", () => {
  it("moves a module past the loose lesson in one request, and shows it", async () => {
    const save = vi.spyOn(coursesService, "saveOutline").mockResolvedValue()
    const perRow = vi.spyOn(coursesService, "updateCourseChapter")
    const { result, current } = setup()

    await act(() => result.current.reorderOutline(drag(2, 0)))

    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith("k1", [
      { module_id: "second", chapter_ids: ["b1"] },
      { module_id: "first", chapter_ids: ["a1"] },
      { module_id: null, chapter_ids: ["loose"] },
    ])
    expect(perRow).not.toHaveBeenCalled()
    expect(current()?.modules?.map((m) => [m.id, m.order_index])).toEqual([
      ["second", 0],
      ["first", 2],
    ])
    expect(current()?.chapters?.map((c) => [c.id, c.order_index])).toEqual([["loose", 4]])
  })

  it("takes a lesson out of a module to just after that module", async () => {
    const save = vi.spyOn(coursesService, "saveOutline").mockResolvedValue()
    const { result } = setup()

    await act(() => result.current.moveChapter("a1", null))

    expect(save).toHaveBeenCalledWith("k1", [
      { module_id: "first", chapter_ids: [] },
      { module_id: null, chapter_ids: ["a1"] },
      { module_id: null, chapter_ids: ["loose"] },
      { module_id: "second", chapter_ids: ["b1"] },
    ])
  })

  it("re-reads the course when the server refuses the order", async () => {
    vi.spyOn(coursesService, "saveOutline").mockRejectedValue(new Error("409"))
    const { result, reload } = setup()

    await act(() => result.current.reorderModuleChapters("first", drag(0, 0)))
    expect(reload).not.toHaveBeenCalled()

    await act(() => result.current.reorderOutline(drag(1, 0)))
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
