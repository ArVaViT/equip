import { describe, expect, it } from "vitest"
import { officialGrade } from "../officialGrade"
import type { StudentProgressEntry } from "@/types"

function student(over: Partial<StudentProgressEntry> = {}): StudentProgressEntry {
  return {
    id: "s1",
    full_name: "Student",
    email: "s@example.com",
    enrolled_at: null,
    progress: 50,
    chapters_completed: 2,
    total_chapters: 4,
    quiz_avg: 80,
    assignment_avg: 70,
    overall_grade: 74,
    manual_grade: null,
    result_state: "graded",
    letter_grade: "C",
    last_activity: null,
    ...over,
  }
}

describe("officialGrade", () => {
  it("shows the weighted percentage with the symbol", () => {
    expect(officialGrade(student())).toEqual({ text: "74.0% (C)", isManual: false, noteKey: null })
  })

  it("prints the same text the Grade Table prints for the same score", () => {
    // The two screens used to round separately — Python to even, JavaScript
    // up — so 86.5 was 86% on one and 87% on the other.
    expect(officialGrade(student({ overall_grade: 86.5, letter_grade: "B" })).text).toBe("86.5% (B)")
  })

  it("shows a hand-set grade rather than the computed one", () => {
    // Two screens telling a student two different things is the exact failure
    // D14 exists to end. The override decides everything official, so it shows.
    const g = officialGrade(student({ manual_grade: "A", overall_grade: 41, letter_grade: "F" }))

    expect(g.text).toBe("A")
    expect(g.isManual).toBe(true)
  })

  it.each([
    ["not_graded_yet", "studentProgress.grade.notGradedYet"],
    ["completion_pass", "studentProgress.grade.byCompletion"],
    ["zero_weighted", "studentProgress.grade.notWeighted"],
    ["not_assessed", "studentProgress.grade.notAssessed"],
  ])("explains an absent number for %s", (state, note) => {
    const g = officialGrade(
      student({ overall_grade: null, result_state: state as StudentProgressEntry["result_state"] }),
    )

    expect(g.text).toBeNull()
    expect(g.noteKey).toBe(note)
  })

  it("drops the parenthesis on a scheme with no symbol", () => {
    expect(officialGrade(student({ letter_grade: null })).text).toBe("74.0%")
  })
})
