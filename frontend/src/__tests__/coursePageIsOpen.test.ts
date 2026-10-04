/**
 * The landing FAQ, in all four languages, promises that "the catalogue and
 * every course page are open to anyone". Until 2026-09-30 the course page
 * sent a visitor to the login screen: a person following a pastor's link
 * could not see even the description. The page has always had a signed-out
 * path (NotEnrolledView asks to sign in to enrol); only the route was shut.
 *
 * Read from `App.tsx` rather than rendered, as `chapterRoutes.test.ts` does:
 * what is in question is which gate the router puts in front of the screen.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const APP = readFileSync(join(__dirname, "..", "App.tsx"), "utf8")

/** `path` as a literal inside a RegExp: every metacharacter escaped, the backslash too. */
function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")
}

function elementFor(path: string): string {
  const m = APP.match(new RegExp(`<Route\\s+path="${escapeRegExp(path)}"\\s+element=\\{(.+?)\\}\\s*/>`))
  if (!m) throw new Error(`no route ${path}`)
  return m[1]!
}

describe("who may open a course page", () => {
  it("anyone may read the course page", () => {
    expect(elementFor("/courses/:id")).not.toContain("<Gate")
  })

  it("a lesson is open, and decides itself what a guest may read", () => {
    // The first lesson is a guest's (guest_preview); every other one shows
    // an invitation, and the server answers 401 for it.
    expect(elementFor("/courses/:courseId/chapters/:chapterId")).toContain('<Gate mode="open">')
    expect(elementFor("/courses/:courseId/modules/:moduleId/chapters/:chapterId")).toContain('<Gate mode="open">')
  })

  it("a module page still needs an account", () => {
    expect(elementFor("/courses/:courseId/modules/:moduleId")).toContain('<Gate mode="private">')
  })
})
