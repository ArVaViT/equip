/**
 * A 422 used to reach the teacher as pydantic's English, joined with
 * semicolons: "Input should be less than or equal to 100; String should
 * have at least 1 character". It did not say which question. These pin
 * the sentence in Russian — who is saving a quiz tomorrow — built from the
 * identifiers (``loc``, ``type``, ``ctx``), never from ``msg``.
 * No ``\b``: it is ASCII-only in JavaScript and never matches beside a
 * Cyrillic letter.
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { describeValidationErrors, isValidationList } from "@/lib/validationErrors"

const LATIN_WORD = /(?<!\p{L})(Input|should|String|Field|required|value)(?!\p{L})/u

describe("what a 422 says", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage("en")
  })

  it("names the question and the field, and puts the limit in the sentence", () => {
    const text = describeValidationErrors([
      { loc: ["body", "questions", 1, "points"], type: "less_than_equal", ctx: { le: 100 } },
    ])
    expect(text).toBe("Вопрос 2, баллы: не больше 100")
  })

  it("counts questions and options from one, the way the teacher does", () => {
    const text = describeValidationErrors([
      { loc: ["body", "questions", 0, "options", 2, "option_text"], type: "quiz_option_blank" },
    ])
    expect(text).toBe("Вопрос 1, вариант 3: введите текст варианта")
  })

  it("translates the backend's own validator types", () => {
    const text = describeValidationErrors([{ loc: ["body", "questions", 3], type: "quiz_no_correct_option" }])
    expect(text).toBe("Вопрос 4: отметьте правильный ответ")
  })

  it("handles a field above the question list", () => {
    expect(describeValidationErrors([{ loc: ["body", "title"], type: "missing" }])).toBe("название: обязательное поле")
    expect(describeValidationErrors([{ loc: ["body", "questions"], type: "too_short", ctx: { min_length: 1 } }])).toBe(
      "вопросы: нужно хотя бы 1",
    )
  })

  it("has a sentence for a type it has never seen, and shows a field name it has no word for", () => {
    const text = describeValidationErrors([{ loc: ["body", "frobnicate"], type: "some_new_pydantic_type" }])
    expect(text).toBe("frobnicate: неверное значение")
  })

  it("lists every problem, one sentence each", () => {
    const text = describeValidationErrors([
      { loc: ["body", "questions", 0, "question_text"], type: "quiz_question_blank" },
      { loc: ["body", "passing_score"], type: "less_than_equal", ctx: { le: 100 } },
    ])
    expect(text).toBe("Вопрос 1: введите текст вопроса; проходной балл: не больше 100")
    expect(text).not.toMatch(LATIN_WORD)
  })

  it("recognises pydantic's list and nothing else", () => {
    expect(isValidationList([{ loc: ["body", "title"], type: "missing", msg: "Field required" }])).toBe(true)
    expect(isValidationList([])).toBe(false)
    expect(isValidationList("Course not found")).toBe(false)
    expect(isValidationList([{ msg: "no loc or type" }])).toBe(false)
  })
})
