import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ReadingSkeleton } from "../ReadingSkeleton"

describe("ReadingSkeleton", () => {
  it("announces that the region is loading without narrating the bars", () => {
    // The bars are decorative — `Skeleton` sets `aria-hidden` on each. What a
    // screen reader needs is one statement about the region, not eleven
    // announcements of nothing.
    const { container } = render(<ReadingSkeleton />)
    expect(container.firstElementChild).toHaveAttribute("aria-busy", "true")
    expect(container.querySelectorAll("[aria-hidden='true']").length).toBeGreaterThan(5)
  })

  it("draws a ragged right edge rather than a stack of identical bars", () => {
    // A block of equal full-width bars reads as a table. Prose has no straight
    // right edge, and the eye recognises the silhouette of a paragraph before
    // it can read a word of it.
    const { container } = render(<ReadingSkeleton />)
    const widths = new Set(
      [...container.querySelectorAll("[aria-hidden='true']")].map((el) =>
        [...el.classList].find((c) => c.startsWith("w-")),
      ),
    )
    expect(widths.size).toBeGreaterThan(2)
  })
})
