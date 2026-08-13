import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Eyebrow } from "../Eyebrow"

describe("Eyebrow", () => {
  it("renders a <p> with the canonical muted recipe by default", () => {
    render(<Eyebrow>Section label</Eyebrow>)
    const el = screen.getByText("Section label")
    expect(el.tagName).toBe("P")
    // The DESIGN.md recipe — 11px is the one documented arbitrary-size
    // exception and the wide tracking is load-bearing.
    expect(el).toHaveClass(
      "text-xs",
      "font-medium",
      "uppercase",
      "tracking-[0.18em]",
      "text-ink-muted",
    )
  })

  it("supports the accent tone (wider tracking, accent color)", () => {
    render(<Eyebrow tone="accent">Celebration</Eyebrow>)
    const el = screen.getByText("Celebration")
    expect(el).toHaveClass("tracking-[0.22em]", "text-accent")
    expect(el).not.toHaveClass("text-ink-muted")
  })

  it("renders as a <label> with htmlFor when used for form field eyebrows", () => {
    render(
      <>
        <Eyebrow as="label" htmlFor="field-1">
          Status
        </Eyebrow>
        <select id="field-1" />
      </>,
    )
    const label = screen.getByText("Status")
    expect(label.tagName).toBe("LABEL")
    expect(screen.getByLabelText("Status")).toBeInTheDocument()
  })

  it("merges caller className on top of the recipe", () => {
    render(
      <Eyebrow as="div" className="pb-1 text-center">
        Mon
      </Eyebrow>,
    )
    const el = screen.getByText("Mon")
    expect(el.tagName).toBe("DIV")
    expect(el).toHaveClass("pb-1", "text-center", "text-xs")
  })
})
