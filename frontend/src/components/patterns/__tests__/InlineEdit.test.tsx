import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { InlineEdit } from "../InlineEdit"

function TestWrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("InlineEdit — heading semantics", () => {
  it('renders a real <h1> element when size="h1"', () => {
    render(
      <InlineEdit
        size="h1"
        value="Course title"
        onSave={vi.fn()}
        placeholder="Title"
      />,
      { wrapper: TestWrapper },
    )
    // The visible heading should be discoverable by screen readers via the
    // heading role at the right level — not just by accessible name on a
    // <span> styled to look like a heading.
    expect(screen.getByRole("heading", { level: 1, name: /course title/i })).toBeInTheDocument()
  })

  it('renders a real <h2> element when size="h2"', () => {
    render(
      <InlineEdit
        size="h2"
        value="Section heading"
        onSave={vi.fn()}
      />,
      { wrapper: TestWrapper },
    )
    expect(screen.getByRole("heading", { level: 2, name: /section heading/i })).toBeInTheDocument()
  })

  it("does NOT introduce a heading for body size", () => {
    render(
      <InlineEdit
        size="body"
        value="Some body text"
        onSave={vi.fn()}
      />,
      { wrapper: TestWrapper },
    )
    expect(screen.queryByRole("heading")).not.toBeInTheDocument()
  })

  it("uses a heading wrapper even when disabled (read-only)", () => {
    render(
      <InlineEdit
        size="h1"
        value="Read-only title"
        onSave={vi.fn()}
        disabled
      />,
      { wrapper: TestWrapper },
    )
    expect(screen.getByRole("heading", { level: 1, name: /read-only title/i })).toBeInTheDocument()
  })
})
