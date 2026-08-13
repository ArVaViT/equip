import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { legalService } from "@/services/legal"
import LegalDocumentPage from "../LegalDocumentPage"

const DOC = {
  slug: "privacy",
  version: "1.0",
  locale: "ru",
  body: "# Политика конфиденциальности\n\nМы не продаём ваши данные.",
  sha256: "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("LegalDocumentPage", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("renders the document the server serves", async () => {
    vi.spyOn(legalService, "document").mockResolvedValue(DOC)
    render(<LegalDocumentPage slug="privacy" />, { wrapper: Wrapper })

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Политика конфиденциальности",
    )
  })

  it("prints the version and fingerprint of what is on screen", async () => {
    vi.spyOn(legalService, "document").mockResolvedValue(DOC)
    render(<LegalDocumentPage slug="privacy" />, { wrapper: Wrapper })

    // This is what an acceptance record points at. Printing it means a person
    // can check that the text they are reading is the text they agreed to.
    expect(await screen.findByText(/abcdef0123456789/)).toBeInTheDocument()
    expect(screen.getByText(/1\.0/)).toBeInTheDocument()
  })

  it("asks for the document in the reader's language", async () => {
    const fetch = vi.spyOn(legalService, "document").mockResolvedValue({ ...DOC, locale: "en" })
    await i18n.changeLanguage("en")
    render(<LegalDocumentPage slug="terms" />, { wrapper: Wrapper })

    await screen.findByRole("heading", { level: 1 })
    expect(fetch).toHaveBeenCalledWith("terms", "en")
  })

  it("says so when the document cannot be loaded", async () => {
    // A legal page that renders empty on a failed fetch reads as "there is no
    // policy", which is precisely the state this work came from.
    vi.spyOn(legalService, "document").mockRejectedValue(new Error("offline"))
    render(<LegalDocumentPage slug="privacy" />, { wrapper: Wrapper })

    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument()
  })
})
