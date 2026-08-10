import { describe, expect, it } from "vitest"
import { chapterActions } from "../chapterActions"
import type { StudentChapterInfo } from "@/types"

function chapter(overrides: Partial<StudentChapterInfo> = {}): StudentChapterInfo {
  return {
    id: "ch1",
    title: "Chapter 1",
    module_id: "m1",
    chapter_type: "assignment",
    requires_completion: true,
    completed: false,
    completed_by: null,
    quiz_result: null,
    assignment_result: null,
    gradable_item: { type: "assignment", id: "a1" },
    ...overrides,
  }
}

describe("chapterActions", () => {
  it("offers the ordinary pair on untouched work", () => {
    expect(chapterActions(chapter())).toEqual({
      canExcuse: true,
      canReturn: false,
      canToggleCompletion: true,
    })
  })

  it("replaces the completion toggle on an excused chapter, never sits beside it", () => {
    // Undoing the tick alone is refused by the server (409) because the
    // exemption holds the grade and the completion together. A visible button
    // whose only outcome is an error toast is worse than no button.
    const actions = chapterActions(chapter({ completed: true, completed_by: "excused" }))

    expect(actions.canReturn).toBe(true)
    expect(actions.canToggleCompletion).toBe(false)
    expect(actions.canExcuse).toBe(false)
  })

  it("still offers to excuse work the student already finished", () => {
    // Someone who submitted while ill can be waived from the mark; the
    // completion they earned stays exactly as it is.
    expect(chapterActions(chapter({ completed: true, completed_by: "self" })).canExcuse).toBe(true)
  })

  it("offers nothing to excuse when there is no work behind the chapter", () => {
    expect(chapterActions(chapter({ gradable_item: null })).canExcuse).toBe(false)
  })

  it("leaves reading chapters alone", () => {
    const actions = chapterActions(chapter({ chapter_type: "reading", gradable_item: null }))

    expect(actions).toEqual({ canExcuse: false, canReturn: false, canToggleCompletion: false })
  })

  it("offers nothing at all for a chapter that has not loaded", () => {
    expect(chapterActions(undefined)).toEqual({
      canExcuse: false,
      canReturn: false,
      canToggleCompletion: false,
    })
  })
})
