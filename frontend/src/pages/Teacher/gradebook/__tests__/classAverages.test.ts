import { describe, expect, it } from "vitest"
import { classAverages } from "../classAverages"
import type { GradeBreakdown, StudentCalculatedGrade } from "@/types"

function student(id: string, over: Partial<GradeBreakdown> = {}): StudentCalculatedGrade {
  return {
    student_id: id,
    student_name: id,
    student_email: `${id}@example.com`,
    manual_grade: null,
    breakdown: {
      quiz_avg: 0,
      quiz_weighted: 0,
      assignment_avg: 0,
      assignment_weighted: 0,
      participation_pct: 0,
      participation_weighted: 0,
      final_score: 0,
      letter_grade: "",
      effective_quiz_weight: 50,
      effective_assignment_weight: 50,
      has_quiz_items: true,
      has_assignment_items: true,
      student_has_quiz_marks: true,
      student_has_assignment_marks: true,
      has_gradable_chapters: true,
      weights_redistributed: false,
      result_state: "graded",
      ...over,
    },
  }
}

describe("classAverages", () => {
  it("averages the students who have a grade", () => {
    const result = classAverages([
      student("a", { quiz_avg: 80, assignment_avg: 60 }),
      student("b", { quiz_avg: 100, assignment_avg: 40 }),
    ])

    expect(result).toEqual({ quiz: 90, assignment: 50, countedStudents: 2 })
  })

  it("leaves out students nobody has marked", () => {
    // Their `quiz_avg` is 0.0 on the wire because there is nothing to report,
    // not because they scored nothing. Counting them made the class average
    // drop every time somebody enrolled.
    const result = classAverages([
      student("a", { quiz_avg: 90, assignment_avg: 90 }),
      student("newcomer", { result_state: "not_graded_yet" }),
    ])

    expect(result.quiz).toBe(90)
    expect(result.countedStudents).toBe(1)
  })

  it("counts a graded student who simply never sat the quiz", () => {
    // They were set the work and did not do it. That is a real fact about the
    // class and belongs in its average.
    const result = classAverages([
      student("a", { quiz_avg: 100 }),
      student("b", { quiz_avg: 0 }),
    ])

    expect(result.quiz).toBe(50)
    expect(result.countedStudents).toBe(2)
  })

  it("does not let one unmarked student blank the whole row", () => {
    // The row used to decide from `students[0]`, so a single unmarked student
    // sorted to the top dashed out the averages for everyone else.
    const result = classAverages([
      student("first", { result_state: "not_graded_yet" }),
      student("b", { quiz_avg: 70, assignment_avg: 70 }),
      student("c", { quiz_avg: 90, assignment_avg: 90 }),
    ])

    expect(result.quiz).toBe(80)
    expect(result.assignment).toBe(80)
  })

  it("keeps zero-weighted marks — they are real, they just carry no weight", () => {
    const result = classAverages([student("a", { result_state: "zero_weighted", quiz_avg: 88 })])

    expect(result.quiz).toBe(88)
  })

  it("shows no average for a category the course does not have", () => {
    // An empty column is honest; 0.0% claims the class failed something that
    // was never set. No items means no marks, so the same filter covers it.
    const result = classAverages([
      student("a", {
        has_assignment_items: false,
        student_has_assignment_marks: false,
        quiz_avg: 75,
      }),
    ])

    expect(result.quiz).toBe(75)
    expect(result.assignment).toBeNull()
  })

  it("averages each category over its own set of marked students", () => {
    // A class can be halfway through its tests with no essay marked yet. The
    // quiz column has a figure; the assignment column must not invent one out
    // of the zeros sitting in the unmarked rows.
    const result = classAverages([
      student("a", { quiz_avg: 80, student_has_assignment_marks: false }),
      student("b", { quiz_avg: 60, student_has_assignment_marks: false }),
    ])

    expect(result.quiz).toBe(70)
    expect(result.assignment).toBeNull()
  })

  it("shows nothing at all when nobody has a grade", () => {
    const result = classAverages([
      student("a", { result_state: "not_graded_yet" }),
      student("b", { result_state: "not_assessed" }),
    ])

    expect(result).toEqual({ quiz: null, assignment: null, countedStudents: 0 })
  })

  it("survives an empty roster without dividing by zero", () => {
    expect(classAverages([])).toEqual({ quiz: null, assignment: null, countedStudents: 0 })
  })
})
