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
    current_grade: 74,
    current_letter_grade: "C",
    scores_differ: false,
    manual_grade: null,
    result_state: "graded",
    letter_grade: "C",
    last_activity: null,
    ...over,
  }
}

describe("officialGrade", () => {
  it("shows one number when nothing is outstanding", () => {
    const g = officialGrade(student())

    expect(g.text).toBe("74.0% C")
    expect(g.finalText).toBeNull()
  })

  it("prints the same text the Grade Table prints for the same score", () => {
    // Both screens format through one function now — that is the whole of D14
    // reduced to a string comparison.
    expect(officialGrade(student({ current_grade: 86.5, current_letter_grade: "B" })).text).toBe(
      "86.5% B",
    )
  })

  it("shows both numbers as soon as they diverge", () => {
    // «Текущая» leads because it is the number the student is looking at.
    // «Итоговая» appears the day it differs, never for the first time at
    // certificate time.
    const g = officialGrade(
      student({
        current_grade: 100,
        current_letter_grade: "A",
        overall_grade: 25,
        letter_grade: "F",
      }),
    )

    expect(g.text).toBe("100.0% A")
    expect(g.finalText).toBe("25.0% F")
  })

  it("shows a hand-set grade rather than either computed number", () => {
    // There is no "current" version of a decision somebody made.
    const g = officialGrade(student({ manual_grade: "A", overall_grade: 41, current_grade: 90 }))

    expect(g.text).toBe("A")
    expect(g.finalText).toBeNull()
    expect(g.isManual).toBe(true)
  })

  it.each([
    ["not_graded_yet", "studentProgress.grade.notGradedYet"],
    ["completion_pass", "studentProgress.grade.byCompletion"],
    ["zero_weighted", "studentProgress.grade.notWeighted"],
    ["not_assessed", "studentProgress.grade.notAssessed"],
  ])("explains an absent number for %s", (state, note) => {
    const g = officialGrade(
      student({
        overall_grade: null,
        current_grade: null,
        result_state: state as StudentProgressEntry["result_state"],
      }),
    )

    expect(g.text).toBeNull()
    expect(g.noteKey).toBe(note)
  })

  it("drops the symbol on a scheme that has none", () => {
    expect(officialGrade(student({ current_letter_grade: null, letter_grade: null })).text).toBe(
      "74.0%",
    )
  })
})
