import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import Footer from "../Footer"

// Footer reads ``useAuth()`` for the brand link surface but doesn't
// branch on the user — we still pass the provider so the hook tree
// resolves. Stubbed minimally to keep this a pure render test.
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: null, loading: false }),
}))

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("Footer (minimalist)", () => {
  it("renders the brand mark and tagline", () => {
    render(<Footer />, { wrapper: Wrapper })
    const links = screen.getAllByRole("link", { name: /equip/i })
    expect(links.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/biblical|biblical teaching|Писани/i)).toBeInTheDocument()
  })

  it("renders a support mailto link", () => {
    render(<Footer />, { wrapper: Wrapper })
    const support = screen.getByRole("link", { name: /support|поддерж/i })
    expect(support).toHaveAttribute("href", expect.stringMatching(/^mailto:/))
  })

  it("never links a signed-out visitor at a gated route", () => {
    render(<Footer />, { wrapper: Wrapper })
    // This assertion started life as "do not duplicate the header nav", back
    // when the footer sat in the application shell. The footer now renders
    // only on the public landing page, so duplication is no longer the
    // problem — but the reason the original was right turns out to be
    // sharper: `/calendar` and `/certificates` are behind
    // `Gate mode="private"`, and a stranger reading the marketing page who
    // clicks one lands on a login wall with no explanation.
    expect(screen.queryByRole("link", { name: /^calendar$|^календарь$/i })).toBeNull()
    expect(screen.queryByRole("link", { name: /^certificates$|^сертификат/i })).toBeNull()
    // Everything that *is* here has to be reachable without an account.
    const PUBLIC = ["/", "/courses", "/login", "/register", "/privacy", "/terms"]
    for (const link of screen.getAllByRole("link")) {
      const href = link.getAttribute("href")
      if (!href || href.startsWith("mailto:")) continue
      expect(PUBLIC, `footer links at gated route ${href}`).toContain(href)
    }
  })
})
