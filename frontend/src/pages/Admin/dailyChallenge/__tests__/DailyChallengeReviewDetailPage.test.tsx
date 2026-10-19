/**
 * Saving one language cell used to reload the page through its skeleton,
 * and the skeleton unmounted every other cell — with the corrections a
 * reviewer had typed into them.
 */
import type { ReactNode } from "react"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ConfirmProvider } from "@/components/ui/alert-dialog"
import i18n, { SUPPORTED_LOCALES, type SupportedLocale } from "@/i18n/config"
import {
  adminDailyChallengeService,
  type AdminDailyChallengeBilingualView,
  type AdminDailyChallengeCvCell,
} from "@/services/adminDailyChallenge"
import DailyChallengeReviewDetailPage from "../DailyChallengeReviewDetailPage"

function cells(text: (locale: SupportedLocale) => string): Record<SupportedLocale, AdminDailyChallengeCvCell> {
  return Object.fromEntries(
    SUPPORTED_LOCALES.map((locale) => [locale, { cv_id: `cv-${locale}`, text: text(locale), origin: "mt", locale, updated_at: null }]),
  ) as Record<SupportedLocale, AdminDailyChallengeCvCell>
}

function view(question: (locale: SupportedLocale) => string): AdminDailyChallengeBilingualView {
  return {
    id: "q1",
    status: "draft",
    rejected: false,
    rejection_reason: null,
    bible_book: "Acts",
    bible_chapter: 2,
    bible_verse_from: 42,
    bible_verse_to: null,
    source_locale: "en",
    question_text: cells(question),
    explanation: cells((l) => `explanation ${l}`),
    options: [],
  } as AdminDailyChallengeBilingualView
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/admin/daily-challenge/review/q1"]}>
        <ConfirmProvider>
          <Routes>
            <Route path="/admin/daily-challenge/review/:questionId" element={children} />
          </Routes>
        </ConfirmProvider>
      </MemoryRouter>
    </I18nextProvider>
  )
}

describe("the daily challenge review page", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("keeps what was typed in the other cells when one of them is saved", async () => {
    const load = vi
      .spyOn(adminDailyChallengeService, "getBilingualView")
      .mockResolvedValueOnce(view((l) => `question ${l}`))
      .mockResolvedValueOnce(view((l) => (l === "en" ? "question en, fixed" : `question ${l}`)))
    vi.spyOn(adminDailyChallengeService, "upsertCv").mockResolvedValue(undefined as never)
    const user = userEvent.setup()
    render(<DailyChallengeReviewDetailPage />, { wrapper: Wrapper })

    const boxes = await screen.findAllByRole("textbox")
    const en = boxes[SUPPORTED_LOCALES.indexOf("en")]!
    const ru = boxes[SUPPORTED_LOCALES.indexOf("ru")]!
    await user.type(ru, " — черновик")
    await user.clear(en)
    await user.type(en, "question en, fixed")
    await user.click(within(en.parentElement!).getByRole("button", { name: "Save" }))

    await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(en).toHaveValue("question en, fixed"))
    // The same element, with the same draft: the page was refreshed, not rebuilt.
    expect(document.body.contains(ru)).toBe(true)
    expect(ru).toHaveValue("question ru — черновик")
  })
})
