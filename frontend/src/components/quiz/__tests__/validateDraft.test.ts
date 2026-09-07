/**
 * A quiz nobody can pass used to save without a word. These pin what the
 * teacher is told instead, in Russian, naming the question — and that a
 * quiz which can be taken is let through. No ``\b`` (ASCII-only in
 * JavaScript; never matches beside a Cyrillic letter).
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { makeDefaultQuestion, makeTrueFalseOptions, type DraftQuestion } from "../editor/types"
import { firstDraftProblem } from "../editor/validateDraft"

function mcq(overrides: Partial<DraftQuestion> = {}): DraftQuestion {
  const q = makeDefaultQuestion(0)
  q.question_text = "Сколько дней творения?"
  q.options = [
    { id: "o1", option_text: "Шесть", is_correct: true, order_index: 0 },
    { id: "o2", option_text: "Семь", is_correct: false, order_index: 1 },
  ]
  return { ...q, ...overrides }
}

describe("what stops a quiz from being saved", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage("en")
  })

  it("lets a quiz that can be taken through", () => {
    expect(firstDraftProblem([mcq()])).toBeNull()
  })

  it("a fresh multiple-choice question has no correct answer — the default the teacher forgets", () => {
    const q = makeDefaultQuestion(0)
    q.question_text = "Вопрос"
    q.options[0]!.option_text = "А"
    q.options[1]!.option_text = "Б"
    expect(firstDraftProblem([mcq(), q])).toBe("Вопрос 2: отметьте правильный ответ")
  })

  it("names the option whose text is blank", () => {
    const q = mcq()
    q.options[1] = { ...q.options[1]!, option_text: "   " }
    expect(firstDraftProblem([q])).toBe("Вопрос 1, вариант 2: введите текст варианта")
  })

  it("names the question whose text is blank", () => {
    expect(firstDraftProblem([mcq(), mcq({ question_text: " " })])).toBe("Вопрос 2: введите текст вопроса")
  })

  it("refuses points outside 1–100, and fractions", () => {
    expect(firstDraftProblem([mcq({ points: 0 })])).toBe("Вопрос 1: баллы — целое число от 1 до 100")
    expect(firstDraftProblem([mcq({ points: 150 })])).toBe("Вопрос 1: баллы — целое число от 1 до 100")
    expect(firstDraftProblem([mcq({ points: 2.5 })])).toBe("Вопрос 1: баллы — целое число от 1 до 100")
    expect(firstDraftProblem([mcq({ points: 100 })])).toBeNull()
  })

  it("needs two options to choose between", () => {
    const q = mcq()
    q.options = [q.options[0]!]
    expect(firstDraftProblem([q])).toBe("Вопрос 1: нужно хотя бы два варианта")
  })

  it("a true/false question is born answerable", () => {
    const q = mcq({ question_type: "true_false", options: makeTrueFalseOptions() })
    expect(firstDraftProblem([q])).toBeNull()
  })

  it("a written answer has no options to check", () => {
    const essay = mcq({ question_type: "essay", options: [] })
    const short = mcq({ question_type: "short_answer", options: [] })
    expect(firstDraftProblem([essay, short])).toBeNull()
  })

  it("reports one problem at a time, in reading order", () => {
    const first = mcq({ question_text: "" })
    const second = mcq({ points: 0 })
    expect(firstDraftProblem([first, second])).toBe("Вопрос 1: введите текст вопроса")
  })
})
