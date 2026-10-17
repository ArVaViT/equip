/**
 * Signing in to a deleted account offers exactly two things: restore it, or
 * sign out. Restoring is by a link emailed to the account's address: a
 * password or Google session that presses «Restore» gets the link sent.
 */
import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { AxiosError, AxiosHeaders } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { getAccountDeleted, publishAccountDeleted, rememberRestoreRequested, wasRestoreRequested } from "@/lib/accountDeleted"

const restoreMyAccount = vi.fn()
vi.mock("@/services/users", () => ({
  usersService: { restoreMyAccount: (...a: unknown[]) => restoreMyAccount(...a) },
}))
const sendSignInLink = vi.fn()
vi.mock("@/services/auth", () => ({
  authService: { sendSignInLink: (...a: unknown[]) => sendSignInLink(...a) },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
const logout = vi.fn()
const refreshUser = vi.fn()
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({
    user: { id: "u1", email: "sasha@web.de", deleted_at: "2026-10-16T12:00:00Z" },
    logout,
    refreshUser,
  }),
}))
const navigate = vi.fn()
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}))

import { AccountDeletedScreen } from "../AccountDeletedScreen"

function needsEmailLink() {
  const headers = new AxiosHeaders()
  return new AxiosError("403", "ERR_BAD_REQUEST", undefined, undefined, {
    status: 403,
    statusText: "Forbidden",
    headers,
    config: { headers },
    data: { detail: { code: "account.restore_needs_email_link", message: "", context: {} } },
  })
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("AccountDeletedScreen", () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    localStorage.clear()
    publishAccountDeleted(true)
    await i18n.changeLanguage("en")
  })

  it("restores the account and goes home", async () => {
    restoreMyAccount.mockResolvedValue(undefined)
    render(<AccountDeletedScreen />, { wrapper: Wrapper })
    expect(screen.getByRole("heading", { name: "This account has been deleted" })).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: "Restore account" }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/", { replace: true }))
    expect(refreshUser).toHaveBeenCalled()
    expect(getAccountDeleted()).toBe(false)
    expect(logout).not.toHaveBeenCalled()
  })

  it("a password or Google session gets the link sent, not a restore", async () => {
    restoreMyAccount.mockRejectedValue(needsEmailLink())
    sendSignInLink.mockResolvedValue(undefined)
    render(<AccountDeletedScreen />, { wrapper: Wrapper })

    await userEvent.click(screen.getByRole("button", { name: "Restore account" }))

    await waitFor(() => expect(sendSignInLink).toHaveBeenCalledWith("sasha@web.de"))
    expect(await screen.findByRole("status")).toHaveTextContent("sasha@web.de")
    expect(screen.getByRole("status")).toHaveTextContent("spam")
    expect(navigate).not.toHaveBeenCalled()
    expect(logout).not.toHaveBeenCalled()
    expect(getAccountDeleted()).toBe(true)
    expect(wasRestoreRequested("u1")).toBe(true)
    // The repeat waits for the hook's window instead of being refused by it.
    expect(screen.getByRole("button", { name: /Send it again in/ })).toBeDisabled()
  })

  it("a link already on its way says so and points at the spam folder", async () => {
    restoreMyAccount.mockRejectedValue(needsEmailLink())
    sendSignInLink.mockRejectedValue(
      Object.assign(new Error("For security purposes, you can only request this after 80 seconds."), {
        status: 429,
        code: "unknown",
      }),
    )
    render(<AccountDeletedScreen />, { wrapper: Wrapper })
    await userEvent.click(screen.getByRole("button", { name: "Restore account" }))

    expect(await screen.findByRole("status")).toHaveTextContent(/spam/i)
    expect(screen.getByRole("status")).not.toHaveTextContent(/wrong on our side/i)
  })

  it("arriving from the link asked for in this browser restores by itself", async () => {
    rememberRestoreRequested("u1")
    restoreMyAccount.mockResolvedValue(undefined)
    render(<AccountDeletedScreen />, { wrapper: Wrapper })

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/", { replace: true }))
    expect(restoreMyAccount).toHaveBeenCalledTimes(1)
    expect(sendSignInLink).not.toHaveBeenCalled()
    expect(wasRestoreRequested("u1")).toBe(false)
  })

  it("the automatic attempt never mails anything by itself", async () => {
    rememberRestoreRequested("u1")
    restoreMyAccount.mockRejectedValue(needsEmailLink())
    render(<AccountDeletedScreen />, { wrapper: Wrapper })

    await waitFor(() => expect(restoreMyAccount).toHaveBeenCalledTimes(1))
    expect(sendSignInLink).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it("a link opened on another device is noticed when the person comes back to this tab", async () => {
    restoreMyAccount.mockRejectedValueOnce(needsEmailLink())
    sendSignInLink.mockResolvedValue(undefined)
    render(<AccountDeletedScreen />, { wrapper: Wrapper })
    await userEvent.click(screen.getByRole("button", { name: "Restore account" }))
    await screen.findByRole("status")

    // Restored on the phone: the server now answers 204 to this tab too.
    restoreMyAccount.mockResolvedValue(undefined)
    document.dispatchEvent(new Event("visibilitychange"))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/", { replace: true }))
    expect(getAccountDeleted()).toBe(false)
  })

  it("can be left deleted", async () => {
    render(<AccountDeletedScreen />, { wrapper: Wrapper })
    await userEvent.click(screen.getByRole("button", { name: i18n.t("common.signOut") }))
    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1))
    expect(restoreMyAccount).not.toHaveBeenCalled()
  })
})
