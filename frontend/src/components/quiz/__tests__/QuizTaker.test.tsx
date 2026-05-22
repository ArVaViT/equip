import React from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Quiz, QuizAttempt } from "@/types"
import i18n from "@/i18n/config"

const getChapterQuiz = vi.fn()
const getMyQuizAttempts = vi.fn()
const submitQuiz = vi.fn()

vi.mock("@/services/courses", () => ({
  coursesService: {
    getChapterQuiz: (...a: unknown[]) => getChapterQuiz(...a),
    getMyQuizAttempts: (...a: unknown[]) => getMyQuizAttempts(...a),
    submitQuiz: (...a: unknown[]) => submitQuiz(...a),
  },
}))

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({
  toast: (...a: unknown[]) => toast(...a),
}))

import QuizTaker from "../QuizTaker"

function I18nWrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const renderOpts = { wrapper: I18nWrapper }

function makeQuiz(overrides: Partial<Quiz> = {}): Quiz {
  return {
    id: "quiz-1",
    chapter_id: "chap-1",
    title: "Genesis 1 Quiz",
    description: "A quick check",
    quiz_type: "quiz",
    max_attempts: 3,
    passing_score: 70,
    created_at: "2025-01-01T00:00:00Z",
    questions: [
      {
        id: "q1",
        quiz_id: "quiz-1",
        question_text: "How many days of creation?",
        question_type: "multiple_choice",
        order_index: 0,
        points: 1,
        min_words: null,
        options: [
          { id: "o1a", question_id: "q1", option_text: "5", is_correct: false, order_index: 0 },
          { id: "o1b", question_id: "q1", option_text: "6", is_correct: true, order_index: 1 },
          { id: "o1c", question_id: "q1", option_text: "7", is_correct: false, order_index: 2 },
        ],
      },
      {
        id: "q2",
        quiz_id: "quiz-1",
        question_text: "God rested on the seventh day.",
        question_type: "true_false",
        order_index: 1,
        points: 1,
        min_words: null,
        options: [
          { id: "o2a", question_id: "q2", option_text: "True", is_correct: true, order_index: 0 },
          { id: "o2b", question_id: "q2", option_text: "False", is_correct: false, order_index: 1 },
        ],
      },
    ],
    ...overrides,
  }
}

function makeAttempt(overrides: Partial<QuizAttempt> = {}): QuizAttempt {
  return {
    id: "a-1",
    quiz_id: "quiz-1",
    user_id: "user-1",
    score: 2,
    max_score: 2,
    passed: true,
    started_at: "2025-01-01T00:00:00Z",
    completed_at: "2025-01-01T00:01:00Z",
    answers: [
      {
        id: "ans-1",
        question_id: "q1",
        selected_option_id: "o1b",
        text_answer: null,
        is_correct: true,
        points_earned: 1,
        grader_comment: null,
        correct_option_id: "o1b",
      },
      {
        id: "ans-2",
        question_id: "q2",
        selected_option_id: "o2a",
        text_answer: null,
        is_correct: true,
        points_earned: 1,
        grader_comment: null,
        correct_option_id: "o2a",
      },
    ],
    ...overrides,
  }
}

describe("QuizTaker", () => {
  beforeEach(() => {
    getChapterQuiz.mockReset()
    getMyQuizAttempts.mockReset()
    submitQuiz.mockReset()
    toast.mockReset()
  })

  it("shows a spinner while loading and then the quiz title", async () => {
    getChapterQuiz.mockResolvedValue(makeQuiz())
    getMyQuizAttempts.mockResolvedValue([])

    render(<QuizTaker chapterId="chap-1" />, renderOpts)

    await waitFor(() => {
      expect(screen.getByText("Genesis 1 Quiz")).toBeInTheDocument()
    })
    expect(screen.getByRole("button", { name: /submit quiz/i })).toBeDisabled()
  })

  it("renders nothing when the chapter has no quiz", async () => {
    getChapterQuiz.mockResolvedValue(null)
    const { container } = render(<QuizTaker chapterId="chap-1" />, renderOpts)
    await waitFor(() => {
      expect(container.querySelector(".animate-spin")).toBeNull()
    })
    expect(container.textContent).toBe("")
  })

  it("shows an error message when the fetch throws", async () => {
    getChapterQuiz.mockRejectedValue(new Error("network"))
    render(<QuizTaker chapterId="chap-1" />, renderOpts)
    await waitFor(() => {
      expect(screen.getByText(/failed to load quiz/i)).toBeInTheDocument()
    })
  })

  it("enables submit once every question is answered", async () => {
    getChapterQuiz.mockResolvedValue(makeQuiz())
    getMyQuizAttempts.mockResolvedValue([])
    const user = userEvent.setup()

    render(<QuizTaker chapterId="chap-1" />, renderOpts)
    await waitFor(() => screen.getByText("Genesis 1 Quiz"))

    const submit = screen.getByRole("button", { name: /submit quiz/i })
    expect(submit).toBeDisabled()

    // Pick the correct MCQ option.
    await user.click(screen.getByLabelText("6"))
    expect(submit).toBeDisabled()

    // true/false uses a <button>, not a label.
    await user.click(screen.getByRole("button", { name: "True" }))
    expect(submit).toBeEnabled()
  })

  it("submits answers and shows the results view on success", async () => {
    getChapterQuiz.mockResolvedValue(makeQuiz())
    getMyQuizAttempts.mockResolvedValue([])
    submitQuiz.mockResolvedValue(makeAttempt())
    const user = userEvent.setup()

    render(<QuizTaker chapterId="chap-1" />, renderOpts)
    await waitFor(() => screen.getByText("Genesis 1 Quiz"))

    await user.click(screen.getByLabelText("6"))
    await user.click(screen.getByRole("button", { name: "True" }))
    await user.click(screen.getByRole("button", { name: /submit quiz/i }))

    await waitFor(() => {
      expect(screen.getByText(/you passed/i)).toBeInTheDocument()
    })
    expect(submitQuiz).toHaveBeenCalledWith("quiz-1", [
      { question_id: "q1", selected_option_id: "o1b", text_answer: undefined },
      { question_id: "q2", selected_option_id: "o2a", text_answer: undefined },
    ])
  })

  it("shows a toast when the submission fails", async () => {
    getChapterQuiz.mockResolvedValue(makeQuiz())
    getMyQuizAttempts.mockResolvedValue([])
    submitQuiz.mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "Server down" } },
    })
    const user = userEvent.setup()

    render(<QuizTaker chapterId="chap-1" />, renderOpts)
    await waitFor(() => screen.getByText("Genesis 1 Quiz"))
    await user.click(screen.getByLabelText("6"))
    await user.click(screen.getByRole("button", { name: "True" }))
    await user.click(screen.getByRole("button", { name: /submit quiz/i }))

    await waitFor(() => {
      expect(toast).toHaveBeenCalled()
    })
    // Still on the quiz form, not the results card.
    expect(screen.queryByText(/you passed/i)).not.toBeInTheDocument()
  })

  it("blocks further attempts once max_attempts is reached", async () => {
    const completed = [
      makeAttempt({ id: "a1", completed_at: "2025-01-01T00:01:00Z" }),
      makeAttempt({ id: "a2", completed_at: "2025-01-02T00:01:00Z" }),
      makeAttempt({ id: "a3", completed_at: "2025-01-03T00:01:00Z" }),
    ]
    getChapterQuiz.mockResolvedValue(makeQuiz({ max_attempts: 3 }))
    getMyQuizAttempts.mockResolvedValue(completed)

    render(<QuizTaker chapterId="chap-1" />, renderOpts)
    await waitFor(() => screen.getByText("Genesis 1 Quiz"))

    expect(screen.getByText(/maximum attempts reached/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /submit quiz/i })).toBeDisabled()
    expect(screen.getByText(/attempts: 3\/3/i)).toBeInTheDocument()
  })

  it("says 'Submit Exam' for quiz_type exam", async () => {
    getChapterQuiz.mockResolvedValue(makeQuiz({ quiz_type: "exam" }))
    getMyQuizAttempts.mockResolvedValue([])

    render(<QuizTaker chapterId="chap-1" />, renderOpts)
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /submit exam/i })).toBeInTheDocument(),
    )
  })
})
