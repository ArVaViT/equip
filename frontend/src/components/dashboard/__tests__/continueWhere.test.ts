import { describe, expect, it } from "vitest"

import type { Course, Enrollment } from "@/types"
import { courseToContinue, nextLesson } from "../continueWhere"

const course = (id: string, chapters: string[]): Course =>
  ({
    id,
    title: id,
    modules: [],
    chapters: chapters.map((c, i) => ({ id: c, course_id: id, module_id: null, title: c, order_index: i })),
  }) as unknown as Course

const enrollment = (id: string, over: Partial<Enrollment> = {}): Enrollment =>
  ({
    id: `e-${id}`,
    user_id: "u",
    course_id: id,
    cohort_id: null,
    enrolled_at: "2026-09-01T00:00:00Z",
    progress: 0,
    chapters_read: 0,
    chapters_to_read: 3,
    course: course(id, []),
    ...over,
  }) as Enrollment

describe("continue where you left off", () => {
  it("offers the course opened last, if it is not finished", () => {
    const list = [enrollment("a"), enrollment("b"), enrollment("c", { progress: 100, chapters_read: 3 })]
    expect(courseToContinue(list, ["c", "b", "a"])?.course_id).toBe("b")
  })

  it("falls back to the most recently joined unfinished course", () => {
    const list = [enrollment("a", { enrolled_at: "2026-08-01T00:00:00Z" }), enrollment("b", { enrolled_at: "2026-09-10T00:00:00Z" })]
    expect(courseToContinue(list, [])?.course_id).toBe("b")
  })

  it("prefers a course already started to one joined later but untouched", () => {
    const list = [
      enrollment("started", { enrolled_at: "2026-08-01T00:00:00Z", chapters_read: 2 }),
      enrollment("untouched", { enrolled_at: "2026-09-10T00:00:00Z" }),
    ]
    expect(courseToContinue(list, [])?.course_id).toBe("started")
    // What the reader opened last still wins.
    expect(courseToContinue(list, ["untouched"])?.course_id).toBe("untouched")
  })

  it("counts reading, not only assessed work, as progress", () => {
    // 0% assessed, but two of three lessons read: still unfinished.
    expect(courseToContinue([enrollment("a", { progress: 0, chapters_read: 2 })], [])?.course_id).toBe("a")
    // 100% assessed and everything read: nothing to continue.
    expect(courseToContinue([enrollment("a", { progress: 100, chapters_read: 3 })], [])).toBeNull()
  })

  it("points at the first lesson in reading order not yet done", () => {
    const next = nextLesson(course("a", ["l1", "l2", "l3"]), ["l1"])
    expect(next?.chapter.id).toBe("l2")
    expect([next?.position, next?.total]).toEqual([2, 3])
    expect(nextLesson(course("a", ["l1"]), ["l1"])).toBeNull()
  })

  it("does not send anyone to a locked lesson", () => {
    const c = course("a", ["quiz", "after", "free"])
    const chapters = (c as unknown as { chapters: Array<Record<string, unknown>> }).chapters
    chapters[0]!.chapter_type = "quiz"
    chapters[1]!.is_locked = true // opens once the quiz before it is passed
    // The quiz is taken but not yet passed: "after" is locked, so the card
    // offers the quiz itself — the first undone lesson that is open.
    expect(nextLesson(c, [])?.chapter.id).toBe("quiz")
    // Quiz passed: the lock opens.
    expect(nextLesson(c, ["quiz"])?.chapter.id).toBe("after")
    // A teacher's lock on the only lesson left: nowhere to send them.
    const only = course("b", ["x"])
    ;(only as unknown as { chapters: Array<Record<string, unknown>> }).chapters[0]!.is_locked = true
    expect(nextLesson(only, [])).toBeNull()
  })
})
