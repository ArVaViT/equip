/**
 * References the server found become buttons in the rendered block — and
 * nothing else does.
 */
import { describe, expect, it } from "vitest"

import { linkScriptureIn, textForScripture } from "../scriptureLinks"

const label = (w: string) => `Открыть стих ${w}`

function block(html: string): HTMLDivElement {
  const div = document.createElement("div")
  div.innerHTML = html
  return div
}

describe("linkScriptureIn", () => {
  it("wraps each occurrence, tied with a no-break space or not", () => {
    const root = block("<p>Сила (Деян. 1:8) и снова Деян. 1:8; потом Деян 2:1–4.</p>")
    expect(linkScriptureIn(root, ["Деян. 1:8", "Деян 2:1–4"], label)).toBe(3)
    const buttons = [...root.querySelectorAll<HTMLButtonElement>("button.verse-ref")]
    expect(buttons.map((b) => [b.textContent, b.dataset.verse])).toEqual([
      ["Деян. 1:8", "0"],
      ["Деян. 1:8", "0"],
      ["Деян 2:1–4", "1"],
    ])
    expect(buttons[0]!.getAttribute("aria-label")).toBe("Открыть стих Деян. 1:8")
    expect(root.textContent).toBe("Сила (Деян. 1:8) и снова Деян. 1:8; потом Деян 2:1–4.")
  })

  it("leaves links, code and longer numbers alone, and does not wrap twice", () => {
    const root = block('<p><a href="/x">Ин 3:16</a> <code>Ин 3:16</code> Ин 3:160 <strong>Ин 3:16</strong></p>')
    expect(linkScriptureIn(root, ["Ин 3:16"], label)).toBe(1)
    expect(root.querySelector("strong button")?.textContent).toBe("Ин 3:16")
    // Running again (StrictMode, a re-render) leaves the same one button.
    linkScriptureIn(root, ["Ин 3:16"], label)
    expect(root.querySelectorAll("button.verse-ref")).toHaveLength(1)
  })

  it("prefers the longer reference", () => {
    const root = block("<p>1 Кор. 13:4</p>")
    linkScriptureIn(root, ["Кор. 13:4", "1 Кор. 13:4"], label)
    expect(root.querySelector("button")?.textContent).toBe("1 Кор. 13:4")
  })

  it("a second pass with a different list re-marks the block, so no button opens the wrong verse", () => {
    const root = block("<p>Ин 3:16 и Рим 8:28</p>")
    linkScriptureIn(root, ["Ин 3:16", "Рим 8:28"], label)
    linkScriptureIn(root, ["Рим 8:28"], label)
    const buttons = [...root.querySelectorAll<HTMLButtonElement>("button.verse-ref")]
    expect(buttons.map((b) => [b.textContent, b.dataset.verse])).toEqual([["Рим 8:28", "0"]])
    linkScriptureIn(root, [], label)
    expect(root.querySelector("button")).toBeNull()
    expect(root.textContent).toBe("Ин 3:16 и Рим 8:28")
  })
})

describe("textForScripture", () => {
  it("keeps references in neighbouring list items apart", () => {
    const root = block("<ul><li>Рим 8:28</li><li>1 Кор. 13:4</li></ul>")
    expect(textForScripture(root)).toBe("Рим 8:28\n1 Кор. 13:4")
  })
})
