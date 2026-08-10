import { describe, expect, it } from "vitest"
import { officialColumn } from "../officialColumn"
import type { GradeBreakdown, StudentCalculatedGrade } from "@/types"

function entry(
  breakdown: Partial<GradeBreakdown> = {},
  manual_grade: string | null = null,
): StudentCalculatedGrade {
  return {
    student_id: "s1",
    student_name: "Student",
    student_email: "s@example.com",
    manual_grade,
    breakdown: {
      quiz_avg: 0,
      quiz_weighted: 0,
      assignment_avg: 0,
      assignment_weighted: 0,
      participation_pct: 0,
      participation_weighted: 0,
      final_score: 0,
      letter_grade: "",
      effective_quiz_weight: 40,
      effective_assignment_weight: 60,
      has_quiz_items: true,
      has_assignment_items: true,
      student_has_quiz_marks: true,
      student_has_assignment_marks: true,
      has_gradable_chapters: true,
      weights_redistributed: false,
      result_state: "graded",
      ...breakdown,
    },
  }
}

describe("officialColumn", () => {
  it("shows the weighted percentage with the course's own symbol", () => {
    const cell = officialColumn(entry({ final_score: 87.4, letter_grade: "B" }))

    expect(cell).toEqual({ text: "87.4% B", isManual: false, noteKey: null })
  })

  it("omits the symbol on a scheme that has none", () => {
    // percent courses have no letter; printing an empty one leaves a dangling space
    expect(officialColumn(entry({ final_score: 91, letter_grade: "" })).text).toBe("91.0%")
  })

  it("never rounds the percentage past the letter beside it", () => {
    // 89.5 printed as "90% B" leaves a teacher holding two facts that
    // contradict each other — the school's band table says 90 is an A — and
    // the one they can see is the wrong one.
    expect(officialColumn(entry({ final_score: 89.5, letter_grade: "B" })).text).toBe("89.5% B")
  })

  it("shows a hand-set grade instead of the computed one", () => {
    // The override IS the official grade (D7) — it decides the certificate and
    // the ведомость, so the column that claims to be official must show it.
    const cell = officialColumn(entry({ final_score: 41, letter_grade: "F" }, "A"))

    expect(cell.text).toBe("A")
    expect(cell.isManual).toBe(true)
  })

  it.each([
    ["completion_pass", "gradebook.table.byCompletion"],
    ["not_graded_yet", "gradebook.table.notGradedYet"],
    ["zero_weighted", "gradebook.table.notWeighted"],
    ["not_assessed", "gradebook.table.notAssessed"],
  ])("prints no number for %s, and says why", (state, note) => {
    // A bare "—" reads as a bug. Each of these is a different next action:
    // mark the first submission, fix the weights, grade this one by hand.
    const cell = officialColumn(entry({ result_state: state as GradeBreakdown["result_state"] }))

    expect(cell.text).toBeNull()
    expect(cell.noteKey).toBe(note)
  })

  it("still shows a hand-set grade when there is no computed number", () => {
    // The whole point of `not_assessed` is that a teacher must decide. Once
    // they have, the column must show their decision, not keep asking.
    const cell = officialColumn(entry({ result_state: "not_assessed" }, "4"))

    expect(cell.text).toBe("4")
    expect(cell.isManual).toBe(true)
  })

  it("prints nothing for a student the summary has no row for", () => {
    expect(officialColumn(undefined)).toEqual({ text: null, isManual: false, noteKey: null })
  })
})
