/**
 * Which screen an address opens.
 *
 * A lesson now has two addresses: the course-shaped one it always has, and
 * the module-shaped one that was the only one until modules became optional.
 * The second must keep working — it is in bookmarks, in e-mail, and in the
 * links the readiness checklist prints — so both are asserted here, against
 * the real route table read out of `App.tsx` rather than a copy of it.
 *
 * Reading the file (as `usePageTitle`'s guard does) instead of rendering the
 * app: every one of these screens is a lazy chunk behind an auth gate, and
 * what is in question is the router's own resolution, not the screens.
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"
import { matchRoutes } from "react-router-dom"
import { describe, expect, it } from "vitest"

const APP = readFileSync(join(__dirname, "..", "App.tsx"), "utf8")

/**
 * The application's route table.
 *
 * App.tsx holds two: a small one for the signed-out auth pages, whose
 * catch-all bounces to the login screen, and this one — everything a
 * signed-in reader can reach. Taking the last `<Routes>` block keeps the
 * auth table's catch-all from answering for addresses it never sees.
 */
const MAIN_ROUTES = APP.slice(APP.lastIndexOf("<Routes>"), APP.lastIndexOf("</Routes>"))

/** `<Route path="/x" element={<Gate…><Screen /></Gate>} />` → `{path, screen}`. */
function routeTable(): { path: string; id: string }[] {
  const routes = Array.from(
    MAIN_ROUTES.matchAll(/<Route\s+path="([^"]+)"\s+element=\{(.+?)\}\s*\/>/g),
    (m) => {
      const components = Array.from(m[2]!.matchAll(/<([A-Z][A-Za-z0-9]*)/g), (c) => c[1]!)
      // The gate wraps the screen; the screen is what we are naming.
      const screen = components.filter((name) => name !== "Gate").pop()
      return { path: m[1]!, id: screen ?? "?" }
    },
  )
  // A guard on the guard: a route table that failed to parse would make
  // every assertion below vacuous.
  expect(routes.length).toBeGreaterThan(20)
  return routes
}

const TABLE = routeTable()

/** The screen an address opens, and the params it carries. */
function resolve(pathname: string): { screen: string; params: Record<string, string | undefined> } {
  const matched = matchRoutes(TABLE, pathname)
  const last = matched?.[matched.length - 1]
  return { screen: last?.route.id ?? "unmatched", params: last?.params ?? {} }
}

describe("a lesson's address", () => {
  it("opens the lesson from its course alone", () => {
    const { screen, params } = resolve("/courses/c-1/chapters/ch-1")
    expect(screen).toBe("ChapterView")
    expect(params).toEqual({ courseId: "c-1", chapterId: "ch-1" })
  })

  it("still opens the same screen through the module that groups it", () => {
    const { screen, params } = resolve("/courses/c-1/modules/m-1/chapters/ch-1")
    expect(screen).toBe("ChapterView")
    expect(params).toEqual({ courseId: "c-1", moduleId: "m-1", chapterId: "ch-1" })
  })

  it("opens the editor from the course alone", () => {
    const { screen, params } = resolve("/teacher/courses/c-1/chapters/ch-1/edit")
    expect(screen).toBe("ChapterEditor")
    expect(params).toEqual({ courseId: "c-1", chapterId: "ch-1" })
  })

  it("still opens the editor through the module", () => {
    const { screen, params } = resolve("/teacher/courses/c-1/modules/m-1/chapters/ch-1/edit")
    expect(screen).toBe("ChapterEditor")
    expect(params).toEqual({ courseId: "c-1", moduleId: "m-1", chapterId: "ch-1" })
  })
})

describe("the addresses around it", () => {
  it("still open what they always did", () => {
    // The new patterns sit next to `/courses/:id` and
    // `/teacher/courses/:courseId`, and must not swallow them.
    expect(resolve("/courses/c-1").screen).toBe("CourseDetail")
    expect(resolve("/courses/c-1/modules/m-1").screen).toBe("ModuleView")
    expect(resolve("/teacher/courses/c-1").screen).toBe("CourseEditor")
    expect(resolve("/teacher/courses/c-1/modules/m-1/edit").screen).toBe("ModuleEditor")
    expect(resolve("/teacher/courses/c-1/gradebook").screen).toBe("TeacherGradebook")
  })

  it("leave a made-up address to the 404", () => {
    expect(resolve("/courses/c-1/chapters").screen).toBe("NotFound")
    expect(resolve("/no-such-page").screen).toBe("NotFound")
  })
})
