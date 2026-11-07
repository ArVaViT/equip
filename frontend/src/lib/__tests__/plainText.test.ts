import { describe, expect, it } from "vitest"

import { asPlainText } from "../plainText"

/**
 * A plain-text field that arrived with HTML in it reads as text (2026-11-06:
 * a student saw «<p>Прочитайте книгу…</p>» under an assignment).
 */
describe("asPlainText", () => {
  it("drops the tags and keeps the paragraphs", () => {
    expect(asPlainText("<p>Прочитайте книгу.</p><p>Сообщите преподавателю.</p>")).toBe(
      "Прочитайте книгу.\nСообщите преподавателю.",
    )
  })

  it("turns a line break into a new line", () => {
    expect(asPlainText("Первое<br>второе<br/>третье")).toBe("Первое\nвторое\nтретье")
  })

  it("leaves plain text, angle brackets and all, as it is", () => {
    expect(asPlainText("Сравните 2 < 3 и Рим. 8:1")).toBe("Сравните 2 < 3 и Рим. 8:1")
  })

  it("never runs anything it is handed", () => {
    expect(asPlainText('<p>Текст</p><img src=x onerror="window.__ran=1"><script>window.__ran=1</script>')).toBe("Текст")
    expect((window as unknown as { __ran?: number }).__ran).toBeUndefined()
  })
})
