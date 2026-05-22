import { describe, expect, it } from "vitest"
import { renderToggleCalloutsIn } from "../callout-toggle"

function makeContainer(innerHTML: string): HTMLDivElement {
  const div = document.createElement("div")
  div.innerHTML = innerHTML
  return div
}

describe("renderToggleCalloutsIn", () => {
  it("rewrites a toggle div to native details/summary", () => {
    const container = makeContainer(
      '<div data-callout="toggle" class="callout callout-toggle">' +
        "<p>What is grace?</p><p>Unmerited favor.</p>" +
        "</div>",
    )
    renderToggleCalloutsIn(container)
    const details = container.querySelector("details")
    expect(details).not.toBeNull()
    expect(details?.getAttribute("data-callout")).toBe("toggle")
    expect(details?.getAttribute("class")).toBe("callout callout-toggle")
    const summary = details?.querySelector("summary")
    expect(summary?.textContent).toBe("What is grace?")
    const body = details?.querySelectorAll(":scope > p")
    expect(body?.length).toBe(1)
    expect(body?.[0]?.textContent).toBe("Unmerited favor.")
  })

  it("preserves inline formatting inside the first paragraph", () => {
    const container = makeContainer(
      '<div data-callout="toggle"><p>Read <strong>John 1:1</strong></p><p>body</p></div>',
    )
    renderToggleCalloutsIn(container)
    const summary = container.querySelector("details > summary")
    expect(summary?.innerHTML).toBe("Read <strong>John 1:1</strong>")
  })

  it("is idempotent: second call leaves DOM unchanged", () => {
    const container = makeContainer(
      '<div data-callout="toggle"><p>q</p><p>a</p></div>',
    )
    renderToggleCalloutsIn(container)
    const firstHtml = container.innerHTML
    renderToggleCalloutsIn(container)
    expect(container.innerHTML).toBe(firstHtml)
    // And no nested details accidentally created on the second pass.
    expect(container.querySelectorAll("details").length).toBe(1)
  })

  it("preserves id and arbitrary class attributes on the rewritten element", () => {
    const container = makeContainer(
      '<div data-callout="toggle" id="custom-id" class="callout callout-toggle special-class">' +
        "<p>q</p><p>a</p></div>",
    )
    renderToggleCalloutsIn(container)
    const details = container.querySelector("details")
    expect(details?.getAttribute("id")).toBe("custom-id")
    expect(details?.getAttribute("class")).toBe(
      "callout callout-toggle special-class",
    )
  })

  it("flags an empty toggle as rendered without throwing", () => {
    const container = makeContainer('<div data-callout="toggle"></div>')
    expect(() => renderToggleCalloutsIn(container)).not.toThrow()
    const div = container.querySelector('div[data-callout="toggle"]')
    expect(div?.getAttribute("data-toggle-rendered")).toBe("true")
    // The empty case is intentionally left as a div, not promoted to
    // details — there's no summary content to put inside one.
    expect(container.querySelector("details")).toBeNull()
  })

  it("leaves non-toggle callouts (info, verse, …) alone", () => {
    const container = makeContainer(
      '<div data-callout="info"><p>note</p></div>' +
        '<div data-callout="verse"><p>scripture</p></div>',
    )
    renderToggleCalloutsIn(container)
    expect(container.querySelectorAll("details").length).toBe(0)
    expect(container.querySelectorAll("div[data-callout]").length).toBe(2)
  })

  it("does nothing when container is null", () => {
    expect(() => renderToggleCalloutsIn(null)).not.toThrow()
  })
})
