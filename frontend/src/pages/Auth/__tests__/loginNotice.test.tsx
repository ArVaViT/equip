import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { rememberSignOutReason } from "@/lib/signOutReason"
import Login from "../Login"

/**
 * Why the sign-in form is on screen.
 *
 * Four arrivals used to render the same blank form: a session that expired
 * mid-work, an account the server switched off, `/auth/confirm` giving up
 * after fifteen seconds and sending `?error=oauth_timeout` (which nothing
 * read), and a guest refused a private page. The person was left to guess
 * what had happened to them.
 */

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ login: vi.fn(), signInWithGoogle: vi.fn(), sendSignInLink: vi.fn() }),
}))

vi.mock("@/context/useTheme", () => ({
  useTheme: () => ({ theme: "light" as const, toggleTheme: vi.fn() }),
}))

function renderAt(entry: string | { pathname: string; state: unknown }) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[entry]}>{children}</MemoryRouter>
    </I18nextProvider>
  )
  return render(<Login />, { wrapper: Wrapper })
}

describe("the sign-in form explains itself", () => {
  beforeEach(async () => {
    window.sessionStorage.clear()
    await i18n.changeLanguage("ru")
  })

  it("says nothing when the person simply came to sign in", () => {
    renderAt("/login")
    expect(screen.queryByRole("status")).toBeNull()
  })

  it("says the session expired when api.ts signed the person out", () => {
    rememberSignOutReason("session_expired")
    renderAt("/login")
    expect(screen.getByRole("status")).toHaveTextContent(i18n.t("auth.notice.sessionExpired"))
  })

  it("says the account is deactivated when that is what the server said", () => {
    rememberSignOutReason("account_deactivated")
    renderAt("/login")
    expect(screen.getByRole("status")).toHaveTextContent(i18n.t("auth.notice.accountDeactivated"))
  })

  it("reads the error /auth/confirm sends it, instead of a blank form", () => {
    renderAt("/login?error=oauth_timeout")
    expect(screen.getByRole("status")).toHaveTextContent(i18n.t("auth.callback.timedOut"))
  })

  it("tells a guest refused a private page why they are here", () => {
    renderAt({ pathname: "/login", state: { from: "/courses/abc" } })
    expect(screen.getByRole("status")).toHaveTextContent(i18n.t("auth.notice.signInToContinue"))
  })

  it("speaks the reader's language", async () => {
    await i18n.changeLanguage("de")
    rememberSignOutReason("session_expired")
    renderAt("/login")
    expect(screen.getByRole("status")).toHaveTextContent("Sitzung ist abgelaufen")
  })
})
