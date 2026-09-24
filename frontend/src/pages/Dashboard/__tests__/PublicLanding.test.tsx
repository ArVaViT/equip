import { readFileSync } from "node:fs"
import { resolve } from "node:path"

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

  it("still names the product, in the document title", () => {
    // Dropping the name from the h1 must not drop it from the page. The
    // footer used to carry it; since 2026-09-23 the footer is one line of
    // legal links with no wordmark («без названия»), so the name lives in
    // the header — which this component does not render — and in the
    // static `<title>`, which is what a crawler and a browser tab read.
    const html = readFileSync(resolve(__dirname, "../../../../index.html"), "utf8")
    expect(html).toMatch(/<title>[^<]*Equip[^<]*<\/title>/)
  })

  it("offers two actions in the hero: browse, and sign back in", () => {
    // claude.com's shape — the thing to do, and the way back for somebody
    // who already has an account. The facts line and the «Create account ·
    // Sign In» pair under the button were removed on 2026-09-23 as
    // «лишний кусок»; registering lives in the header and at the close.
    renderLanding()
    const hero = screen.getByRole("region", { name: i18n.t("landing.hero.manifesto") })
    const hrefs = Array.from(hero.querySelectorAll("a[href]")).map((a) => a.getAttribute("href"))
    expect(hrefs).toEqual(["/courses", "/login"])
    expect(screen.queryByText(i18n.t("landing.hero.facts"))).not.toBeInTheDocument()
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

  it("makes all three claims where there is no pinned scene", () => {
    renderLanding()
    // jsdom has no `matchMedia`, so the page renders its narrow layout —
    // the same one a phone gets. There the claims are an ordinary column
    // and all three are present at once.
    //
    // Cross-fading one at a time is a property of the *pinned* layout,
    // where each claim captions the stretch of the backdrop it belongs to.
    // Below `lg` there is no backdrop and so no stage: the sticky track was
    // three screens of scrolling with one short sentence floating in the
    // middle of each empty one.
    for (const key of [
      "landing.value.structure.title",
      "landing.value.assessment.title",
      "landing.value.certificates.title",
    ]) {
      expect(screen.getByText(i18n.t(key))).toBeInTheDocument()
    }
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
