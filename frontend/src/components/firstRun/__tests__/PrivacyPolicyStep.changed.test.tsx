/**
 * The document changed while the gate was open (a deploy). The version on
 * hand was stale, and retrying with it failed every time under «check your
 * connection» — the only ways out of a full-screen gate were a reload or
 * signing out.
 */
import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (o: unknown) => toast(o) }))
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ logout: vi.fn() }) }))

import i18n from "@/i18n/config"
import { legalService } from "@/services/legal"
import { PrivacyPolicyStep } from "../PrivacyPolicyStep"

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

const EVERYONE = ["student", "teacher", "director", "admin"]
const doc = (version: string) => ({ slug: "privacy", version, effective: "2026-10-01", required_for: EVERYONE, requires_consent: true })
const SCHOOL = { slug: "school-agreement", version: "1.0", effective: "2026-09-17", required_for: ["director"], requires_consent: true }

describe("PrivacyPolicyStep when the document changed under the gate", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
    toast.mockClear()
  })

  it("accepts the current version instead of failing on the stale one", async () => {
    const changed = Object.assign(new Error("Conflict"), {
      isAxiosError: true,
      response: { status: 409, data: { detail: { code: "legal.document_changed", message: "changed" } } },
    })
    const accept = vi.spyOn(legalService, "accept").mockRejectedValueOnce(changed).mockResolvedValue({} as never)
    vi.spyOn(legalService, "status").mockResolvedValue({ outstanding: [doc("2.0")] } as never)
    const onAccept = vi.fn()
    render(<PrivacyPolicyStep onAccept={onAccept} documents={[doc("1.0")]} />, { wrapper: Wrapper })

    await userEvent.click(screen.getByRole("checkbox"))
    await userEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.privacy.next") }))

    await waitFor(() => expect(onAccept).toHaveBeenCalledTimes(1))
    expect(accept).toHaveBeenNthCalledWith(1, "privacy", "1.0", "en")
    expect(accept).toHaveBeenNthCalledWith(2, "privacy", "2.0", "en")
    expect(toast).not.toHaveBeenCalled()
  })

  it("records only the documents its checkbox names, never a role-scoped one", async () => {
    // With no list handed over, the step asks the server itself — and for a
    // director the server lists the School Agreement too. Accepting that here
    // would record it under a sentence about the privacy policy and the terms.
    const accept = vi.spyOn(legalService, "accept").mockResolvedValue({} as never)
    vi.spyOn(legalService, "status").mockResolvedValue({ outstanding: [doc("2.0"), SCHOOL] } as never)
    const onAccept = vi.fn()
    render(<PrivacyPolicyStep onAccept={onAccept} />, { wrapper: Wrapper })

    await userEvent.click(screen.getByRole("checkbox"))
    await userEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.privacy.next") }))

    await waitFor(() => expect(onAccept).toHaveBeenCalledTimes(1))
    expect(accept).toHaveBeenCalledTimes(1)
    expect(accept).toHaveBeenCalledWith("privacy", "2.0", "en")
  })
})
