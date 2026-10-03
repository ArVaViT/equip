import type { QuizQuestionSave, QuizUpdateData } from "@/services/quizzes"
import type { Quiz } from "@/types"
import type { DraftQuestion } from "./types"

/** The editor's state, normalised the way the API stores it. */
export interface DraftSnapshot {
  title: string
  description: string | null
  passingScore: number
  /** ``null`` for a plain quiz — only an exam caps attempts. */
  maxAttempts: number | null
  /** The lesson's kind. The server reads it for whether a finished attempt
   *  shows the right answers, so it has to follow the lesson. */
  quizType: "quiz" | "exam"
  questions: DraftQuestion[]
}

/**
 * What to send to keep a saved quiz — and every attempt on it — in place.
 *
 * Saving used to mean ``POST`` a new quiz and ``DELETE`` the old one, and
 * ``quiz_attempts.quiz_id`` cascades: a teacher fixing a typo deleted the
 * class's graded work. Corrections go to the quiz that exists instead:
 * the fields above the questions to ``PUT /quizzes/{id}``, and each
 * changed question — whole, with every one of its options — to
 * ``PUT /quizzes/questions/{id}``. Only questions with a change are sent.
 *
 * Whole, not field by field: the right answer moving from one option to
 * another was two requests, and in between the question had no right
 * answer — so the server could not refuse a question saved that way on
 * purpose, and let one through (2026-10-03). One request per question is
 * one state the server can judge the way it judges a new question.
 */
export interface InPlacePlan {
  quiz: QuizUpdateData | null
  questions: Array<{ id: string; question: QuizQuestionSave }>
}

export function isEmptyPlan(plan: InPlacePlan): boolean {
  return plan.quiz === null && plan.questions.length === 0
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
  // A lesson switched between quiz and exam kept the old kind on the quiz:
  // an «exam» went on showing the right answers (2026-10-03).
  if (draft.quizType !== existing.quiz_type) quiz.quiz_type = draft.quizType

  const questions: InPlacePlan["questions"] = []
  for (const question of draft.questions) {
    const saved = byId.get(question.id)
    if (!saved) return null
    const savedOptions = new Map(saved.options.map((option) => [option.id, option]))
    let changed =
      question.question_text !== saved.question_text ||
      question.question_type !== saved.question_type ||
      question.order_index !== saved.order_index ||
      question.points !== saved.points ||
      (question.min_words ?? null) !== (saved.min_words ?? null)
    for (const option of question.options) {
      const savedOption = savedOptions.get(option.id)
      if (!savedOption) return null
      changed ||=
        option.option_text !== savedOption.option_text ||
        option.is_correct !== Boolean(savedOption.is_correct) ||
        option.order_index !== savedOption.order_index
    }
    if (!changed) continue
    questions.push({
      id: question.id,
      question: {
        question_text: question.question_text,
        question_type: question.question_type,
        order_index: question.order_index,
        points: question.points,
        min_words: question.question_type === "essay" ? (question.min_words ?? null) : null,
        options: question.options.map((option) => ({
          id: option.id,
          option_text: option.option_text,
          is_correct: option.is_correct,
          order_index: option.order_index,
        })),
      },
    })
  }

  return { quiz: Object.keys(quiz).length > 0 ? quiz : null, questions }
}

/**
 * The draft with the ids the server gave its questions and options on
 * create, matched by position; the draft's own text stays as typed.
 *
 * After the first save a new quiz kept its client-side ids, so
 * `planInPlaceSave` found nothing to match and the next save rebuilt the
 * whole quiz — and once students had attempts, a rebuild takes them (with
 * a confirm). All or nothing: if the shapes differ, the draft is returned
 * unchanged and the old behaviour stands.
 */
export function adoptServerIds(draft: DraftQuestion[], saved: Quiz): DraftQuestion[] {
  const byOrder = new Map(saved.questions.map((question) => [question.order_index, question]))
  if (byOrder.size !== draft.length) return draft
  const adopted: DraftQuestion[] = []
  for (const question of draft) {
    const server = byOrder.get(question.order_index)
    if (!server || server.options.length !== question.options.length) return draft
    const options = new Map(server.options.map((option) => [option.order_index, option]))
    const nextOptions = []
    for (const option of question.options) {
      const serverOption = options.get(option.order_index)
      if (!serverOption) return draft
      nextOptions.push({ ...option, id: serverOption.id })
    }
    adopted.push({ ...question, id: server.id, options: nextOptions })
  }
  return adopted
}
