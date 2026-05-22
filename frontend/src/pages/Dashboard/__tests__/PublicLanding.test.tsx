import { render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { PublicLanding } from "@/pages/Dashboard/PublicLanding"

/**
 * The marketing landing exists for two audiences:
 *
 *   1. First-time human visitors (activation funnel).
 *   2. Search-engine crawlers (Googlebot needs real ``<a href>`` links
 *      to discover /courses, /register, /login, /forgot-password and
 *      to feed the sitelinks heuristic).
 *
 * These tests lock in the *crawler-visible* contract: the page must
 * render an <h1> with the brand name and real anchor elements to
 * every key internal destination. Refactoring a Link into a
 * button + ``navigate()`` would pass typecheck but silently strip
 * the page of its SEO surface — these tests fail loudly when that
 * happens.
 */

function renderLanding() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <PublicLanding />
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("PublicLanding (unauth marketing page)", () => {
  it("renders the brand name as the page h1", () => {
    renderLanding()
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/equip/i)
  })

  it("exposes every key internal destination as a real <a href>", () => {
    const { container } = renderLanding()
    const hrefs = Array.from(container.querySelectorAll<HTMLAnchorElement>("a[href]")).map(
      (a) => a.getAttribute("href"),
    )
    // Each destination must appear at least once. Multiple matches per
    // path are expected (hero + quick-links + final-CTA all link to
    // /courses + /register), so we use ``toContain`` not equality.
    expect(hrefs).toContain("/courses")
    expect(hrefs).toContain("/register")
    expect(hrefs).toContain("/login")
    expect(hrefs).toContain("/forgot-password")
  })

  it("renders the 'Quick links' section as a semantic <ul>", () => {
    renderLanding()
    // The section labels itself via ``aria-labelledby`` pointing at the
    // heading id, so the region is queryable by name. Inside, every
    // quick-link is an <li> — keeping that semantic shape matters for
    // crawler comprehension + screen-reader navigation.
    const heading = screen.getByRole("heading", { level: 2, name: /куда дальше|where to next/i })
    const section = heading.closest("section")
    expect(section).not.toBeNull()
    const list = within(section!).getByRole("list")
    expect(within(list).getAllByRole("listitem").length).toBeGreaterThanOrEqual(4)
  })
})
