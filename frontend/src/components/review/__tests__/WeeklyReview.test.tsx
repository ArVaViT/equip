/** The week's review, as a student meets it in Russian: start, answer, see why, finish. */
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { reviewService } from "@/services/review"
import { WeeklyReview } from "../WeeklyReview"

const QUESTIONS = [
  { id: "q1", question_text: "Кто проповедовал в Пятидесятницу?", options: [{ id: "a", option_text: "Павел" }, { id: "b", option_text: "Пётр" }] },
  { id: "q2", question_text: "Где обратился Савл?", options: [{ id: "c", option_text: "По дороге в Дамаск" }, { id: "d", option_text: "В Риме" }] },
]

function show() {
  return render(
    <I18nextProvider i18n={i18n}>
      <WeeklyReview courseId="k" />
    </I18nextProvider>,
  )
}

describe("WeeklyReview", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("goes through the questions and says how it went", async () => {
    const user = userEvent.setup()
    vi.spyOn(reviewService, "forCourse").mockResolvedValue(QUESTIONS)
    vi.spyOn(reviewService, "check")
      .mockResolvedValueOnce({ correct: false, correct_option_id: "b" })
      .mockResolvedValueOnce({ correct: true, correct_option_id: "c" })
    show()
    expect(await screen.findByText("2 вопроса из пройденного — для себя, на оценки не влияет.")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Начать" }))
    await user.click(screen.getByRole("button", { name: "Павел" }))
    expect(await screen.findByText("Неверно")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Пётр.*правильный ответ/ })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "Дальше" }))
    await user.click(screen.getByRole("button", { name: "По дороге в Дамаск" }))
    expect(await screen.findByText("Верно")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Готово" }))
    expect(screen.getByText("Верно 1 из 2. Новые вопросы — на следующей неделе.")).toBeInTheDocument()
  })

  it("is absent when there is nothing to review", async () => {
    vi.spyOn(reviewService, "forCourse").mockResolvedValue([])
    const { container } = show()
    await new Promise((r) => setTimeout(r, 0))
    expect(container).toBeEmptyDOMElement()
  })

  it("moves focus to each question, and says when a check failed", async () => {
    const user = userEvent.setup()
    vi.spyOn(reviewService, "forCourse").mockResolvedValue(QUESTIONS)
    vi.spyOn(reviewService, "check")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ correct: true, correct_option_id: "b" })
    show()
    await user.click(await screen.findByRole("button", { name: "Начать" }))
    expect(screen.getByText("Кто проповедовал в Пятидесятницу?")).toHaveFocus()
    await user.click(screen.getByRole("button", { name: "Пётр" }))
    expect(await screen.findByText("Не удалось проверить — попробуйте ещё раз.")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Пётр" }))
    expect(await screen.findByText("Верно")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Дальше" }))
    expect(screen.getByText("Где обратился Савл?")).toHaveFocus()
  })
})
