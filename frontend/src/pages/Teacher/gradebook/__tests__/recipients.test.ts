/**
 * Who the Monday note goes to. Nobody excused is chased, nobody whose test
 * is still waiting for its open answers is told they failed, and the
 * addresses go in Bcc so nobody sees anybody else's.
 */
import { describe, expect, it } from "vitest"

import { mailtoFor, pickRecipients } from "../recipients"
import type { ChapterInfo, StudentProgressData } from "../types"

const work = (over: Partial<ChapterInfo>): ChapterInfo => ({
  id: "q1",
  title: "Quiz",
  module_id: "m1",
  chapter_type: "quiz",
  completed: false,
  completed_by: null,
  quiz_result: null,
  assignment_result: null,
  ...over,
})

const student = (name: string, chapter: Partial<ChapterInfo>, email = `${name}@example.com`): StudentProgressData => ({
  id: name,
  full_name: name,
  email,
  progress: 0,
  chapters_completed: 0,
  total_chapters: 1,
  chapters: [work(chapter)],
})

const CLASS = [
  student("nothing", {}),
  student("excused", { completed_by: "excused" }),
  student("failed", { quiz_result: { score: 2, max_score: 10, passed: false } }),
  student("waiting", { quiz_result: { score: 2, max_score: 10, passed: false, awaiting_grading: true } }),
  student("passed", { quiz_result: { score: 9, max_score: 10, passed: true } }),
  student("returned", { id: "q1", chapter_type: "assignment", assignment_result: { status: "returned", grade: null } }),
  student("noemail", {}, ""),
]

const names = (r: StudentProgressData[]) => r.map((s) => s.full_name)

describe("pickRecipients", () => {
  it("not handed in: nothing there, and not excused", () => {
    expect(names(pickRecipients(CLASS, "q1", "not_submitted"))).toEqual(["nothing"])
  })

  it("not passed: a failed test or work returned, never one still being marked", () => {
    expect(names(pickRecipients(CLASS, "q1", "not_passed"))).toEqual(["failed", "returned"])
  })

  it("everyone with an address", () => {
    expect(pickRecipients(CLASS, null, "everyone")).toHaveLength(6)
  })
})

describe("mailtoFor", () => {
  it("puts the class in Bcc and encodes the subject", () => {
    expect(mailtoFor(["a+b@example.com", "c@example.com"], "Деяния: Тест 1")).toBe(
      "mailto:?bcc=a%2Bb@example.com,c@example.com&subject=%D0%94%D0%B5%D1%8F%D0%BD%D0%B8%D1%8F%3A%20%D0%A2%D0%B5%D1%81%D1%82%201",
    )
  })
})
