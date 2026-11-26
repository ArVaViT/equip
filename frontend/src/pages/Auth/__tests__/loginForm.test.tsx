import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import Login, { FORGOT_PASSWORD_AFTER } from "../Login"

/**
 * The sign-in screen, kept short.
 *
 * Most people here sign in with Google (54 of 73 accounts on 25.11.2026), so
 * the email form waits behind the «or continue with email» divider, and
 * «Forgot password?» appears only once a password has actually been missed a
 * few times. The «email me a link» button is gone from this screen: it did
 * what «Forgot password?» does, was pressed once in ninety days, and every
 * press spent the shared hourly email allowance.
 */

const login = vi.fn()
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ login: (...a: unknown[]) => login(...a), signInWithGoogle: vi.fn() }),
}))

vi.mock("@/context/useTheme", () => ({
  useTheme: () => ({ theme: "light" as const, toggleTheme: vi.fn() }),
}))

function renderLogin(state?: unknown) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[{ pathname: "/login", state }]}>{children}</MemoryRouter>
    </I18nextProvider>
  )
  return render(<Login />, { wrapper: Wrapper })
}

const wrongPassword = () =>
  Object.assign(new Error("Invalid login credentials"), { code: "invalid_credentials", status: 400 })

async function submitWrong(user: ReturnType<typeof userEvent.setup>, times: number) {
  await user.type(screen.getByLabelText(i18n.t("auth.email")), "reader@example.com")
  const password = screen.getByLabelText(i18n.t("auth.password"), { selector: "input" })
  for (let i = 0; i < times; i++) {
    await user.clear(password)
    await user.type(password, `guess-${i}`)
    await user.click(screen.getByRole("button", { name: i18n.t("auth.signIn") }))
    await screen.findByRole("alert")
  }
}

describe("the sign-in screen", () => {
  beforeEach(async () => {
    login.mockReset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    await i18n.changeLanguage("en")
  })

  it("shows Google and the divider, not the email fields", () => {
    renderLogin()
    expect(screen.getByRole("button", { name: /google/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: i18n.t("auth.orContinueWithEmail") })).toHaveAttribute(
      "aria-expanded",
      "false",
    )
    expect(screen.queryByLabelText(i18n.t("auth.email"))).toBeNull()
    expect(screen.queryByLabelText(i18n.t("auth.password"), { selector: "input" })).toBeNull()
  })

  it("opens the email form from the divider and puts the cursor in it", async () => {
    const user = userEvent.setup()
    renderLogin()
    await user.click(screen.getByRole("button", { name: i18n.t("auth.orContinueWithEmail") }))

    expect(screen.getByLabelText(i18n.t("auth.email"))).toHaveFocus()
    expect(screen.getByLabelText(i18n.t("auth.password"), { selector: "input" })).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: i18n.t("auth.signIn") })).toHaveLength(1)
  })

  it("starts open when there is an invited address to finish", () => {
    renderLogin({ email: "sasha@web.de" })
    expect(screen.getByLabelText(i18n.t("auth.email"))).toHaveValue("sasha@web.de")
    expect(screen.getByLabelText(i18n.t("auth.password"), { selector: "input" })).toHaveFocus()
  })

  it("starts open on a device that signed in with a password before", async () => {
    const user = userEvent.setup()
    login.mockResolvedValueOnce(undefined)
    const first = renderLogin()
    await user.click(screen.getByRole("button", { name: i18n.t("auth.orContinueWithEmail") }))
    await submitRight(user)
    first.unmount()

    renderLogin()
    expect(screen.getByLabelText(i18n.t("auth.email"))).toBeInTheDocument()
  })

  it("offers no emailed sign-in link", async () => {
    const user = userEvent.setup()
    renderLogin()
    await user.click(screen.getByRole("button", { name: i18n.t("auth.orContinueWithEmail") }))
    expect(screen.queryByRole("button", { name: /link/i })).toBeNull()
  })

  it(`offers «Forgot password?» only after ${FORGOT_PASSWORD_AFTER} wrong passwords`, async () => {
    const user = userEvent.setup()
    login.mockRejectedValue(wrongPassword())
    renderLogin()
    await user.click(screen.getByRole("button", { name: i18n.t("auth.orContinueWithEmail") }))

    await submitWrong(user, FORGOT_PASSWORD_AFTER - 1)
    expect(screen.queryByRole("link", { name: i18n.t("auth.forgotPasswordLink") })).toBeNull()

    await user.click(screen.getByRole("button", { name: i18n.t("auth.signIn") }))
    expect(await screen.findByRole("link", { name: i18n.t("auth.forgotPasswordLink") })).toHaveAttribute(
      "href",
      "/forgot-password",
    )
  })

  it("does not count failures that are not a wrong password", async () => {
    const user = userEvent.setup()
    login.mockRejectedValue(Object.assign(new Error("Too many"), { code: "over_request_rate_limit", status: 429 }))
    renderLogin()
    await user.click(screen.getByRole("button", { name: i18n.t("auth.orContinueWithEmail") }))

    await submitWrong(user, FORGOT_PASSWORD_AFTER)
    expect(screen.queryByRole("link", { name: i18n.t("auth.forgotPasswordLink") })).toBeNull()
  })
})

async function submitRight(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(i18n.t("auth.email")), "reader@example.com")
  await user.type(screen.getByLabelText(i18n.t("auth.password"), { selector: "input" }), "right-one")
  await user.click(screen.getByRole("button", { name: i18n.t("auth.signIn") }))
  await vi.waitFor(() => expect(login).toHaveBeenCalled())
}
