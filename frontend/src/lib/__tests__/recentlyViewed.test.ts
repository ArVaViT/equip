import { describe, it, expect, beforeEach } from "vitest"
import { getRecentCourses, recordCourseView } from "../recentlyViewed"

describe("recentlyViewed", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("returns an empty list when nothing has been viewed", () => {
    expect(getRecentCourses()).toEqual([])
  })

  it("records a course view and reads it back", () => {
    recordCourseView("course-a")
    const recent = getRecentCourses()
    expect(recent).toHaveLength(1)
    const first = recent[0]!
    expect(first.id).toBe("course-a")
    expect(typeof first.ts).toBe("number")
  })

  it("orders most-recently-viewed first", () => {
    recordCourseView("course-a")
    recordCourseView("course-b")
    recordCourseView("course-c")
    expect(getRecentCourses().map((r) => r.id)).toEqual(["course-c", "course-b", "course-a"])
  })

  it("de-duplicates and moves a re-viewed course to the front", () => {
    recordCourseView("course-a")
    recordCourseView("course-b")
    recordCourseView("course-a")
    const ids = getRecentCourses().map((r) => r.id)
    expect(ids).toEqual(["course-a", "course-b"])
    expect(ids).toHaveLength(2)
  })

  it("caps the list at 5 entries", () => {
    for (let i = 0; i < 8; i++) {
      recordCourseView(`course-${i}`)
    }
    const recent = getRecentCourses()
    expect(recent).toHaveLength(5)
    // The five most recent (3..7), newest first.
    expect(recent.map((r) => r.id)).toEqual([
      "course-7",
      "course-6",
      "course-5",
      "course-4",
      "course-3",
    ])
  })

  it("ignores empty ids", () => {
    recordCourseView("")
    expect(getRecentCourses()).toEqual([])
  })

  it("tolerates corrupt storage and returns an empty list", () => {
    window.localStorage.setItem("equip.recently-viewed.courses", "not-json{")
    expect(getRecentCourses()).toEqual([])
  })

  it("drops malformed entries when reading", () => {
    window.localStorage.setItem(
      "equip.recently-viewed.courses",
      JSON.stringify([{ id: "good", ts: 123 }, { id: 42 }, "garbage", { ts: 1 }]),
    )
    expect(getRecentCourses().map((r) => r.id)).toEqual(["good"])
  })
})
