/**
 * A reorder is one request per lesson whose number moved. When some land and
 * some fail, the old order put back on screen is an order the server no
 * longer has — so the editor re-reads the course instead (2026-10-03).
 */
import type { ReactNode } from "react"
import { act, renderHook } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import type { DropResult } from "@hello-pangea/dnd"

import { coursesService } from "@/services/courses"
import type { Chapter, Course } from "@/types"
import { useCourseChapters } from "../useCourseChapters"

const ch = (id: string, order: number) =>
  ({ id, title: id, order_index: order, module_id: null, chapter_type: "reading" }) as unknown as Chapter

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>
}

describe("reordering lessons", () => {
  it("re-reads the course when only some of the moves landed", async () => {
    const course = { id: "k1", chapters: [ch("a", 0), ch("b", 1), ch("c", 2)], modules: [] } as unknown as Course
    vi.spyOn(coursesService, "updateCourseChapter")
      .mockResolvedValueOnce(ch("c", 0))
      .mockRejectedValue(new Error("offline"))
    const reload = vi.fn()
    const setCourse = vi.fn()
    const { result } = renderHook(() => useCourseChapters({ courseId: "k1", course, setCourse, reload }), { wrapper })

    await act(() =>
      result.current.reorderChapters({
        source: { index: 2, droppableId: "chapters" },
        destination: { index: 0, droppableId: "chapters" },
      } as DropResult),
    )

    expect(reload).toHaveBeenCalledTimes(1)
  })
})
