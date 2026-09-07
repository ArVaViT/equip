import i18n from "@/i18n/config"
import type { DraftQuestion } from "./types"

/** Mirrors ``QuizQuestionCreate.points`` (``ge=1, le=100``) and the DB CHECK. */
export const MIN_POINTS = 1
export const MAX_POINTS = 100

const CHOICE_TYPES: ReadonlySet<DraftQuestion["question_type"]> = new Set(["multiple_choice", "true_false"])

/**
 * The first thing wrong with the questions, as a sentence naming the
 * question — or ``null`` when the draft can be sent.
 *
 * A quiz nobody could pass used to save without a word: a multiple-choice
 * question starts with no option marked correct (``QuestionCard`` shows an
 * empty radio group), the old check counted questions and nothing else, and
 * the teacher found out from the students. Blank option text was worse —
 * the server counts an empty string as untranslated and the whole quiz
 * answered 409 to every student who opened it.
 *
 * One problem at a time, in reading order: the teacher fixes the question
 * the toast names, saves again, and is told the next one. A list of eight
 * complaints is not read.
 */
export function firstDraftProblem(questions: DraftQuestion[]): string | null {
  for (const [index, question] of questions.entries()) {
    const n = index + 1
    if (!question.question_text.trim()) {
      return i18n.t("quizEditor.validation.questionTextRequired", { n })
    }
    if (!Number.isInteger(question.points) || question.points < MIN_POINTS || question.points > MAX_POINTS) {
      return i18n.t("quizEditor.validation.pointsRange", { n })
    }
    if (!CHOICE_TYPES.has(question.question_type)) continue
    if (question.options.length < 2) {
      return i18n.t("quizEditor.validation.tooFewOptions", { n })
    }
    const blank = question.options.findIndex((option) => !option.option_text.trim())
    if (blank >= 0) {
      return i18n.t("quizEditor.validation.optionTextRequired", { n, m: blank + 1 })
    }
    if (question.options.filter((option) => option.is_correct).length !== 1) {
      return i18n.t("quizEditor.validation.correctAnswerRequired", { n })
    }
  }
  return null
}
