import { fireEvent, render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { emailService } from "@/services/email"
import UnsubscribePage from "../UnsubscribePage"

/**
 * The link at the foot of a course mail. It must ask before it acts: mail
 * scanners open every link, and a page that unsubscribed on load would turn
 * people's mail off for them.
 */
function renderAt(url: string) {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/unsubscribe" element={<UnsubscribePage />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("UnsubscribePage", () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await i18n.changeLanguage("ru")
  })

  it("opening the link turns nothing off; pressing the button does", async () => {
    const read = vi.spyOn(emailService, "readUnsubscribe").mockResolvedValue({ kind: "work_returned", off: false })
    const act = vi.spyOn(emailService, "unsubscribe").mockResolvedValue({ kind: "work_returned", off: true })
    renderAt("/unsubscribe?token=t1")
    const button = await screen.findByRole("button", { name: i18n.t("unsubscribe.button") })
    expect(read).toHaveBeenCalledWith("t1")
    expect(act).not.toHaveBeenCalled()
    fireEvent.click(button)
    expect(
      await screen.findByText(i18n.t("unsubscribe.done", { kind: i18n.t("profile.emails.kinds.work_returned") })),
    ).toBeInTheDocument()
    expect(act).toHaveBeenCalledWith("t1")
  })

  it("says so when the kind is already off", async () => {
    vi.spyOn(emailService, "readUnsubscribe").mockResolvedValue({ kind: "work_returned", off: true })
    renderAt("/unsubscribe?token=t1")
    const kind = i18n.t("profile.emails.kinds.work_returned")
    expect(await screen.findByText(i18n.t("unsubscribe.done", { kind }))).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: i18n.t("unsubscribe.button") })).toBeNull()
  })

  it("explains a broken link instead of failing silently", async () => {
    // The server's own refusal — a plain network failure is no longer a broken link.
    vi.spyOn(emailService, "readUnsubscribe").mockRejectedValue(
      Object.assign(new Error("400"), { isAxiosError: true, response: { status: 400, data: {} } }),
    )
    renderAt("/unsubscribe?token=bad")
    expect(await screen.findByText(i18n.t("unsubscribe.invalid"))).toBeInTheDocument()
  })

  it("a link with no token is broken, without asking the server", async () => {
    const read = vi.spyOn(emailService, "readUnsubscribe")
    renderAt("/unsubscribe")
    expect(await screen.findByText(i18n.t("unsubscribe.invalid"))).toBeInTheDocument()
    expect(read).not.toHaveBeenCalled()
  })

  it("does not call a link broken when the server could not be reached, and asks again", async () => {
    const read = vi
      .spyOn(emailService, "readUnsubscribe")
      .mockRejectedValueOnce(Object.assign(new Error("Network Error"), { isAxiosError: true }))
      .mockResolvedValue({ kind: "work_returned", off: false })
    renderAt("/unsubscribe?token=t1")
    expect(await screen.findByText(i18n.t("unsubscribe.unavailable"))).toBeInTheDocument()
    expect(screen.queryByText(i18n.t("unsubscribe.invalid"))).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: i18n.t("common.tryAgain") }))
    expect(await screen.findByRole("button", { name: i18n.t("unsubscribe.button") })).toBeInTheDocument()
    expect(read).toHaveBeenCalledTimes(2)
  })

  it("still calls a link the server refused broken", async () => {
    vi.spyOn(emailService, "readUnsubscribe").mockRejectedValue(
      Object.assign(new Error("Bad Request"), { isAxiosError: true, response: { status: 400, data: {} } }),
    )
    renderAt("/unsubscribe?token=bad")
    expect(await screen.findByText(i18n.t("unsubscribe.invalid"))).toBeInTheDocument()
  })
})
