import { render, screen } from "@testing-library/react"
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
 *      to discover /courses, /register, /login and to feed the
 *      sitelinks heuristic).
 *
 * These tests lock in the *crawler-visible* contract: the page must
 * render an <h1> with the brand name and real anchor elements to the
 * key internal destinations. Refactoring a Link into a button +
 * ``navigate()`` would pass typecheck but silently strip the page of
 * its SEO surface — these tests fail loudly when that happens.
 *
 * Note: /forgot-password is deliberately NOT asserted here. The old
 * design gave it its own "Reset password" landing-page card purely to
 * keep it crawler-visible — that card was flagged as generic
 * template-filler (Vadym: literally a reset-password feature card on
 * the marketing page) and removed in the 2026-07 rebuild. It's still
 * one click away from /login, which is the correct place for it.
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
  it("spends the h1 on the claim, not on the brand name", () => {
    // The name is already in the header, the <title> and the footer.
    // Repeating it in the largest type on the page tells a visitor deciding
    // whether this is for them precisely nothing.
    renderLanding()
    const h1 = screen.getByRole("heading", { level: 1 })
    expect(h1).toHaveTextContent(i18n.t("landing.hero.manifesto"))
  })

  it("still names the product somewhere on the page", () => {
    // Dropping it from the h1 must not drop it from the page: the footer
    // carries it, and a visitor has to be able to learn what this is called.
    const { container } = renderLanding()
    expect(container.textContent).toMatch(/equip/i)
  })

  it("states the facts once, quietly, instead of in three badges", () => {
    renderLanding()
    expect(screen.getByText(i18n.t("landing.hero.facts"))).toBeInTheDocument()
  })

  it("exposes the key internal destinations as real <a href>", () => {
    const { container } = renderLanding()
    const hrefs = Array.from(container.querySelectorAll<HTMLAnchorElement>("a[href]")).map(
      (a) => a.getAttribute("href"),
    )
    // Each destination must appear at least once. Multiple matches per
    // path are expected (hero + final-CTA both link to /courses +
    // /register), so we use ``toContain`` not equality.
    expect(hrefs).toContain("/courses")
    expect(hrefs).toContain("/register")
    expect(hrefs).toContain("/login")
  })

  it("renders the four value-proposition rows as h3 headings", () => {
    renderLanding()
    // Each row is a concrete claim (structure / assessment /
    // certificates / bilingual), not a generic icon+adjective grid.
    const h3s = screen.getAllByRole("heading", { level: 3 })
    expect(h3s.length).toBe(4)
  })

  it("does not render a generic 'reset password' marketing card", () => {
    renderLanding()
    expect(screen.queryByText(/восстановить пароль|reset password/i)).not.toBeInTheDocument()
  })
})
