import { readFileSync } from "node:fs"
import { join } from "node:path"
import { renderHook } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { matchTitleKey, usePageTitle } from "../usePageTitle"

/**
 * Every route the app can land on names itself in the tab strip.
 *
 * The title map is hand-maintained and had fallen behind the router:
 * /verify (added the same week), /invite/accept, /teach/grading, the Daily
 * Challenge archive, a single certificate, the grade sheet and the 404 all
 * fell through to a bare "Equip". In a tab strip they were
 * indistinguishable from each other; to a screen reader, arriving at any of
 * them announced nothing about where it had landed (WCAG 2.4.2).
 *
 * The guard reads the routes out of App.tsx rather than repeating them, so
 * a route added tomorrow without a title fails here rather than shipping
 * anonymous.
 */

const APP = readFileSync(join(__dirname, "..", "..", "App.tsx"), "utf8")

/** `path="/foo/:bar"` → `/foo/sample`, which is what the matcher sees. */
function concreteRoutes(): string[] {
  const paths = Array.from(APP.matchAll(/path="([^"]+)"/g), (m) => m[1]!)
  return paths
    .filter((p) => p !== "*")
    .map((p) => p.replace(/:[^/]+/g, "sample"))
}

describe("page titles", () => {
  it("cover every route in App.tsx", () => {
    const anonymous = concreteRoutes().filter((p) => {
      const key = matchTitleKey(p)
      // Unclaimed, or claimed with a key that never made it into the
      // catalogs — both render as a bare "Equip" to the reader.
      return key === null || i18n.t(key) === key
    })

    expect(
      anonymous,
      `These routes have no translated title and would render as a bare ` +
        `"Equip":\n  ${anonymous.join("\n  ")}`,
    ).toEqual([])
  })

  it("leaves an unknown path unclaimed, and the hook names it a 404", () => {
    expect(matchTitleKey("/no-such-page")).toBeNull()

    renderHook(() => usePageTitle(), {
      wrapper: ({ children }) => (
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={["/no-such-page"]}>{children}</MemoryRouter>
        </I18nextProvider>
      ),
    })

    expect(document.title).toBe(`${i18n.t("notFound.title")} — ${i18n.t("common.appName")}`)
  })

  it("keeps a route's own title when a longer route shares its prefix", () => {
    // /certificates/:id must not borrow the list page's rule by accident,
    // and /verify/:number must resolve like /verify.
    expect(matchTitleKey("/verify/ABC-123")).toBe("verify.title")
    expect(matchTitleKey("/teacher/courses/c-1/vedomost")).toBe("vedomost.title")
    expect(matchTitleKey("/teacher/courses/c-1/gradebook")).toBe("pageTitle.gradebook")
  })
})
