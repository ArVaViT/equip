/**
 * Reading a course's shape, once, for every screen.
 *
 * The course arrives in two halves — the lessons inside modules and the
 * lessons inside nothing — and until now each screen joined them by hand.
 * The joins disagreed: one showed the loose lessons, another did not; "the
 * next lesson" walked a module at a time and stopped at its edge. These
 * tests pin the join and the reading order for all of them.
 */

import { describe, expect, it } from "vitest"
import {
  chapterEditHref,
  chapterHref,
  countChapters,
  countModules,
  findChapter,
  readCourseStructure,
  UNGROUPED_GROUP_ID,
} from "@/lib/courseStructure"
import type { Chapter, Course, Module } from "@/types"

function chapter(id: string, over: Partial<Chapter> = {}): Chapter {
  return {
    id,
    course_id: "c-1",
    module_id: null,
    title: id,
    order_index: 0,
    chapter_type: "reading",
    requires_completion: false,
    is_locked: false,
    ...over,
  }
}

function module(id: string, over: Partial<Module> = {}): Module {
  return {
    id,
    course_id: "c-1",
    title: id,
    description: null,
    order_index: 0,
    due_date: null,
    ...over,
  }
}

function course(over: Partial<Course> = {}): Course {
  return {
    id: "c-1",
    title: "Послание к Римлянам",
    description: null,
    image_url: null,
    status: "published",
    access_mode: "public",
    created_by: "u-1",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    ...over,
  }
}

const ids = (chapters: Chapter[]): string[] => chapters.map((c) => c.id)

describe("readCourseStructure", () => {
  it("reads a course built entirely of modules", () => {
    const structure = readCourseStructure(
      course({
        modules: [
          module("m-2", {
            order_index: 1,
            chapters: [
              chapter("b2", { module_id: "m-2", order_index: 1 }),
              chapter("b1", { module_id: "m-2", order_index: 0 }),
            ],
          }),
          module("m-1", {
            order_index: 0,
            chapters: [chapter("a1", { module_id: "m-1", order_index: 0 })],
          }),
        ],
        chapters: [],
      }),
    )

    expect(structure.groups.map((g) => g.moduleId)).toEqual(["m-1", "m-2"])
    expect(structure.groups.map((g) => ids(g.chapters))).toEqual([["a1"], ["b1", "b2"]])
    // Modules by their order, lessons by theirs — and the flat order runs
    // straight through the module boundary rather than stopping at it.
    expect(ids(structure.chapters)).toEqual(["a1", "b1", "b2"])
  })

  it("reads a course of four lessons and no modules at all", () => {
    // The shape the first teacher wanted and had to invent a module for.
    const structure = readCourseStructure(
      course({
        modules: [],
        chapters: [
          chapter("l3", { order_index: 2 }),
          chapter("l1", { order_index: 0 }),
          chapter("l2", { order_index: 1 }),
        ],
      }),
    )

    expect(ids(structure.chapters)).toEqual(["l1", "l2", "l3"])
    expect(structure.groups).toHaveLength(1)
    expect(structure.groups[0]!.moduleId).toBeNull()
    expect(structure.groups[0]!.module).toBeNull()
    expect(ids(structure.groups[0]!.chapters)).toEqual(["l1", "l2", "l3"])
  })

  it("puts the ungrouped lessons in one group after the last module", () => {
    const structure = readCourseStructure(
      course({
        modules: [
          module("m-1", {
            order_index: 0,
            chapters: [chapter("a1", { module_id: "m-1", order_index: 0 })],
          }),
          module("m-2", {
            order_index: 1,
            chapters: [chapter("b1", { module_id: "m-2", order_index: 0 })],
          }),
        ],
        // Deliberately low order indexes: the tail is a rule about grouping,
        // not a consequence of the numbers.
        chapters: [chapter("loose2", { order_index: 1 }), chapter("loose1", { order_index: 0 })],
      }),
    )

    expect(structure.groups.map((g) => g.moduleId)).toEqual(["m-1", "m-2", null])
    expect(ids(structure.chapters)).toEqual(["a1", "b1", "loose1", "loose2"])
  })

  it("keeps an empty module in the outline and out of the reading order", () => {
    // An empty module is a thing a teacher can see and fill. Hiding it makes
    // the module they just created look like it failed to save.
    const structure = readCourseStructure(
      course({
        modules: [module("m-1", { order_index: 0, chapters: [] })],
        chapters: [chapter("l1")],
      }),
    )

    expect(structure.groups.map((g) => g.moduleId)).toEqual(["m-1", null])
    expect(structure.groups[0]!.chapters).toEqual([])
    expect(ids(structure.chapters)).toEqual(["l1"])
  })

  it("grows no nameless heading when every lesson is in a module", () => {
    const structure = readCourseStructure(
      course({
        modules: [module("m-1", { chapters: [chapter("a1", { module_id: "m-1" })] })],
        chapters: [],
      }),
    )

    expect(structure.groups.map((g) => g.moduleId)).toEqual(["m-1"])
  })

  it("leaves a deleted lesson out of the outline and out of the reading order", () => {
    const structure = readCourseStructure(
      course({
        modules: [
          module("m-1", {
            chapters: [
              chapter("a1", { module_id: "m-1", order_index: 0 }),
              chapter("gone", { module_id: "m-1", order_index: 1, deleted_at: "2026-09-01T00:00:00Z" }),
            ],
          }),
        ],
        chapters: [chapter("gone-loose", { deleted_at: "2026-09-01T00:00:00Z" }), chapter("l1")],
      }),
    )

    expect(ids(structure.chapters)).toEqual(["a1", "l1"])
    expect(ids(structure.groups[0]!.chapters)).toEqual(["a1"])
    expect(ids(structure.groups[1]!.chapters)).toEqual(["l1"])
  })

  it("leaves a deleted module and everything under it out", () => {
    const structure = readCourseStructure(
      course({
        modules: [
          module("m-1", {
            order_index: 0,
            deleted_at: "2026-09-01T00:00:00Z",
            chapters: [chapter("orphan", { module_id: "m-1" })],
          }),
          module("m-2", { order_index: 1, chapters: [chapter("b1", { module_id: "m-2" })] }),
        ],
      }),
    )

    expect(structure.groups.map((g) => g.moduleId)).toEqual(["m-2"])
    expect(ids(structure.chapters)).toEqual(["b1"])
  })

  it("counts a lesson once even if a payload lists it in both halves", () => {
    // The server partitions the two halves. A cached payload from before it
    // did would otherwise show the lesson twice and make "next" walk into
    // itself.
    const both = chapter("a1", { module_id: "m-1" })
    const structure = readCourseStructure(
      course({
        modules: [module("m-1", { chapters: [both] })],
        chapters: [both],
      }),
    )

    expect(ids(structure.chapters)).toEqual(["a1"])
    expect(structure.groups.map((g) => g.moduleId)).toEqual(["m-1"])
  })

  it("reads a course that carries neither half as empty", () => {
    // A catalog row, or a screen still loading.
    expect(readCourseStructure(course())).toEqual({ groups: [], chapters: [] })
    expect(readCourseStructure(null)).toEqual({ groups: [], chapters: [] })
    expect(readCourseStructure(undefined)).toEqual({ groups: [], chapters: [] })
  })
})

describe("findChapter", () => {
  const structure = readCourseStructure(
    course({
      modules: [
        module("m-1", {
          order_index: 0,
          chapters: [
            chapter("a1", { module_id: "m-1", order_index: 0 }),
            chapter("a2", { module_id: "m-1", order_index: 1 }),
          ],
        }),
        module("m-2", {
          order_index: 1,
          chapters: [chapter("b1", { module_id: "m-2", order_index: 0 })],
        }),
      ],
      chapters: [chapter("loose", { order_index: 9 })],
    }),
  )

  it("steps out of a module into the next one instead of into a dead end", () => {
    const last = findChapter(structure, "a2")
    expect(last?.next?.id).toBe("b1")
    expect(last?.prev?.id).toBe("a1")
  })

  it("steps from the last module into the ungrouped tail", () => {
    expect(findChapter(structure, "b1")?.next?.id).toBe("loose")
  })

  it("names the group a lesson sits in, module or not", () => {
    expect(findChapter(structure, "a1")?.group.moduleId).toBe("m-1")
    expect(findChapter(structure, "loose")?.group.moduleId).toBeNull()
  })

  it("has nothing after the last lesson and nothing before the first", () => {
    expect(findChapter(structure, "loose")?.next).toBeNull()
    expect(findChapter(structure, "a1")?.prev).toBeNull()
    expect(findChapter(structure, "a1")?.index).toBe(0)
  })

  it("answers null for a lesson the course does not hold", () => {
    // A bookmark to a deleted lesson, which a screen must be able to tell
    // from "still loading".
    expect(findChapter(structure, "no-such")).toBeNull()
    expect(findChapter(structure, null)).toBeNull()
  })
})

describe("counts", () => {
  it("prefers the server's count, which is right where no lesson was fetched", () => {
    // A catalog card: modules summarized, not a chapter row in sight.
    expect(countChapters(course({ chapter_count: 12, modules: [] }))).toBe(12)
    expect(countModules(course({ module_count: 3, modules: [] }))).toBe(3)
  })

  it("falls back to the walk when the payload was not counted", () => {
    const uncounted = course({
      modules: [module("m-1", { chapters: [chapter("a1", { module_id: "m-1" })] })],
      chapters: [chapter("l1")],
    })

    expect(countChapters(uncounted)).toBe(2)
    expect(countModules(uncounted)).toBe(1)
  })
})

describe("addresses", () => {
  it("names a lesson by its course, not by the module of the day", () => {
    expect(chapterHref("c-1", "ch-1")).toBe("/courses/c-1/chapters/ch-1")
    expect(chapterEditHref("c-1", "ch-1")).toBe("/teacher/courses/c-1/chapters/ch-1/edit")
  })
})

describe("UNGROUPED_GROUP_ID", () => {
  it("is the id the reports give the group of loose lessons", () => {
    // Mirrors the backend constant; the reports group by a non-null key and
    // this is the one they mint. Changing it breaks the gradebook silently,
    // so it is pinned here.
    expect(UNGROUPED_GROUP_ID).toBe("__ungrouped__")
  })
})
