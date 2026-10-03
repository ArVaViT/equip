import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * A dialog taller than the screen must scroll inside itself. The base class
 * once said ``sm:max-h-none sm:overflow-visible`` and relied on ``Modal`` to
 * add the cap; Tailwind emitted ``max-h-none`` after ``max-h-[85vh]`` and won,
 * so the events editor ran off the top of a laptop screen, title and all.
 * Both classes in one element is a coin toss on CSS order: keep the cap in
 * the base and nothing that undoes it.
 */
describe("dialog height", () => {
  const src = readFileSync(resolve(__dirname, "../dialog.tsx"), "utf-8")
  it("is capped on wide screens and scrolls inside", () => {
    expect(src).toContain("sm:max-h-[85vh]")
    expect(src).toContain("sm:overflow-y-auto")
  })
  it("has nothing that lifts the cap", () => {
    expect(src).not.toMatch(/sm:max-h-none|sm:overflow-visible/)
  })
})
