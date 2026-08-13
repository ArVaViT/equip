import { readFileSync, readdirSync, statSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Section } from "../Section"

const PAGES = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "pages")

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

describe("Section", () => {
  it("takes a kind of page, not a width", () => {
    render(
      <Section width="reading" as="main">
        <p>Глава</p>
      </Section>,
    )
    const el = screen.getByRole("main")
    // 680px is decision 002's measure: 68 characters per line in Cyrillic.
    expect(el.className).toContain("max-w-[680px]")
    expect(el.className).toContain("mx-auto")
  })

  it("carries its own vertical rhythm so pages stop inventing one", () => {
    const { container } = render(
      <Section>
        <p>x</p>
      </Section>,
    )
    expect(container.firstElementChild?.className).toContain("py-6")
  })

  it("still lets a page add to the shell without replacing it", () => {
    const { container } = render(
      <Section className="space-y-8">
        <p>x</p>
      </Section>,
    )
    const cls = container.firstElementChild?.className ?? ""
    expect(cls).toContain("space-y-8")
    expect(cls).toContain("max-w-5xl")
  })
})

describe("the geometry census", () => {
  /**
   * A budget, not a ban. There were twenty distinct `container mx-auto …`
   * strings in `pages/` when `Section` was written, and the point of the
   * component is that the number goes down and stays down. A page with a
   * genuinely special shell — the dashboard is locked to the viewport — is
   * allowed; twenty of them are how the product got here.
   */
  it("does not grow a new page geometry without noticing", () => {
    const geometries = new Set<string>()
    for (const file of pageFiles(PAGES)) {
      for (const m of readFileSync(file, "utf8").matchAll(/container mx-auto[^"'`]*/g)) {
        geometries.add(m[0].replace(/\s+/g, " ").trim())
      }
    }
    expect(
      geometries.size,
      `Distinct page geometries found:\n  ${[...geometries].sort().join("\n  ")}\n` +
        "Use <Section> unless the page's shell is genuinely special — and if it " +
        "is, raise this number in the same commit with a reason.",
    ).toBeLessThanOrEqual(BUDGET)
  })
})

/** Lower it as pages migrate; never raise it without a sentence saying why. */
const BUDGET = 18
