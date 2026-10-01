import type { TFunction } from "i18next"
import type { QuizQuestionType } from "@/types"

export interface DraftOption {
  id: string
  option_text: string
  is_correct: boolean
  order_index: number
}

export interface DraftQuestion {
  id: string
  question_text: string
  question_type: QuizQuestionType
  order_index: number
  points: number
  min_words: number | null
  options: DraftOption[]
}

let _uid = 0
function uid(): string {
  return `draft-${++_uid}-${Date.now()}`
}

/**
 * Draft questions from text pasted into the import dialog, numbered after the
 * questions already in the quiz. One point each, multiple choice — what the
 * text says; the teacher adjusts any of it before saving, as with any draft.
 */
export function draftsFromImport(
  imported: { question_text: string; options: { option_text: string; is_correct: boolean }[] }[],
  startAt: number,
): DraftQuestion[] {
  return imported.map((q, i) => ({
    id: uid(),
    question_text: q.question_text,
    question_type: "multiple_choice",
    order_index: startAt + i,
    points: 1,
    min_words: null,
    options: q.options.map((o, j) => ({ id: uid(), option_text: o.option_text, is_correct: o.is_correct, order_index: j })),
  }))
}

export function makeTrueFalseOptions(): DraftOption[] {
  return [
    { id: uid(), option_text: "True", is_correct: true, order_index: 0 },
    { id: uid(), option_text: "False", is_correct: false, order_index: 1 },
  ]
}

/**
 * Map a True/False option's persisted English value to the localized
 * display string. The DB stores ``"True"`` / ``"False"`` literally
 * (legacy + keeps the schema locale-neutral); the UI renders the
 * translation via the ``quizEditor.questions.trueFalseOption.*`` keys.
 *
 * Unknown values fall back to the raw text so nothing silently
 * disappears if a future option type slips through.
 */
export function getTrueFalseLabel(optionText: string, t: TFunction): string {
  if (optionText === "True") return t("quizEditor.questions.trueFalseOption.True")
  if (optionText === "False") return t("quizEditor.questions.trueFalseOption.False")
  return optionText
}

export function makeDefaultOption(order: number): DraftOption {
  return { id: uid(), option_text: "", is_correct: false, order_index: order }
}

export function makeDefaultQuestion(order: number): DraftQuestion {
  return {
    id: uid(),
    question_text: "",
    question_type: "multiple_choice",
    order_index: order,
    points: 1,
    min_words: null,
    options: [makeDefaultOption(0), makeDefaultOption(1)],
  }
}
