import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { User } from "@/types"

const setEmailKind = vi.fn()
vi.mock("@/services/users", () => ({ usersService: { setEmailKind: (...a: unknown[]) => setEmailKind(...a) } }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

const applyUser = vi.fn()
let currentUser: User
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: currentUser, applyUser }) }))

import { EmailSetting } from "../EmailSetting"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

/**
 * The privacy policy promises every kind of course mail can be turned off in
 * the profile. The switch writes the person's own list of kinds turned off.
 */
describe("EmailSetting", () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage("ru")
    currentUser = { id: "u1", email: "s@example.com", role: "student", email_off: [] } as unknown as User
  })

  const box = () => screen.getByRole("checkbox", { name: i18n.t("profile.emails.kinds.work_returned") })

  it("is on until the person turns it off", async () => {
    setEmailKind.mockResolvedValue(["work_returned"])
    render(<EmailSetting />, { wrapper: Wrapper })
    expect(box()).toHaveAttribute("data-state", "checked")
    await userEvent.click(box())
    await waitFor(() => expect(setEmailKind).toHaveBeenCalledWith("work_returned", false))
    expect(applyUser).toHaveBeenCalledWith({ id: "u1", email_off: ["work_returned"] })
  })

  it("turns back on, and shows what the server now holds", async () => {
    currentUser = { ...currentUser, email_off: ["announcement", "work_returned"] } as User
    setEmailKind.mockResolvedValue(["announcement"])
    render(<EmailSetting />, { wrapper: Wrapper })
    expect(box()).toHaveAttribute("data-state", "unchecked")
    await userEvent.click(box())
    await waitFor(() => expect(setEmailKind).toHaveBeenCalledWith("work_returned", true))
    expect(applyUser).toHaveBeenCalledWith({ id: "u1", email_off: ["announcement"] })
  })
})
