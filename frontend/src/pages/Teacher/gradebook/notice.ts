import type { GradeBreakdown, GradingConfig } from "@/types"

/**
 * Which explanation the gradebook owes the teacher, if any.
 *
 * This lives in its own function for one reason: every time the wording was
 * decided inline it started lying in some corner. Five adversarial reviews
 * produced, in order — a banner claiming a course had no quizzes while four
 * sat in it; a banner telling teachers to mark an assignment in a course with
 * no assignments; and a banner announcing "you set quizzes to 0%" to a teacher
 * who had set them to 100%. Each was a different branch nobody had enumerated.
 *
 * So the branches are enumerated here, in one place, over the inputs that
 * actually decide the sentence:
 *
 * - `state` — is there a score at all, and if not, why not;
 * - the **configured** weights — what the teacher chose. Never the effective
 *   ones: in `zero_weighted` both effective weights are 0, so asking which of
 *   them is zero tells you nothing and quietly answers "quizzes" every time;
 * - whether the course **contains** items of each kind — otherwise the advice
 *   points at work that does not exist.
 *
 * Returns a translation key, or null when the gradebook has nothing to explain.
 */
export function gradebookNotice(
  breakdown: GradeBreakdown | undefined,
  config: GradingConfig | undefined,
): string | null {
  if (!breakdown || !config) return null

  const { result_state, has_quiz_items, has_assignment_items, weights_redistributed } = breakdown

  if (result_state === "completion_pass") {
    // A chapter typed "quiz" exists from the moment it is created; the quiz
    // itself is only saved once it has questions. Announcing "this course has
    // no quizzes, and that is not an error" to a teacher looking at a chapter
    // named «Тест 1» is confidently wrong — and the same claim reaches the
    // exported sheet, certifying a completion pass for a course still being
    // built.
    return breakdown.has_gradable_chapters
      ? "gradebook.summary.chaptersNotFilledIn"
      : "gradebook.summary.completionPassCourse"
  }

  if (result_state === "not_graded_yet") return "gradebook.summary.notGradedYetCourse"

  if (result_state === "zero_weighted") {
    // Graded work exists but sits in a category the teacher weighted 0%.
    // Which one is zero comes from the configuration, and what the teacher
    // should expect next depends on whether the *other* kind of work is even
    // in the course.
    if (config.quiz_weight === 0) {
      return has_assignment_items
        ? "gradebook.summary.quizzesWeighZero"
        : "gradebook.summary.quizzesWeighZeroNoAssignments"
    }
    return has_quiz_items
      ? "gradebook.summary.assignmentsWeighZero"
      : "gradebook.summary.assignmentsWeighZeroNoQuizzes"
  }

  // A graded course where one category is configured at 0% but does carry
  // marks. The score is real and so are those marks — they simply contribute
  // nothing, and without a word about it the teacher sees 80% next to a total
  // that ignores it. Distinct from `zero_weighted`, where there is no score at
  // all: here the promise "a percentage appears once..." would be nonsense,
  // the percentage is already on screen.
  if (result_state === "graded" && !weights_redistributed) {
    if (config.assignment_weight === 0 && has_assignment_items) {
      return "gradebook.summary.assignmentsNotCounted"
    }
    if (config.quiz_weight === 0 && has_quiz_items) {
      return "gradebook.summary.quizzesNotCounted"
    }
  }

  if (weights_redistributed) {
    // One category is carrying the whole grade because the other has nothing
    // graded in it. Whether that is permanent (no such items exist) or
    // temporary (items exist, unmarked) changes both the reason and what
    // happens next — including that grades will *fall* for students with
    // nothing marked.
    if (breakdown.effective_assignment_weight === 0) {
      return has_assignment_items
        ? "gradebook.summary.assignmentsUnmarked"
        : "gradebook.summary.noAssignmentsCourse"
    }
    return has_quiz_items ? "gradebook.summary.quizzesUntaken" : "gradebook.summary.noQuizzesCourse"
  }

  return null
}


/**
 * The label shown in the grade column when there is no symbol to show.
 *
 * Lives beside `gradebookNotice` because it drifted from it once already:
 * `zero_weighted` fell through into the "not graded" branch and printed «Нет
 * оценок» in the same row as a real 87.5% two columns to the left. The work
 * had been marked; it simply carried no weight.
 */
export function gradePillLabel(state: GradeBreakdown["result_state"]): string | null {
  switch (state) {
    case "graded":
      return null
    case "completion_pass":
      return "gradebook.summary.byCompletionBadge"
    case "zero_weighted":
      return "gradebook.summary.notWeightedBadge"
    case "not_graded_yet":
      return "gradebook.summary.notGradedYetBadge"
  }
}
