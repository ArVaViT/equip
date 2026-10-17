/**
 * Signing in to a deleted account offers exactly two things: restore it, or
 * sign out. A session older than the deletion is sent to sign in again.
 */
import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { AxiosError, AxiosHeaders } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { getAccountDeleted, publishAccountDeleted } from "@/lib/accountDeleted"
import { takeSignOutReason } from "@/lib/signOutReason"

const restoreMyAccount = vi.fn()
vi.mock("@/services/users", () => ({
  usersService: { restoreMyAccount: (...a: unknown[]) => restoreMyAccount(...a) },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
const logout = vi.fn()
const refreshUser = vi.fn()
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: { id: "u1", deleted_at: "2026-10-16T12:00:00Z" }, logout, refreshUser }),
}))
const navigate = vi.fn()
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}))

import { AccountDeletedScreen } from "../AccountDeletedScreen"

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
    takeSignOutReason()
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

  it("sends a stale session to sign in again instead of pretending", async () => {
    const headers = new AxiosHeaders()
    restoreMyAccount.mockRejectedValue(
      new AxiosError("403", "ERR_BAD_REQUEST", undefined, undefined, {
        status: 403,
        statusText: "Forbidden",
        headers,
        config: { headers },
        data: { detail: { code: "account.restore_needs_sign_in", message: "", context: {} } },
      }),
    )
    render(<AccountDeletedScreen />, { wrapper: Wrapper })

    await userEvent.click(screen.getByRole("button", { name: "Restore account" }))

    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1))
    expect(navigate).toHaveBeenCalledWith("/login", { replace: true })
    expect(takeSignOutReason()).toBe("restore_needs_sign_in")
  })

  it("can be left deleted", async () => {
    render(<AccountDeletedScreen />, { wrapper: Wrapper })
    await userEvent.click(screen.getByRole("button", { name: i18n.t("common.signOut") }))
    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1))
    expect(restoreMyAccount).not.toHaveBeenCalled()
  })
})
