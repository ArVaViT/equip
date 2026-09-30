import { describe, expect, it } from "vitest"

import { readingMinutes, wordsIn } from "../readingTime"

describe("reading time", () => {
  it("counts words, not tags or entities", () => {
    expect(wordsIn("<p>В начале было <strong>Слово</strong>&nbsp;и Слово</p>")).toBe(6)
  })

  it("reads Russian more slowly than English", () => {
    const text = `<p>${"слово ".repeat(1600)}</p>`
    expect(readingMinutes([text], "ru")).toBe(10)
    expect(readingMinutes([`<p>${"word ".repeat(1600)}</p>`], "en")).toBe(7)
  })

  it("says nothing for a lesson under half a minute", () => {
    expect(readingMinutes(["<p>Коротко.</p>"], "ru")).toBe(0)
  })
})
