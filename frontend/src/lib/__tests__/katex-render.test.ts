import { describe, expect, it } from "vitest"
import { renderMathIn } from "../katex-render"

function makeContainer(innerHTML: string): HTMLDivElement {
  const div = document.createElement("div")
  div.innerHTML = innerHTML
  return div
}

describe("renderMathIn", () => {
  it("renders an inline math marker via KaTeX", () => {
    const container = makeContainer(
      '<p><span data-type="inlineMath" data-latex="x^2" data-display="no">$x^2$</span></p>',
    )
    renderMathIn(container)
    const span = container.querySelector('span[data-type="inlineMath"]')
    expect(span?.getAttribute("data-katex-rendered")).toBe("true")
    // KaTeX emits a ``.katex`` wrapper inside the marker.
    expect(span?.querySelector(".katex")).not.toBeNull()
  })

  it("respects data-display=yes for block math", () => {
    const container = makeContainer(
      '<span data-type="inlineMath" data-latex="\\sum_{i=0}^n i" data-display="yes">$$\\sum$$</span>',
    )
    renderMathIn(container)
    const span = container.querySelector('span[data-type="inlineMath"]')
    expect(span?.querySelector(".katex-display")).not.toBeNull()
  })

  it("is idempotent: the rendered flag stops a second pass", () => {
    const container = makeContainer(
      '<span data-type="inlineMath" data-latex="a" data-display="no">$a$</span>',
    )
    renderMathIn(container)
    const firstHtml = container.innerHTML
    renderMathIn(container)
    expect(container.innerHTML).toBe(firstHtml)
  })

  it("skips markers with no data-latex (corrupt HTML)", () => {
    const container = makeContainer(
      '<span data-type="inlineMath" data-display="no">$x$</span>',
    )
    expect(() => renderMathIn(container)).not.toThrow()
    const span = container.querySelector('span[data-type="inlineMath"]')
    // No render attempted → no rendered flag set.
    expect(span?.getAttribute("data-katex-rendered")).toBeNull()
    expect(span?.querySelector(".katex")).toBeNull()
  })

  it("one bad expression doesn't blank out neighbouring markers", () => {
    const container = makeContainer(
      '<span data-type="inlineMath" data-latex="x^2" data-display="no">$x^2$</span>' +
        '<span data-type="inlineMath" data-latex="\\unknown{" data-display="no">bad</span>' +
        '<span data-type="inlineMath" data-latex="y_1" data-display="no">$y_1$</span>',
    )
    expect(() => renderMathIn(container)).not.toThrow()
    const spans = container.querySelectorAll('span[data-type="inlineMath"]')
    // First + third are valid → flagged. Middle one with ``strict: "ignore"``
    // also renders (KaTeX shows the broken source) → also flagged.
    expect(spans[0]?.getAttribute("data-katex-rendered")).toBe("true")
    expect(spans[2]?.getAttribute("data-katex-rendered")).toBe("true")
  })

  it("does nothing when container is null", () => {
    expect(() => renderMathIn(null)).not.toThrow()
  })
})
