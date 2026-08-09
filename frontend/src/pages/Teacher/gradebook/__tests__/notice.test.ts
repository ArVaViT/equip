import { describe, it, expect } from "vitest"

import { gradebookNotice, gradePillLabel } from "../notice"
import type { GradeBreakdown, GradingConfig } from "@/types"

/**
 * Every branch of the gradebook's explanation, enumerated.
 *
 * Five adversarial reviews found the same class of defect three times, each in
 * a corner nobody had listed: a banner claiming a course had no quizzes while
 * four sat in it; one telling a teacher to mark an assignment in a course with
 * no assignments; one announcing "you set quizzes to 0%" to a teacher who had
 * set them to 100%. None of them were arithmetic bugs — all three were the UI
 * confidently describing a situation that was not the one on screen.
 *
 * The wording now comes from one function, and this file is the reason it can
 * be trusted: the whole input space is spelled out, including the mirror cases
 * that kept being missed.
 */

const breakdown = (over: Partial<GradeBreakdown>): GradeBreakdown => ({
  quiz_avg: 0,
  quiz_weighted: 0,
  assignment_avg: 0,
  assignment_weighted: 0,
  participation_pct: 0,
  participation_weighted: 0,
  final_score: 0,
  letter_grade: "",
  effective_quiz_weight: 0,
  effective_assignment_weight: 0,
  has_quiz_items: false,
  has_assignment_items: false,
  has_gradable_chapters: false,
  weights_redistributed: false,
  result_state: "graded",
  ...over,
})

const config = (quiz: number, assignment: number): GradingConfig => ({
  quiz_weight: quiz,
  assignment_weight: assignment,
  participation_weight: 0,
})

describe("gradebookNotice", () => {
  it("says nothing about an ordinary graded course", () => {
    const b = breakdown({
      result_state: "graded",
      effective_quiz_weight: 40,
      effective_assignment_weight: 60,
      has_quiz_items: true,
      has_assignment_items: true,
    })

    expect(gradebookNotice(b, config(40, 60))).toBeNull()
  })

  it("explains a course that contains nothing gradable", () => {
    const b = breakdown({ result_state: "completion_pass" })

    expect(gradebookNotice(b, config(40, 60))).toBe("gradebook.summary.completionPassCourse")
  })

  it("does not call a course under construction a completion-pass course", () => {
    // A chapter typed "quiz" exists the moment it is created; the quiz is
    // saved only once it has questions. Announcing "no quizzes here, and that
    // is not an error" to a teacher looking at «Тест 1» is confidently wrong —
    // and the same sentence reaches the printed sheet.
    const b = breakdown({ result_state: "completion_pass", has_gradable_chapters: true })

    expect(gradebookNotice(b, config(40, 60))).toBe("gradebook.summary.chaptersNotFilledIn")
  })

  it("explains a course where marking has not started", () => {
    const b = breakdown({ result_state: "not_graded_yet", has_quiz_items: true })

    expect(gradebookNotice(b, config(40, 60))).toBe("gradebook.summary.notGradedYetCourse")
  })

  describe("a category weighted zero", () => {
    it("names quizzes when quizzes are the zeroed one", () => {
      const b = breakdown({
        result_state: "zero_weighted",
        has_quiz_items: true,
        has_assignment_items: true,
      })

      expect(gradebookNotice(b, config(0, 100))).toBe("gradebook.summary.quizzesWeighZero")
    })

    it("names assignments when assignments are the zeroed one", () => {
      // The mirror case, and the one that shipped broken: in `zero_weighted`
      // both *effective* weights are 0, so branching on them answered
      // "quizzes" every time — telling a teacher who had set quizzes to 100%
      // that they had set them to 0%.
      const b = breakdown({
        result_state: "zero_weighted",
        has_quiz_items: true,
        has_assignment_items: true,
      })

      expect(gradebookNotice(b, config(100, 0))).toBe("gradebook.summary.assignmentsWeighZero")
    })

    it("does not send a teacher after assignments that do not exist", () => {
      const b = breakdown({
        result_state: "zero_weighted",
        has_quiz_items: true,
        has_assignment_items: false,
      })

      expect(gradebookNotice(b, config(0, 100))).toBe(
        "gradebook.summary.quizzesWeighZeroNoAssignments",
      )
    })

    it("does not send a teacher after quizzes that do not exist", () => {
      const b = breakdown({
        result_state: "zero_weighted",
        has_quiz_items: false,
        has_assignment_items: true,
      })

      expect(gradebookNotice(b, config(100, 0))).toBe(
        "gradebook.summary.assignmentsWeighZeroNoQuizzes",
      )
    })
  })

  describe("weight redistributed to the live category", () => {
    it("distinguishes assignments that exist but are unmarked", () => {
      const b = breakdown({
        result_state: "graded",
        weights_redistributed: true,
        effective_quiz_weight: 100,
        effective_assignment_weight: 0,
        has_quiz_items: true,
        has_assignment_items: true,
      })

      expect(gradebookNotice(b, config(40, 60))).toBe("gradebook.summary.assignmentsUnmarked")
    })

    it("distinguishes a course that has no assignments at all", () => {
      const b = breakdown({
        result_state: "graded",
        weights_redistributed: true,
        effective_quiz_weight: 100,
        effective_assignment_weight: 0,
        has_quiz_items: true,
        has_assignment_items: false,
      })

      expect(gradebookNotice(b, config(40, 60))).toBe("gradebook.summary.noAssignmentsCourse")
    })

    it("distinguishes quizzes that exist but are untaken", () => {
      const b = breakdown({
        result_state: "graded",
        weights_redistributed: true,
        effective_quiz_weight: 0,
        effective_assignment_weight: 100,
        has_quiz_items: true,
        has_assignment_items: true,
      })

      expect(gradebookNotice(b, config(40, 60))).toBe("gradebook.summary.quizzesUntaken")
    })

    it("distinguishes a course that has no quizzes at all", () => {
      const b = breakdown({
        result_state: "graded",
        weights_redistributed: true,
        effective_quiz_weight: 0,
        effective_assignment_weight: 100,
        has_quiz_items: false,
        has_assignment_items: true,
      })

      expect(gradebookNotice(b, config(40, 60))).toBe("gradebook.summary.noQuizzesCourse")
    })
  })

  describe("a graded course where one category is configured at zero", () => {
    it("explains assignments that are marked but do not count", () => {
      // The gap this closes: the table shows 80% for assignments while the
      // total ignores them, and nothing on the page said why.
      const b = breakdown({
        result_state: "graded",
        weights_redistributed: false,
        effective_quiz_weight: 100,
        effective_assignment_weight: 0,
        has_quiz_items: true,
        has_assignment_items: true,
        quiz_avg: 75,
        assignment_avg: 80,
        final_score: 75,
      })

      expect(gradebookNotice(b, config(100, 0))).toBe("gradebook.summary.assignmentsNotCounted")
    })

    it("explains quizzes that are taken but do not count", () => {
      const b = breakdown({
        result_state: "graded",
        weights_redistributed: false,
        effective_quiz_weight: 0,
        effective_assignment_weight: 100,
        has_quiz_items: true,
        has_assignment_items: true,
      })

      expect(gradebookNotice(b, config(0, 100))).toBe("gradebook.summary.quizzesNotCounted")
    })

    it("says nothing when the zero-weight category holds nothing anyway", () => {
      // No marks to explain away — the ordinary shape of a quiz-only course.
      const b = breakdown({
        result_state: "graded",
        weights_redistributed: false,
        effective_quiz_weight: 100,
        effective_assignment_weight: 0,
        has_quiz_items: true,
        has_assignment_items: false,
      })

      expect(gradebookNotice(b, config(100, 0))).toBeNull()
    })
  })

  it("stays silent when there is nothing to render yet", () => {
    expect(gradebookNotice(undefined, config(40, 60))).toBeNull()
    expect(gradebookNotice(breakdown({}), undefined)).toBeNull()
  })
})

/**
 * The grade pill has its own three-way split, and it drifted from the banner's
 * once already: `zero_weighted` fell into the "not graded" branch and printed
 * «Нет оценок» in the same row as a real 87.5% two columns to the left. The
 * work had been marked — it simply carried no weight.
 */
describe("gradePillLabel", () => {
  it("shows no label at all when there is a real grade symbol", () => {
    expect(gradePillLabel("graded")).toBeNull()
  })

  it("calls a completion-only course what it is", () => {
    expect(gradePillLabel("completion_pass")).toBe("gradebook.summary.byCompletionBadge")
  })

  it("does not call marked-but-unweighted work ungraded", () => {
    expect(gradePillLabel("zero_weighted")).toBe("gradebook.summary.notWeightedBadge")
  })

  it("still says ungraded when nothing has been graded", () => {
    expect(gradePillLabel("not_graded_yet")).toBe("gradebook.summary.notGradedYetBadge")
  })
})
