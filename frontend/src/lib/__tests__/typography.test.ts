import { describe, expect, it } from "vitest"

import { tieText, tieTypographyIn } from "../typography"

const NB = " "

/**
 * The most common line-breaking defects in a Bible-study lesson, prevented
 * when it is shown: a reference split from its book, a one-letter word left
 * hanging, a dash starting a line.
 */
describe("lesson typography", () => {
  it("keeps a verse reference on one line in every language", () => {
    expect(tieText("см. Ин 3:16 и дальше", "ru")).toContain(`Ин${NB}3:16`)
    expect(tieText("see John 3:16", "en")).toBe(`see John${NB}3:16`)
    expect(tieText("vgl. Joh 3,16", "de")).toBe(`vgl. Joh${NB}3,16`)
    expect(tieText("Пс. 22:1", "ru")).toBe(`Пс.${NB}22:1`)
  })

  it("keeps a numbered book with its number", () => {
    expect(tieText("читаем 1 Кор 13:4", "ru")).toBe(`читаем 1${NB}Кор${NB}13:4`)
    expect(tieText("in 2 Tim 3:16", "en")).toBe(`in 2${NB}Tim${NB}3:16`)
  })

  it("leaves no one-letter word at the end of a line in Russian and Ukrainian", () => {
    expect(tieText("и в Иерусалиме", "ru")).toBe(`и${NB}в${NB}Иерусалиме`)
    expect(tieText("Павло пішов у Єрусалим і з ним", "uk")).toBe(`Павло пішов у${NB}Єрусалим і${NB}з${NB}ним`)
  })

  it("does not start a line with a dash in Russian", () => {
    expect(tieText("Вера — это", "ru")).toBe(`Вера${NB}— это`)
  })

  it("does not touch English words or German prose it has no rule for", () => {
    expect(tieText("a man and a woman", "en")).toBe("a man and a woman")
    expect(tieText("Er ging in die Stadt", "de")).toBe("Er ging in die Stadt")
  })

  it("leaves code and math alone", () => {
    const root = document.createElement("div")
    root.innerHTML = "<p>и в доме</p><pre><code>и в коде</code></pre><p>формула $a и b$</p>"
    tieTypographyIn(root, "ru")
    const [p, code, math] = [root.querySelector("p")!, root.querySelector("code")!, root.querySelectorAll("p")[1]!]
    expect(p.textContent).toBe(`и${NB}в${NB}доме`)
    expect(code.textContent).toBe("и в коде")
    expect(math.textContent).toBe("формула $a и b$")
  })
})
