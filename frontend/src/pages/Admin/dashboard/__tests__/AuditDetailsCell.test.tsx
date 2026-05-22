import type { ReactNode } from "react"
import { render, screen, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { AuditDetailsCell } from "../AuditDetailsCell"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("AuditDetailsCell", () => {
  it("renders an em-dash when details is null", () => {
    render(<AuditDetailsCell details={null} />, { wrapper: Wrapper })
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("renders an em-dash when details is empty", () => {
    render(<AuditDetailsCell details={{}} />, { wrapper: Wrapper })
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("renders the field/old/new shape as 'field: old → new'", () => {
    render(
      <AuditDetailsCell
        details={{ field: "title", old: "Old name", new: "New name" }}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText("title:")).toBeInTheDocument()
    expect(screen.getByText("Old name")).toBeInTheDocument()
    expect(screen.getByText("New name")).toBeInTheDocument()
    expect(screen.getByText("→")).toBeInTheDocument()
  })

  it("accepts before/after synonyms in place of old/new", () => {
    render(
      <AuditDetailsCell details={{ field: "status", before: "draft", after: "published" }} />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText("draft")).toBeInTheDocument()
    expect(screen.getByText("published")).toBeInTheDocument()
  })

  it("falls back to a key:value list for arbitrary payloads", () => {
    render(
      <AuditDetailsCell details={{ approver: "u-123", cohort: "c-abc" }} />,
      { wrapper: Wrapper },
    )
    const items = screen.getAllByRole("listitem")
    expect(items).toHaveLength(2)
    const first = items[0]!
    expect(within(first).getByText("approver:")).toBeInTheDocument()
    expect(within(first).getByText("u-123")).toBeInTheDocument()
  })

  it("truncates long string values so the row height stays bounded", () => {
    const longString = "a".repeat(200)
    render(<AuditDetailsCell details={{ note: longString }} />, { wrapper: Wrapper })
    const rendered = screen.getByText(/^a+…$/)
    expect(rendered.textContent!.length).toBeLessThanOrEqual(81)
  })

  it("stringifies booleans and numbers safely", () => {
    render(<AuditDetailsCell details={{ count: 42, active: true, empty: null }} />, {
      wrapper: Wrapper,
    })
    expect(screen.getByText("42")).toBeInTheDocument()
    expect(screen.getByText("true")).toBeInTheDocument()
    expect(screen.getByText("null")).toBeInTheDocument()
  })
})
