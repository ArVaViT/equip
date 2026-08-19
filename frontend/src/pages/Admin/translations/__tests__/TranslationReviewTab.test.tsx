import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { adminTranslationsService, type NeedsReviewRow } from "@/services/adminTranslations"
import { TranslationReviewTab } from "../TranslationReviewTab"

function row(over: Partial<NeedsReviewRow> = {}): NeedsReviewRow {
  return {
    id: "3f2b1c44-0000-4000-8000-000000000001",
    entity_type: "quiz_option",
    entity_id: "opt-1",
    field: "option_text",
    locale: "uk",
    source_locale: "ru",
    review_reason: "[wrong_language] reads as ru, not uk",
    text: "Через віру",
    source_text: "Через веру",
    created_at: "2026-08-14T09:00:00Z",
    course_id: "c1",
    course_title: "Послание к Римлянам",
    is_daily_challenge: false,
    ...over,
  }
}

function page(items: NeedsReviewRow[]) {
  return { items, total: items.length, limit: 25, offset: 0 }
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("TranslationReviewTab", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("shows the translation beside the text it was made from", async () => {
    // Neither half is enough on its own: the reviewer is deciding
    // whether the check was right, and that is a comparison.
    vi.spyOn(adminTranslationsService, "listNeedsReview").mockResolvedValue(page([row()]))
    render(<TranslationReviewTab />, { wrapper: Wrapper })

    expect(await screen.findByText("Через віру")).toBeInTheDocument()
    expect(screen.getByText("Через веру")).toBeInTheDocument()
    expect(screen.getByText("[wrong_language] reads as ru, not uk")).toBeInTheDocument()
  })

  it("says which course the row belongs to", async () => {
    vi.spyOn(adminTranslationsService, "listNeedsReview").mockResolvedValue(page([row()]))
    render(<TranslationReviewTab />, { wrapper: Wrapper })

    expect(await screen.findByText("Послание к Римлянам")).toBeInTheDocument()
  })

  it("names platform content rather than leaving the course blank", async () => {
    vi.spyOn(adminTranslationsService, "listNeedsReview").mockResolvedValue(
      page([row({ course_id: null, course_title: null, is_daily_challenge: true })]),
    )
    render(<TranslationReviewTab />, { wrapper: Wrapper })

    expect(await screen.findByText("Вопрос дня")).toBeInTheDocument()
  })

  it("accepts one row and reloads so the count follows it", async () => {
    const list = vi
      .spyOn(adminTranslationsService, "listNeedsReview")
      .mockResolvedValueOnce(page([row()]))
      .mockResolvedValueOnce(page([]))
    const accept = vi.spyOn(adminTranslationsService, "accept").mockResolvedValue({ reset: 1 })
    render(<TranslationReviewTab />, { wrapper: Wrapper })

    await userEvent.click(await screen.findByRole("button", { name: /Принять/ }))

    expect(accept).toHaveBeenCalledWith(["3f2b1c44-0000-4000-8000-000000000001"])
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("retries exactly the row the button belongs to", async () => {
    // The endpoint also takes a coarse selector — entity type plus
    // language — and using it here would re-open every parked quiz
    // option in Ukrainian for one press beside one line of text.
    vi.spyOn(adminTranslationsService, "listNeedsReview").mockResolvedValue(
      page([row(), row({ id: "3f2b1c44-0000-4000-8000-000000000002", text: "Інший" })]),
    )
    const retry = vi.spyOn(adminTranslationsService, "retry").mockResolvedValue({ reset: 1 })
    render(<TranslationReviewTab />, { wrapper: Wrapper })

    const [, second] = await screen.findAllByRole("button", { name: /Перевести заново/ })
    if (!second) throw new Error("expected a Retry button on each of the two rows")
    await userEvent.click(second)

    expect(retry).toHaveBeenCalledWith(["3f2b1c44-0000-4000-8000-000000000002"])
  })

  it("says the queue is empty instead of showing an error", async () => {
    vi.spyOn(adminTranslationsService, "listNeedsReview").mockResolvedValue(page([]))
    render(<TranslationReviewTab />, { wrapper: Wrapper })

    expect(await screen.findByText("Ничего не ждёт")).toBeInTheDocument()
  })

  it("offers a way back when the queue will not load", async () => {
    vi.spyOn(adminTranslationsService, "listNeedsReview").mockRejectedValue(new Error("boom"))
    render(<TranslationReviewTab />, { wrapper: Wrapper })

    expect(await screen.findByText(/Не удалось загрузить очередь/)).toBeInTheDocument()
  })
})
