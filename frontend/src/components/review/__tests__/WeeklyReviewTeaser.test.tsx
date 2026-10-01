/** The home page's "review is ready" line: one per course, nothing when none. */
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { reviewService } from "@/services/review"

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))

import { WeeklyReviewTeaser } from "../WeeklyReviewTeaser"

function show() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <WeeklyReviewTeaser />
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("WeeklyReviewTeaser", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("links each course with a review to its review", async () => {
    vi.spyOn(reviewService, "waiting").mockResolvedValue([{ course_id: "c1", course_title: "Деяния", count: 3 }])
    show()
    const link = await screen.findByRole("link", { name: /Деяния.*3 вопроса/ })
    expect(link).toHaveAttribute("href", "/courses/c1#weekly-review")
  })

  it("is absent when there is nothing to review", async () => {
    vi.spyOn(reviewService, "waiting").mockResolvedValue([])
    const { container } = show()
    await new Promise((r) => setTimeout(r, 0))
    expect(container).toBeEmptyDOMElement()
  })
})
