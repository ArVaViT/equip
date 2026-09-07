import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import Login from "../Login"

/**
 * Signing in with a link, and the one thing it must never leak.
 *
 * The whole chain for this already existed: the send-email hook has carried
 * `magic_link` copy in four languages since it was written, and /auth/confirm
 * accepts any session GoTrue puts in the fragment. Nothing could ask for the
 * email, so none of it ran.
 *
 * The risk a link form brings with it is disclosure. If "no such user" looked
 * different from "sent", the sign-in page would be a way to check which
 * addresses are registered here — one request per address, no account needed.
 * So the confirmation is identical either way, and these tests hold that.
 */

const sendSignInLink = vi.fn()
const login = vi.fn()

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ login, signInWithGoogle: vi.fn(), sendSignInLink }),
}))

// AuthLayout reads the theme, and the real provider calls `matchMedia`, which
// jsdom does not have. The colour scheme has nothing to do with what is being
// tested here.
vi.mock("@/context/useTheme", () => ({
  useTheme: () => ({ theme: "light" as const, toggleTheme: vi.fn() }),
}))

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

async function askForALink(email = "reader@example.com") {
  const user = userEvent.setup()
  render(<Login />, { wrapper: Wrapper })
  await user.type(screen.getByLabelText(/email/i), email)
  await user.click(screen.getByRole("button", { name: /email me a link/i }))
  return user
}

describe("signing in with a link", () => {
  beforeEach(() => {
    sendSignInLink.mockReset()
    login.mockReset()
    i18n.changeLanguage("en")
  })

  it("asks the server for a link and confirms", async () => {
    sendSignInLink.mockResolvedValueOnce(undefined)
    await askForALink()

    await waitFor(() => expect(sendSignInLink).toHaveBeenCalledWith("reader@example.com"))
    expect(await screen.findByText(/on its way/i)).toBeInTheDocument()
  })

  it("says exactly the same thing when the address has no account", async () => {
    // GoTrue's answer with `shouldCreateUser: false` and no such user. If this
    // ever renders differently from the success above, the page has become an
    // address checker.
    sendSignInLink.mockRejectedValueOnce(
      Object.assign(new Error("Signups not allowed for otp"), { code: "otp_disabled", status: 422 }),
    )
    await askForALink("stranger@example.com")

    expect(await screen.findByText(/on its way/i)).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("does say when the server asked us to slow down", async () => {
    // The one outcome the reader can act on, by waiting.
    sendSignInLink.mockRejectedValueOnce(
      Object.assign(new Error("email rate limit exceeded"), { code: "over_email_send_rate_limit", status: 429 }),
    )
    await askForALink()

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many|minute/i)
    expect(screen.queryByText(/on its way/i)).not.toBeInTheDocument()
  })

  it("never sends without a valid address", async () => {
    const user = userEvent.setup()
    render(<Login />, { wrapper: Wrapper })
    await user.type(screen.getByLabelText(/email/i), "not-an-address")
    await user.click(screen.getByRole("button", { name: /email me a link/i }))

    expect(sendSignInLink).not.toHaveBeenCalled()
  })

  it("does not put a second «sign in» on the page", async () => {
    // Two buttons whose names both start with "sign in" broke the e2e suite
    // and would read the same way to a screen reader. This one says what it
    // does — an email arrives — rather than repeating the submit button.
    render(<Login />, { wrapper: Wrapper })
    expect(screen.getAllByRole("button", { name: /^sign in$/i })).toHaveLength(1)
  })

  it("offers the way back to the password", async () => {
    sendSignInLink.mockResolvedValueOnce(undefined)
    const user = await askForALink()

    const back = await screen.findByRole("button", { name: /password/i })
    await user.click(back)
    expect(screen.getByLabelText(/password|пароль/i)).toBeInTheDocument()
  })
})
