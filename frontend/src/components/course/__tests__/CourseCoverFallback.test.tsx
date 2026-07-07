import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { axe } from "@/test/a11y"
import { CourseCoverFallback } from "../CourseCoverFallback"

describe("CourseCoverFallback", () => {
  it("renders the uppercase initial of the title", () => {
    const { getByText } = render(<CourseCoverFallback courseId="course-1" title="genesis foundations" />)
    expect(getByText("G")).toBeInTheDocument()
  })

  it("is deterministic — the same course id always gets the same tint class", () => {
    const first = render(<CourseCoverFallback courseId="course-abc" title="Romans" />)
    const second = render(<CourseCoverFallback courseId="course-abc" title="Romans" />)
    const tintClass = (el: HTMLElement) =>
      Array.from(el.firstElementChild!.classList).find((c) => c.startsWith("course-cover-tint-"))
    expect(tintClass(first.container)).toBe(tintClass(second.container))
  })

  it("picks different tints across different course ids (spread, not identical for a small sample)", () => {
    const ids = ["a", "b", "c", "d", "e", "f", "g", "h"]
    const tints = new Set(
      ids.map((id) => {
        const { container } = render(<CourseCoverFallback courseId={id} title="X" />)
        return Array.from(container.firstElementChild!.classList).find((c) => c.startsWith("course-cover-tint-"))
      }),
    )
    expect(tints.size).toBeGreaterThan(1)
  })

  it("falls back to a placeholder glyph for a blank title", () => {
    const { getByText } = render(<CourseCoverFallback courseId="course-2" title="   " />)
    expect(getByText("?")).toBeInTheDocument()
  })

  it("is purely decorative (aria-hidden) since the real title renders as text elsewhere", () => {
    const { container } = render(<CourseCoverFallback courseId="course-3" title="Exodus" />)
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true")
  })

  it("renders without a11y violations", async () => {
    const { container } = render(
      <div>
        <h2>Exodus</h2>
        <CourseCoverFallback courseId="course-4" title="Exodus" />
      </div>,
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
