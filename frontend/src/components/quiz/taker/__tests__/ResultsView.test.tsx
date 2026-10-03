import { render, screen, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import type { Quiz, QuizAttempt, QuizQuestion } from "@/types"
import { ResultsView } from "../ResultsView"

/**
 * Right and wrong are said, not only coloured. The icons beside each question
 * had no words, and the options carried bare ✓ / ✗ that a screen reader reads
 * as "check mark" and "multiplication sign"; and the reader's own choice was
 * unmarked whenever it was the right one.
 */
const opt = (id: string, text: string, order: number) => ({ id, question_id: "", option_text: text, is_correct: false, order_index: order })
const questions = [
  { id: "q1", quiz_id: "z", question_text: "Кто?", question_type: "multiple_choice", order_index: 0, points: 1, min_words: null, options: [opt("a", "Пётр", 0), opt("b", "Павел", 1)] },
  { id: "q2", quiz_id: "z", question_text: "Где?", question_type: "multiple_choice", order_index: 1, points: 1, min_words: null, options: [opt("c", "Рим", 0), opt("d", "Иерусалим", 1)] },
] as unknown as QuizQuestion[]
const result = {
  id: "t", quiz_id: "z", user_id: "u", score: 1, max_score: 2, passed: false, started_at: "", completed_at: "",
  answers: [
    { id: "1", question_id: "q1", selected_option_id: "a", text_answer: null, is_correct: true, points_earned: 1, grader_comment: null, correct_option_id: "a" },
    { id: "2", question_id: "q2", selected_option_id: "c", text_answer: null, is_correct: false, points_earned: 0, grader_comment: null, correct_option_id: "d" },
  ],
} as QuizAttempt

describe("ResultsView", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })

  it("says which answers were right and wrong, and which was yours", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <ResultsView
          result={result}
          quiz={{ passing_score: 70 } as Quiz}
          questions={questions}
          answers={{ q1: { selected_option_id: "a" }, q2: { selected_option_id: "c" } } as never}
        />
      </I18nextProvider>,
    )
    const right = screen.getByText("Пётр").closest("div")!
    expect(within(right).getByText(`(${i18n.t("quiz.result.yourAnswer")})`)).toBeInTheDocument()
    expect(within(right).getByText(i18n.t("quiz.result.correct"))).toBeInTheDocument()

    const wrongPick = screen.getByText("Рим").closest("div")!
    expect(within(wrongPick).getByText(`(${i18n.t("quiz.result.yourAnswer")})`)).toBeInTheDocument()
    expect(within(wrongPick).getByText(i18n.t("quiz.result.incorrect"))).toBeInTheDocument()

    const key = screen.getByText("Иерусалим").closest("div")!
    expect(within(key).getByText(i18n.t("quiz.result.rightAnswer"))).toBeInTheDocument()

    // Each question says its verdict in words too.
    expect(screen.getAllByText(i18n.t("quiz.result.correct")).length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText(i18n.t("quiz.result.incorrect")).length).toBeGreaterThanOrEqual(2)
  })

  it("on an exam, which hides the key, still calls a right answer right", () => {
    const exam = {
      ...result,
      answers: result.answers!.map((a) => ({ ...a, correct_option_id: null })),
    } as QuizAttempt
    render(
      <I18nextProvider i18n={i18n}>
        <ResultsView
          result={exam}
          quiz={{ passing_score: 70 } as Quiz}
          questions={questions}
          answers={{ q1: { selected_option_id: "a" }, q2: { selected_option_id: "c" } } as never}
        />
      </I18nextProvider>,
    )
    const right = screen.getByText("Пётр").closest("div")!
    expect(within(right).getByText(i18n.t("quiz.result.correct"))).toBeInTheDocument()
    expect(within(right).queryByText(i18n.t("quiz.result.incorrect"))).toBeNull()
    expect(right.textContent).not.toContain("✗")

    const wrongPick = screen.getByText("Рим").closest("div")!
    expect(within(wrongPick).getByText(i18n.t("quiz.result.incorrect"))).toBeInTheDocument()
    // The key stays hidden.
    expect(screen.queryByText(i18n.t("quiz.result.rightAnswer"))).toBeNull()
  })
})
