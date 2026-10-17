/**
 * "Delete account" asks once, in the words of what happens, and only then
 * deletes; afterwards the person is signed out and told how to come back.
 */
import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { AxiosError, AxiosHeaders } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { ConfirmProvider } from "@/components/ui/alert-dialog"
import { takeSignOutReason } from "@/lib/signOutReason"

const deleteMyAccount = vi.fn()
vi.mock("@/services/users", () => ({
  usersService: { deleteMyAccount: (...a: unknown[]) => deleteMyAccount(...a) },
}))
const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (...a: unknown[]) => toast(...a) }))
const logout = vi.fn()
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ logout }) }))
const navigate = vi.fn()
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}))

import { DeleteAccountSetting } from "../DeleteAccountSetting"

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <ConfirmProvider>{children}</ConfirmProvider>
      </MemoryRouter>
    </I18nextProvider>
  )
}

function refusal(reason: string): AxiosError {
  const headers = new AxiosHeaders()
  return new AxiosError("409", "ERR_BAD_REQUEST", undefined, undefined, {
    status: 409,
    statusText: "Conflict",
    headers,
    config: { headers },
    data: { detail: { code: "account.cannot_delete", message: "", context: { reason } } },
  })
}

describe("DeleteAccountSetting", () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    takeSignOutReason()
    await i18n.changeLanguage("ru")
  })

  it("deletes nothing until the person confirms", async () => {
    const user = userEvent.setup()
    render(<DeleteAccountSetting />, { wrapper: Wrapper })

    await user.click(screen.getByRole("button", { name: "Удалить аккаунт" }))
    const dialog = await screen.findByRole("alertdialog")
    // The dialog says what happens, including the way back.
    expect(dialog).toHaveTextContent("Ваши работы, оценки и сертификаты останутся у школы.")
    expect(dialog).toHaveTextContent("войдите снова")

    await user.click(screen.getByRole("button", { name: "Отмена" }))
    expect(deleteMyAccount).not.toHaveBeenCalled()
    expect(logout).not.toHaveBeenCalled()
  })

  it("on confirm deletes, signs out and leaves a reason for the sign-in page", async () => {
    const user = userEvent.setup()
    deleteMyAccount.mockResolvedValue(undefined)
    render(<DeleteAccountSetting />, { wrapper: Wrapper })

    await user.click(screen.getByRole("button", { name: "Удалить аккаунт" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(
      Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Удалить аккаунт")!,
    )

    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1))
    expect(deleteMyAccount).toHaveBeenCalledTimes(1)
    expect(navigate).toHaveBeenCalledWith("/login", { replace: true })
    expect(takeSignOutReason()).toBe("account_deleted")
  })

  it("explains, and stays signed in, when the only director tries to leave", async () => {
    const user = userEvent.setup()
    deleteMyAccount.mockRejectedValue(refusal("only_director"))
    render(<DeleteAccountSetting />, { wrapper: Wrapper })

    await user.click(screen.getByRole("button", { name: "Удалить аккаунт" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(
      Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Удалить аккаунт")!,
    )

    await waitFor(() => expect(toast).toHaveBeenCalledTimes(1))
    expect(toast.mock.calls[0]![0]).toMatchObject({ title: i18n.t("account.delete.onlyDirector") })
    expect(logout).not.toHaveBeenCalled()
  })
})
