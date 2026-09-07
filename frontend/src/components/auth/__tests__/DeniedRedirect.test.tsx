import { render, screen, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { DeniedRedirect } from "../DeniedRedirect"

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (opts: unknown) => toast(opts) }))

/**
 * A student on /teacher used to be bounced to the dashboard with no word —
 * indistinguishable from a broken link. The redirect stays; the sentence is
 * what was missing.
 */
describe("DeniedRedirect", () => {
  beforeEach(async () => {
    toast.mockClear()
    await i18n.changeLanguage("ru")
  })

  it("lands on the dashboard and says why, once", async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={["/teacher"]}>
          <Routes>
            <Route path="/teacher" element={<DeniedRedirect />} />
            <Route path="/" element={<p>дашборд</p>} />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(await screen.findByText("дашборд")).toBeInTheDocument()
    await waitFor(() => expect(toast).toHaveBeenCalledTimes(1))
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: i18n.t("auth.notice.sectionUnavailable") }),
    )
  })
})
