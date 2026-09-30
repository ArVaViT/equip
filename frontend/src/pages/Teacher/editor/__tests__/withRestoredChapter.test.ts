import { describe, expect, it } from "vitest"

import { withRestoredChapter } from "../useCourseChapters"
import type { Chapter, Course } from "@/types"

const ch = (id: string, order: number, module_id: string | null = null) =>
  ({ id, title: id, order_index: order, module_id, chapter_type: "reading" }) as unknown as Chapter

describe("withRestoredChapter", () => {
  it("puts the lesson back into the course as it is now, not as it was", () => {
    // Renamed during the eight seconds the "Undo" was on screen.
    const course = { id: "c", chapters: [ch("a", 0), ch("c", 2)], modules: [] } as unknown as Course
    course.chapters![0]!.title = "renamed"
    const next = withRestoredChapter(course, ch("b", 1))
    expect(next.chapters!.map((c) => c.id)).toEqual(["a", "b", "c"])
    expect(next.chapters![0]!.title).toBe("renamed")
  })

  it("puts it back into its module when the module is on the page", () => {
    const course = {
      id: "c",
      chapters: [],
      modules: [{ id: "m", chapters: [ch("x", 5, "m")] }],
    } as unknown as Course
    const next = withRestoredChapter(course, ch("y", 3, "m"))
    expect(next.modules![0]!.chapters!.map((c) => c.id)).toEqual(["y", "x"])
    expect(next.chapters).toEqual([])
  })

  it("puts it among the loose lessons when its module is gone", () => {
    const course = { id: "c", chapters: [], modules: [] } as unknown as Course
    const next = withRestoredChapter(course, ch("y", 3, "gone"))
    expect(next.chapters!.map((c) => [c.id, c.module_id])).toEqual([["y", null]])
  })
})
