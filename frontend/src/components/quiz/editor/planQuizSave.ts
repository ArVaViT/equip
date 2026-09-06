import type { QuizOptionPatch, QuizQuestionPatch, QuizUpdateData } from "@/services/quizzes"
import type { Quiz } from "@/types"
import type { DraftQuestion } from "./types"

/** The editor's state, normalised the way the API stores it. */
export interface DraftSnapshot {
  title: string
  description: string | null
  passingScore: number
  /** ``null`` for a plain quiz — only an exam caps attempts. */
  maxAttempts: number | null
  questions: DraftQuestion[]
}

/**
 * What to send to keep a saved quiz — and every attempt on it — in place.
 *
 * Saving used to mean ``POST`` a new quiz and ``DELETE`` the old one, and
 * ``quiz_attempts.quiz_id`` cascades: a teacher fixing a typo deleted the
 * class's graded work. The backend has had ``PATCH /quizzes/questions/{id}``
 * and ``PATCH /quizzes/options/{id}`` for exactly this since #1167; the
 * editor never called them. Now it does, sending only what changed.
 */
export interface InPlacePlan {
  quiz: QuizUpdateData | null
  questions: Array<{ id: string; patch: QuizQuestionPatch }>
  options: Array<{ id: string; patch: QuizOptionPatch }>
}

export function isEmptyPlan(plan: InPlacePlan): boolean {
  return plan.quiz === null && plan.questions.length === 0 && plan.options.length === 0
}

function sameIds(a: ReadonlyArray<{ id: string }>, b: ReadonlyArray<{ id: string }>): boolean {
  if (a.length !== b.length) return false
  const ids = new Set(a.map((item) => item.id))
  return b.every((item) => ids.has(item.id))
}

/**
 * ``null`` when the draft adds or removes a question or an option.
 *
 * There is no route for that shape on purpose: deleting an option nulls
 * ``quiz_answers.selected_option_id`` and a graded attempt stops saying
 * what the student chose. A structural change is a rebuild, and the caller
 * decides — with the teacher — whether the attempts are worth it.
 */
export function planInPlaceSave(existing: Quiz, draft: DraftSnapshot): InPlacePlan | null {
  if (!sameIds(existing.questions, draft.questions)) return null
  const byId = new Map(existing.questions.map((question) => [question.id, question]))
  for (const question of draft.questions) {
    const saved = byId.get(question.id)
    if (!saved || !sameIds(saved.options, question.options)) return null
  }

  const quiz: QuizUpdateData = {}
  if (draft.title !== existing.title) quiz.title = draft.title
  if (draft.description !== (existing.description ?? null)) quiz.description = draft.description
  if (draft.passingScore !== existing.passing_score) quiz.passing_score = draft.passingScore
  if (draft.maxAttempts !== (existing.max_attempts ?? null)) quiz.max_attempts = draft.maxAttempts

  const questions: InPlacePlan["questions"] = []
  const options: InPlacePlan["options"] = []
  for (const question of draft.questions) {
    const saved = byId.get(question.id)
    if (!saved) return null
    const patch: QuizQuestionPatch = {}
    if (question.question_text !== saved.question_text) patch.question_text = question.question_text
    if (question.question_type !== saved.question_type) patch.question_type = question.question_type
    if (question.order_index !== saved.order_index) patch.order_index = question.order_index
    if (question.points !== saved.points) patch.points = question.points
    if ((question.min_words ?? null) !== (saved.min_words ?? null)) patch.min_words = question.min_words ?? null
    if (Object.keys(patch).length > 0) questions.push({ id: question.id, patch })

    const savedOptions = new Map(saved.options.map((option) => [option.id, option]))
    for (const option of question.options) {
      const savedOption = savedOptions.get(option.id)
      if (!savedOption) return null
      const optionPatch: QuizOptionPatch = {}
      if (option.option_text !== savedOption.option_text) optionPatch.option_text = option.option_text
      if (option.is_correct !== Boolean(savedOption.is_correct)) optionPatch.is_correct = option.is_correct
      if (option.order_index !== savedOption.order_index) optionPatch.order_index = option.order_index
      if (Object.keys(optionPatch).length > 0) options.push({ id: option.id, patch: optionPatch })
    }
  }

  return { quiz: Object.keys(quiz).length > 0 ? quiz : null, questions, options }
}
