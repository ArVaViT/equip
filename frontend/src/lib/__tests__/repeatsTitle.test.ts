import { describe, expect, it } from "vitest"
import { repeatsTitle } from "../repeatsTitle"

describe("a card title that only repeats the page's", () => {
  it("is caught inside a longer page title, case and punctuation aside", () => {
    expect(repeatsTitle("Эссе: что изменилось в Пятидесятницу", "Что изменилось в Пятидесятницу")).toBe(true)
    expect(repeatsTitle("Проверьте себя: Пятидесятница", "Пятидесятница")).toBe(true)
    expect(repeatsTitle("Урок 1", "урок 1")).toBe(true)
  })

  it("is not caught by part of a word, or by a different name", () => {
    expect(repeatsTitle("Пасхальные гимны", "Пасха")).toBe(false)
    expect(repeatsTitle("Проверьте себя: Пятидесятница", "Итоговый тест")).toBe(false)
    expect(repeatsTitle("Что угодно", "")).toBe(false)
  })
})
