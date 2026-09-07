import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import ForgotPassword from "../ForgotPassword"

/**
 * What the reader is told when the reset email does not go out.
 *
 * This screen said one sentence for every failure: "could not send, try in a
 * minute". The common failure here is a 429 — the project's hourly email
 * allowance is small enough to reach — and the two call for different things
 * from the reader. A generic failure reads as "the product is broken"; the
 * real answer is "wait, then ask again".
 *
 * Found while checking the day's work: a reset email never arrived, and the
 * screen could not say why.
 */

const resetPassword = vi.fn()
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ resetPassword }) }))
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

async function ask() {
  const user = userEvent.setup()
  render(<ForgotPassword />, { wrapper: Wrapper })
  await user.type(screen.getByLabelText(/email/i), "reader@example.com")
  await user.click(screen.getByRole("button", { name: /send|link|отправить/i }))
}

describe("the reset-password screen", () => {
  beforeEach(() => {
    resetPassword.mockReset()
    i18n.changeLanguage("en")
  })

  it("tells the reader to wait when the server says too many", async () => {
    resetPassword.mockRejectedValueOnce(
      Object.assign(new Error("email rate limit exceeded"), {
        code: "over_email_send_rate_limit",
        status: 429,
      }),
    )

    await ask()

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many|minute/i)
  })

  it("still has something to say for an unrecognised failure", async () => {
    resetPassword.mockRejectedValueOnce(new Error("socket hang up"))

    await ask()

    const alert = await screen.findByRole("alert")
    expect(alert.textContent?.trim().length ?? 0).toBeGreaterThan(0)
    // Never the server's own words, on any screen.
    expect(alert).not.toHaveTextContent(/socket hang up/i)
  })

  it("confirms without saying whether the address is registered", async () => {
    resetPassword.mockResolvedValueOnce(undefined)

    await ask()

    expect(await screen.findByText(/if an account/i)).toBeInTheDocument()
  })
})
