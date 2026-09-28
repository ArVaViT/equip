import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { afterAll, describe, expect, it } from "vitest"

import i18n, { SUPPORTED_LOCALES } from "@/i18n/config"

import { Faq } from "../Faq"

/**
 * The two answers with a link in them, in every language.
 *
 * The links were first tagged `<link>` in the catalogues. `link` is a void
 * element in HTML, so the Trans parser closed it on the spot: each rendered
 * as an empty `<a>` with its words spilled out beside it — a link nobody
 * could see or click, in all four languages, with nothing failing.
 */
describe("Faq", () => {
  const initial = i18n.language
  afterAll(async () => {
    await i18n.changeLanguage(initial)
  })

  for (const locale of SUPPORTED_LOCALES) {
    it(`puts the words inside its links (${locale})`, async () => {
      await i18n.changeLanguage(locale)
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <Faq />
          </MemoryRouter>
        </I18nextProvider>,
      )

      const verify = screen.getAllByRole("link").find((a) => a.getAttribute("href") === "/verify")
      const mail = screen.getAllByRole("link").find((a) => a.getAttribute("href")?.startsWith("mailto:"))
      expect(verify?.textContent?.trim(), "verification link is empty").toBeTruthy()
      expect(mail?.textContent?.trim(), "contact link is empty").toBeTruthy()
    })
  }
})
