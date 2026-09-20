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

  it("shows exactly one claim at a time", () => {
    renderLanding()
    // The three claims used to share a grid cell and cross-fade by opacity.
    // The ranges never overlap on paper; on a real wheel they do, because a
    // fast scroll jumps straight past the handover and paints two full
    // paragraphs on top of each other. Only the active one is mounted now,
    // so collision is not a thing that can happen at any scroll speed.
    const claimTitles = [
      i18n.t("landing.value.structure.title"),
      i18n.t("landing.value.assessment.title"),
      i18n.t("landing.value.certificates.title"),
    ]
    const shown = claimTitles.filter((title) => screen.queryByText(title) !== null)

    expect(shown).toEqual([claimTitles[0]])
  })

  it("offers the film behind a poster, and never starts it by itself", () => {
    renderLanding()
    const videos = [...document.querySelectorAll("video")]
    const film = videos.find((v) => v.hasAttribute("controls"))

    // A minute of speech: it waits, it is asked for, and it can be paused.
    expect(film).toBeDefined()
    expect(film?.getAttribute("poster")).toBeTruthy()
    expect(film?.hasAttribute("autoplay")).toBe(false)
    expect(film?.getAttribute("preload")).toBe("none")
  })

  it("plays the silent tour by itself, and only silently", () => {
    renderLanding()
    const videos = [...document.querySelectorAll("video")]
    const tour = videos.find((v) => !v.hasAttribute("controls"))

    // The opposite contract to the film: it is a caption that moves, so it
    // loops on its own — which every browser allows only while muted, and
    // which would be an ambush with sound.
    expect(tour).toBeDefined()
    expect(tour?.muted || tour?.hasAttribute("muted")).toBe(true)
    expect(tour?.hasAttribute("loop")).toBe(true)
    expect(tour?.hasAttribute("controls")).toBe(false)
  })

  it("does not render a generic 'reset password' marketing card", () => {
    renderLanding()
    expect(screen.queryByText(/восстановить пароль|reset password/i)).not.toBeInTheDocument()
  })
})
