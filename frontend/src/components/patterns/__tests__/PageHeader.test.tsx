import { readFileSync, readdirSync, statSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { BookOpen } from "lucide-react"
import { describe, expect, it } from "vitest"
import { PageHeader } from "../PageHeader"

const HERE = dirname(fileURLToPath(import.meta.url))
const PAGES = resolve(HERE, "..", "..", "..", "pages")

function wrap(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

function pageFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = resolve(dir, entry)
    if (statSync(full).isDirectory()) {
      if (entry !== "__tests__") pageFiles(full, acc)
    } else if (entry.endsWith(".tsx")) {
      acc.push(full)
    }
  }
  return acc
}

describe("PageHeader", () => {
  it("owns the heading rather than taking one", () => {
    // The old signature was `title: ReactNode`, so every caller brought its
    // own <h1> and its own classes — which is why eight files imported it and
    // twenty-three wrote their own header anyway.
    wrap(<PageHeader title="Каталог курсов" />)
    const h1 = screen.getByRole("heading", { level: 1 })
    expect(h1).toHaveTextContent("Каталог курсов")
    expect(h1.className).toContain("font-serif")
  })

  it("sets an icon at one size instead of three", () => {
    const { container } = wrap(<PageHeader title="Архив" icon={BookOpen} />)
    const svg = container.querySelector("h1 svg")
    expect(svg?.getAttribute("class")).toContain("h-6")
    expect(svg?.getAttribute("class")).toContain("w-6")
  })

  it("keeps an escape hatch for a heading that is a control", () => {
    // The course and module editors put an InlineEdit where the title goes.
    // That is a real variant, and it is named rather than being the default
    // door everybody walks through.
    wrap(<PageHeader titleSlot={<input aria-label="Название курса" defaultValue="Деяния" />} />)
    expect(screen.getByLabelText("Название курса")).toBeInTheDocument()
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument()
  })

  it("puts the eyebrow above the heading, not inside it", () => {
    wrap(<PageHeader eyebrow="Поток" title="Осень 2026" />)
    expect(screen.getByText("Поток")).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Осень 2026")
  })
})

/**
 * A budget, not a ban — the same shape as the geometry census in
 * `Section.test.tsx`. Twenty-three pages spelled their own page heading while
 * a `PageHeader` component sat unused in eight. Lower it as pages migrate; a
 * page with a genuinely unusual masthead is allowed, but it has to be a
 * decision somebody made rather than one nobody noticed.
 */
const HAND_ROLLED_H1_BUDGET = 17

describe("the page-heading census", () => {
  it("does not grow another hand-rolled page heading", () => {
    const offenders: string[] = []
    for (const file of pageFiles(PAGES)) {
      const text = readFileSync(file, "utf8")
      if (/<h1[\s>]/.test(text)) offenders.push(file.replace(PAGES, "pages"))
    }
    expect(
      offenders.length,
      `Pages writing their own <h1>:\n  ${offenders.join("\n  ")}\n` +
        "Use <PageHeader title=…>. If this page's masthead really is special, " +
        "raise the budget in the same commit with a reason.",
    ).toBeLessThanOrEqual(HAND_ROLLED_H1_BUDGET)
  })
})
