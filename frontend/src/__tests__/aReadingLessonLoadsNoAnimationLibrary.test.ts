/**
 * A reading lesson does not load the animation library.
 *
 * On 2026-10-01 a phone opening a reading lesson loaded 85 KB of JavaScript
 * beyond the app's start, 38 KB of it the animation library, for an icon that
 * springs in on a test's results screen the lesson never shows. Two imports
 * did it: the test component itself, and the `@/components/motion` barrel,
 * which shares a chunk with the components built on the library. Both are
 * gone from the lesson page's static imports; this keeps them gone.
 *
 * Read from source, as the route tests do: what matters is which modules the
 * page pulls in eagerly.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const PAGE = readFileSync(join(__dirname, "..", "pages", "Course", "ChapterView.tsx"), "utf8")
const staticImports = PAGE.split("\n").filter((line) => /^import\s/.test(line) && !/^import\s+type\s/.test(line))

describe("the lesson page's eager imports", () => {
  it("do not include the animation library or the motion barrel", () => {
    const offending = staticImports.filter((l) => /from "motion|from "@\/components\/motion"/.test(l))
    expect(offending).toEqual([])
  })

  it("load the test component on demand, not up front", () => {
    expect(staticImports.some((l) => l.includes("@/components/quiz/QuizTaker"))).toBe(false)
    expect(PAGE).toMatch(/lazy\(\(\) => import\("@\/components\/quiz\/QuizTaker"\)\)/)
  })
})
