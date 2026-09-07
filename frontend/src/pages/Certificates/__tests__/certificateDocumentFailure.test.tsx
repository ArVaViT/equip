import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import CertificateDocument from "../CertificateDocument"

/**
 * A certificate that failed to load is not a certificate that was never
 * issued. The page read only `{ data, loading }` from `useAsyncData`, so the
 * owner of an issued certificate, offline for a moment, was told «ещё не
 * выдано».
 */
function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/certificates/cert-1"]}>
        <Routes>
          <Route path="/certificates/:certificateId" element={<CertificateDocument />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("CertificateDocument when the list cannot be fetched", () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await i18n.changeLanguage("ru")
  })

  it("says the load failed, not that the certificate was never issued", async () => {
    vi.spyOn(coursesService, "getMyCertificates").mockRejectedValue(new Error("Network Error"))
    renderPage()
    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("certificates.document.loadFailed"))
    expect(screen.getByRole("button", { name: i18n.t("common.tryAgain") })).toBeInTheDocument()
    expect(screen.queryByText(i18n.t("certificates.document.notIssued"))).toBeNull()
  })

  it("still says «not issued» when the list simply does not contain it", async () => {
    vi.spyOn(coursesService, "getMyCertificates").mockResolvedValue([])
    renderPage()
    expect(await screen.findByText(i18n.t("certificates.document.notIssued"))).toBeInTheDocument()
  })
})
