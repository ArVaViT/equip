/**
 * What saving a quiz does to the class's attempts.
 *
 * The editor used to save every change the same way: POST a new quiz,
 * DELETE the old one — and ``quiz_attempts.quiz_id`` cascades. A teacher
 * who fixed a typo deleted every attempt and grade, and was told «Тест
 * сохранён». These pin the new behaviour from the teacher's side, in
 * Russian, which is who is saving a quiz tomorrow:
 *
 * - a correction goes to the quiz that exists (PATCH), nothing is deleted;
 * - a change that needs a rebuild asks first, with the number of attempts;
 * - a quiz nobody can pass is not sent, and the toast names the question;
 * - a 422 comes back as a Russian sentence naming the field;
 * - the type of an answered question cannot be changed, and says why.
 *
 * The error path is a plain function that throws, not ``vi.fn()`` with a
 * rejected promise: the latter lands in ``mock.results`` and the runner
 * reports an unhandled rejection before the component's ``catch`` runs.
 */

import React from "react"
import { AxiosError } from "axios"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Quiz, QuizAttempt } from "@/types"

const getChapterQuizForEdit = vi.fn()
const getQuizAttempts = vi.fn()
const createQuiz = vi.fn()
const deleteQuiz = vi.fn()
const updateQuiz = vi.fn()
const updateQuizQuestion = vi.fn()
const updateQuizOption = vi.fn()

/** Swapped in by a test that needs the create to fail. */
let createImpl: (...a: unknown[]) => Promise<unknown> = async (...a) => createQuiz(...a)

vi.mock("@/services/courses", () => ({
  coursesService: {
    getChapterQuizForEdit: (...a: unknown[]) => getChapterQuizForEdit(...a),
    getQuizAttempts: (...a: unknown[]) => getQuizAttempts(...a),
    createQuiz: (...a: unknown[]) => createImpl(...a),
    deleteQuiz: (...a: unknown[]) => deleteQuiz(...a),
    updateQuiz: (...a: unknown[]) => updateQuiz(...a),
    updateQuizQuestion: (...a: unknown[]) => updateQuizQuestion(...a),
    updateQuizOption: (...a: unknown[]) => updateQuizOption(...a),
  },
}))

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({
  toast: (...a: unknown[]) => toast(...a),
}))

const confirm = vi.fn()
vi.mock("@/components/ui/alert-dialog", () => ({
  useConfirm: () => (...a: unknown[]) => confirm(...a),
}))

import QuizEditor from "../QuizEditor"

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function savedQuiz(): Quiz {
  return {
    id: "quiz-1",
    chapter_id: "chap-1",
    title: "Бытие 1",
    description: null,
    quiz_type: "quiz",
    max_attempts: null,
    passing_score: 70,
    created_at: "2026-09-01T00:00:00Z",
    questions: [
      {
        id: "q1",
        quiz_id: "quiz-1",
        question_text: "Сколько дней творения?",
        question_type: "multiple_choice",
        order_index: 0,
        points: 1,
        min_words: null,
        options: [
          { id: "o1", question_id: "q1", option_text: "Пять", is_correct: false, order_index: 0 },
          { id: "o2", question_id: "q1", option_text: "Шесть", is_correct: true, order_index: 1 },
          { id: "o3", question_id: "q1", option_text: "Семь", is_correct: false, order_index: 2 },
        ],
      },
      {
        id: "q2",
        quiz_id: "quiz-1",
        question_text: "Опишите день седьмой.",
        question_type: "essay",
        order_index: 1,
        points: 5,
        min_words: null,
        options: [],
      },
    ],
  }
}

/** Two students answered the first question; nobody reached the essay. */
function twoAttemptsOnQ1(): QuizAttempt[] {
  const attempt = (id: string): QuizAttempt => ({
    id,
    quiz_id: "quiz-1",
    user_id: `student-${id}`,
    score: 1,
    max_score: 6,
    passed: false,
    started_at: "2026-09-02T00:00:00Z",
    completed_at: "2026-09-02T00:10:00Z",
    answers: [
      {
        id: `${id}-a`,
        question_id: "q1",
        selected_option_id: "o2",
        text_answer: null,
        is_correct: true,
        points_earned: 1,
        grader_comment: null,
        correct_option_id: "o2",
      },
    ],
  })
  return [attempt("a1"), attempt("a2")]
}

function pydantic422(entries: unknown[]): AxiosError {
  const err = new AxiosError("request failed")
  err.response = {
    status: 422,
    statusText: "",
    headers: {},
    config: { headers: undefined } as never,
    data: { detail: entries },
  }
  return err
}

async function renderSavedQuiz(attempts: QuizAttempt[] = twoAttemptsOnQ1()) {
  getChapterQuizForEdit.mockResolvedValue(savedQuiz())
  getQuizAttempts.mockResolvedValue(attempts)
  render(<QuizEditor chapterId="chap-1" />, { wrapper: Wrapper })
  await screen.findByDisplayValue("Сколько дней творения?")
}

const saveButton = () => screen.getByRole("button", { name: "Сохранить тест" })

describe("saving a quiz students have already taken", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage("en")
  })
  beforeEach(() => {
    vi.clearAllMocks()
    createImpl = async (...a) => createQuiz(...a)
    confirm.mockResolvedValue(true)
  })

  it("sends a typo fix to the question that exists and deletes nothing", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    const corrected = { ...savedQuiz() }
    corrected.questions[0]!.question_text = "Сколько было дней творения?"
    updateQuizQuestion.mockResolvedValue(corrected)

    const input = screen.getByDisplayValue("Сколько дней творения?")
    await user.clear(input)
    await user.type(input, "Сколько было дней творения?")
    await user.click(saveButton())

    await waitFor(() =>
      expect(updateQuizQuestion).toHaveBeenCalledWith(
        "q1",
        { question_text: "Сколько было дней творения?" },
        "chap-1",
      ),
    )
    expect(createQuiz).not.toHaveBeenCalled()
    expect(deleteQuiz).not.toHaveBeenCalled()
    expect(confirm).not.toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "Тест сохранён", variant: "success" }))
  })

  it("moving the right answer patches the two options, not the quiz", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    updateQuizOption.mockResolvedValue(savedQuiz())

    const radios = screen.getAllByRole("radio", { name: "Отметить как правильный" })
    await user.click(radios[2]!)
    await user.click(saveButton())

    await waitFor(() => expect(updateQuizOption).toHaveBeenCalledTimes(2))
    expect(updateQuizOption).toHaveBeenCalledWith("o2", { is_correct: false }, "chap-1")
    expect(updateQuizOption).toHaveBeenCalledWith("o3", { is_correct: true }, "chap-1")
    expect(createQuiz).not.toHaveBeenCalled()
    expect(deleteQuiz).not.toHaveBeenCalled()
  })

  it("asks before a rebuild, naming the number of attempts, and does nothing on «cancel»", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    confirm.mockResolvedValue(false)

    // Removing an option is the one edit the in-place routes cannot carry.
    await user.click(screen.getByRole("button", { name: "Удалить вариант 3" }))
    await user.click(saveButton())

    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
    const options = confirm.mock.calls[0]![0] as { title: string; description: string; confirmLabel: string }
    expect(options.title).toBe("Пересоздать тест?")
    expect(options.description).toContain("у него уже 2 попытки")
    expect(options.description).toContain("безвозвратно")
    expect(options.confirmLabel).toBe("Пересоздать и удалить попытки")
    expect(createQuiz).not.toHaveBeenCalled()
    expect(deleteQuiz).not.toHaveBeenCalled()
  })

  it("after «yes» rebuilds, then deletes the old quiz with force — the teacher has agreed", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    const rebuilt = { ...savedQuiz(), id: "quiz-2" }
    createQuiz.mockResolvedValue(rebuilt)
    deleteQuiz.mockResolvedValue(undefined)

    await user.click(screen.getByRole("button", { name: "Удалить вариант 3" }))
    await user.click(saveButton())

    await waitFor(() => expect(deleteQuiz).toHaveBeenCalledWith("quiz-1", "chap-1", { force: true }))
    expect(createQuiz).toHaveBeenCalledTimes(1)
    expect(createQuiz.mock.invocationCallOrder[0]).toBeLessThan(deleteQuiz.mock.invocationCallOrder[0]!)
  })

  it("does not ask when there are no attempts to lose", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz([])
    createQuiz.mockResolvedValue({ ...savedQuiz(), id: "quiz-2" })
    deleteQuiz.mockResolvedValue(undefined)

    await user.click(screen.getByRole("button", { name: "Удалить вариант 3" }))
    await user.click(saveButton())

    await waitFor(() => expect(deleteQuiz).toHaveBeenCalledWith("quiz-1", "chap-1", { force: false }))
    expect(confirm).not.toHaveBeenCalled()
  })

  it("locks the type of a question somebody has answered, and says why", async () => {
    await renderSavedQuiz()

    const selectors = screen.getAllByRole("combobox", { name: "Тип вопроса" })
    expect(selectors[0]).toBeDisabled()
    expect(selectors[1]).not.toBeDisabled()
    expect(
      screen.getByText(/На этот вопрос уже отвечали, поэтому тип изменить нельзя/),
    ).toBeInTheDocument()
  })

  it("tells the teacher how many attempts a delete would take with it", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    deleteQuiz.mockResolvedValue(undefined)

    await user.click(screen.getByRole("button", { name: "Удалить тест" }))

    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
    const options = confirm.mock.calls[0]![0] as { description: string }
    expect(options.description).toBe("У этого теста уже 2 попытки. Все они исчезнут вместе с оценками — безвозвратно.")
    await waitFor(() => expect(deleteQuiz).toHaveBeenCalledWith("quiz-1", "chap-1", { force: true }))
  })
})

describe("a quiz nobody could pass", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage("en")
  })
  beforeEach(() => {
    vi.clearAllMocks()
    createImpl = async (...a) => createQuiz(...a)
    getChapterQuizForEdit.mockResolvedValue(null)
  })

  async function renderNewQuizWithOneQuestion() {
    const user = userEvent.setup()
    render(<QuizEditor chapterId="chap-1" />, { wrapper: Wrapper })
    await screen.findByText("Создать тест")
    await user.type(screen.getByPlaceholderText("напр. Тест по главе"), "Бытие 1")
    await user.click(screen.getByRole("button", { name: "Добавить вопрос" }))
    await user.type(screen.getByPlaceholderText("Текст вопроса..."), "Сколько дней творения?")
    await user.type(screen.getByPlaceholderText("Вариант 1"), "Шесть")
    await user.type(screen.getByPlaceholderText("Вариант 2"), "Семь")
    return user
  }

  it("is not sent when no answer is marked correct — the toast names the question", async () => {
    const user = await renderNewQuizWithOneQuestion()

    await user.click(saveButton())

    expect(toast).toHaveBeenCalledWith({ title: "Вопрос 1: отметьте правильный ответ", variant: "destructive" })
    expect(createQuiz).not.toHaveBeenCalled()
  })

  it("is sent once the answer is marked", async () => {
    const user = await renderNewQuizWithOneQuestion()
    createQuiz.mockResolvedValue({ ...savedQuiz(), id: "quiz-9" })

    await user.click(screen.getAllByRole("radio", { name: "Отметить как правильный" })[0]!)
    await user.click(saveButton())

    await waitFor(() => expect(createQuiz).toHaveBeenCalledTimes(1))
    expect(deleteQuiz).not.toHaveBeenCalled()
  })

  it("shows a 422 as a Russian sentence naming the field, not pydantic's English", async () => {
    const user = await renderNewQuizWithOneQuestion()
    createImpl = async () => {
      throw pydantic422([
        {
          type: "less_than_equal",
          loc: ["body", "questions", 0, "points"],
          msg: "Input should be less than or equal to 100",
          input: 150,
          ctx: { le: 100 },
        },
      ])
    }

    await user.click(screen.getAllByRole("radio", { name: "Отметить как правильный" })[0]!)
    await user.click(saveButton())

    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith({
        title: "Не удалось сохранить тест",
        description: "Вопрос 1, баллы: не больше 100",
        variant: "destructive",
      }),
    )
  })

  it("refuses 150 points before sending, naming the range", async () => {
    const user = await renderNewQuizWithOneQuestion()
    const points = screen.getByRole("spinbutton", { name: "Баллы:" })
    await user.clear(points)
    await user.type(points, "150")
    await user.click(screen.getAllByRole("radio", { name: "Отметить как правильный" })[0]!)

    await user.click(saveButton())

    expect(toast).toHaveBeenCalledWith({ title: "Вопрос 1: баллы — целое число от 1 до 100", variant: "destructive" })
    expect(createQuiz).not.toHaveBeenCalled()
  })
})
