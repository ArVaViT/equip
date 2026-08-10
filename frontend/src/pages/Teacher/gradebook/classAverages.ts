import type { StudentCalculatedGrade } from "@/types"

export interface ClassAverages {
  /** Mean quiz percentage across the students who have a grade. `null` = "—". */
  quiz: number | null
  assignment: number | null
  /** How many students the two figures above are computed from. */
  countedStudents: number
}

/** The states where the student has no number, so contributes none. */
const NO_NUMBER = new Set(["completion_pass", "not_graded_yet", "not_assessed"])

/**
 * The footer row of the gradebook: the class's category averages.
 *
 * Two things it must not do, both of which it used to.
 *
 * **Average in students who have no average.** A student nobody has marked has
 * `quiz_avg = 0.0` on the wire — not because they scored nothing, but because
 * there is nothing to report. Counting them dragged the class figure down by
 * exactly the students who had not been assessed, so the number moved every
 * time somebody enrolled. Only students the calculator gave a grade to are
 * counted, which is the rule the backend already applies to `class_average`.
 *
 * A `graded` student who simply never sat a quiz *is* counted at 0: they were
 * set the work and did not do it, and that is a real fact about the class.
 *
 * **Read one student's state as the whole class's.** The row decided whether to
 * print anything at all from `students[0]`, so a single unmarked student
 * sorted to the top blanked the averages for everyone else.
 *
 * `zero_weighted` counts: those marks are real, they simply carry no weight
 * toward the final grade. Dashing them out while every row above shows a figure
 * is the same defect one line lower.
 */
export function classAverages(students: StudentCalculatedGrade[]): ClassAverages {
  const counted = students.filter((s) => !NO_NUMBER.has(s.breakdown.result_state))
  if (counted.length === 0) {
    return { quiz: null, assignment: null, countedStudents: 0 }
  }

  // Averaged over the students who have a figure in *that* category, which is
  // not the same set for quizzes and for assignments: a class can be halfway
  // through its tests with no essay marked yet. Folding a student with nothing
  // marked in at 0.0 is how the class average dropped every time somebody
  // enrolled.
  const withQuizMarks = counted.filter((s) => s.breakdown.student_has_quiz_marks)
  const withAssignmentMarks = counted.filter((s) => s.breakdown.student_has_assignment_marks)
  const mean = (rows: StudentCalculatedGrade[], pick: (s: StudentCalculatedGrade) => number) =>
    rows.length === 0 ? null : rows.reduce((acc, s) => acc + pick(s), 0) / rows.length

  return {
    quiz: mean(withQuizMarks, (s) => s.breakdown.quiz_avg),
    assignment: mean(withAssignmentMarks, (s) => s.breakdown.assignment_avg),
    countedStudents: counted.length,
  }
}
