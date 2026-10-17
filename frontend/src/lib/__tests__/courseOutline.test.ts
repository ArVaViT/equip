/**
 * The teacher's editor arranges a course as one list of places — a module
 * with its lessons, or a lesson outside modules — and the order it sets is
 * the order everybody reads (2026-10-16). These pin the moves the editor
 * makes and that the numbers written read back as the arrangement.
 */
import { describe, expect, it } from "vitest"

import {
  applyOutline,
  fileLesson,
  moveInModule,
  movePlace,
  outlinePayload,
  outlinePlaces,
  readCourseStructure,
} from "@/lib/courseStructure"
import type { Chapter, Course, Module } from "@/types"

const ch = (id: string, order: number, moduleId: string | null = null): Chapter =>
  ({ id, course_id: "c", module_id: moduleId, title: id, order_index: order, chapter_type: "reading" }) as Chapter

const mod = (id: string, order: number, chapters: Chapter[] = []): Module =>
  ({ id, course_id: "c", title: id, description: null, order_index: order, due_date: null, chapters }) as Module

// First (a1, a2) · loose · Second (b1)
const COURSE = {
  id: "c",
  modules: [mod("first", 0, [ch("a1", 1, "first"), ch("a2", 2, "first")]), mod("second", 4, [ch("b1", 5, "second")])],
  chapters: [ch("loose", 3)],
} as unknown as Course

/** The course as it reads: `[module]` then its lessons, loose lessons bare. */
function reads(course: Course): string[] {
  return readCourseStructure(course).groups.flatMap((g) =>
    g.module ? [`[${g.module.id}]`, ...g.chapters.map((c) => c.id)] : g.chapters.map((c) => c.id),
  )
}

const places = () => outlinePlaces(readCourseStructure(COURSE))

describe("the course outline", () => {
  it("lists a loose lesson as its own place, where it stands", () => {
    expect(places().map((p) => (p.kind === "module" ? p.module.id : p.chapter.id))).toEqual([
      "first",
      "loose",
      "second",
    ])
  })

  it("moves a module with its lessons and leaves the loose lesson where it is", () => {
    const after = applyOutline(COURSE, movePlace(places(), 2, 0))
    expect(reads(after)).toEqual(["[second]", "b1", "[first]", "a1", "a2", "loose"])
  })

  it("drags a loose lesson above a module", () => {
    expect(reads(applyOutline(COURSE, movePlace(places(), 1, 0)))).toEqual([
      "loose",
      "[first]",
      "a1",
      "a2",
      "[second]",
      "b1",
    ])
  })

  it("reorders inside a module without moving anything outside it", () => {
    expect(reads(applyOutline(COURSE, moveInModule(places(), "first", 1, 0)))).toEqual([
      "[first]",
      "a2",
      "a1",
      "loose",
      "[second]",
      "b1",
    ])
  })

  it("takes a lesson out of a module and keeps it right after that module", () => {
    expect(reads(applyOutline(COURSE, fileLesson(places(), "a1", null)))).toEqual([
      "[first]",
      "a2",
      "a1",
      "loose",
      "[second]",
      "b1",
    ])
  })

  it("files a loose lesson at the end of a module", () => {
    const after = applyOutline(COURSE, fileLesson(places(), "loose", "second"))
    expect(reads(after)).toEqual(["[first]", "a1", "a2", "[second]", "b1", "loose"])
    expect(after.modules?.[1]?.chapters?.map((c) => c.module_id)).toEqual(["second", "second"])
  })

  it("leaves the outline alone for a move that goes nowhere", () => {
    const before = places()
    expect(fileLesson(before, "loose", null)).toBe(before)
    expect(fileLesson(before, "a1", "first")).toBe(before)
    expect(movePlace(before, 5, 0)).toBe(before)
  })

  it("numbers the course with one counter, as the server does", () => {
    const after = applyOutline(COURSE, places())
    expect(after.modules?.map((m) => [m.id, m.order_index])).toEqual([
      ["first", 0],
      ["second", 4],
    ])
    expect(after.modules?.[0]?.chapters?.map((c) => c.order_index)).toEqual([1, 2])
    expect(after.chapters?.map((c) => [c.id, c.order_index])).toEqual([["loose", 3]])
  })

  it("sends the server every module and lesson, in reading order", () => {
    expect(outlinePayload(places())).toEqual([
      { module_id: "first", chapter_ids: ["a1", "a2"] },
      { module_id: null, chapter_ids: ["loose"] },
      { module_id: "second", chapter_ids: ["b1"] },
    ])
  })
})
