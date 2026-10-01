/** A tour's spotlight does not dress a card up as a popup button. */
import { describe, expect, it } from "vitest"

import { dropPopupAttributesFromStaticElement } from "../tour"

function marked(html: string): Element {
  const host = document.createElement("div")
  host.innerHTML = html
  const el = host.firstElementChild!
  el.setAttribute("aria-haspopup", "dialog")
  el.setAttribute("aria-expanded", "true")
  el.setAttribute("aria-controls", "driver-popover-content")
  return el
}

describe("dropPopupAttributesFromStaticElement", () => {
  it("clears them from a section", () => {
    const el = marked("<section>Courses</section>")
    dropPopupAttributesFromStaticElement(el)
    expect(el.getAttribute("aria-haspopup")).toBeNull()
    expect(el.getAttribute("aria-expanded")).toBeNull()
    expect(el.getAttribute("aria-controls")).toBeNull()
  })

  it("leaves them on a real button", () => {
    const el = marked("<button>Search</button>")
    dropPopupAttributesFromStaticElement(el)
    expect(el.getAttribute("aria-haspopup")).toBe("dialog")
  })

  it("clears them from a focusable div with no role", () => {
    const el = marked('<div tabindex="0">Tile</div>')
    dropPopupAttributesFromStaticElement(el)
    expect(el.getAttribute("aria-haspopup")).toBeNull()
  })
})
