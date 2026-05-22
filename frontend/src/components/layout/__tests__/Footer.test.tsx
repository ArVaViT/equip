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

  it("does NOT duplicate the header nav inside the footer", () => {
    render(<Footer />, { wrapper: Wrapper })
    // Older revisions duplicated Courses / Calendar / Certificates /
    // Teacher / Admin in the footer. The minimalist rewrite drops them
    // — if a future edit re-adds them, this assertion will catch it.
    expect(screen.queryByRole("link", { name: /^calendar$|^календарь$/i })).toBeNull()
    expect(screen.queryByRole("link", { name: /^certificates$|^сертификат/i })).toBeNull()
  })
})
