import { describe, expect, it } from "vitest"

import { groupNotes } from "../groupNotes"

const note = (course: string, module: string | null, chapter: string) => ({
  chapter_id: chapter,
  chapter_title: chapter,
  module_id: module,
  module_title: module,
  course_id: course,
  course_title: course,
  body: "b",
  updated_at: "2026-10-01T10:00:00Z",
  available: true,
})

describe("groupNotes", () => {
  it("groups by course, then module, keeping the server's order", () => {
    const groups = groupNotes([note("Acts", "m1", "c1"), note("Acts", "m1", "c2"), note("Acts", null, "c3"), note("Romans", "m9", "c9")])
    expect(groups.map((g) => [g.courseId, g.modules.map((m) => [m.moduleId, m.notes.map((n) => n.chapter_id)])])).toEqual([
      ["Acts", [["m1", ["c1", "c2"]], [null, ["c3"]]]],
      ["Romans", [["m9", ["c9"]]]],
    ])
  })
})
