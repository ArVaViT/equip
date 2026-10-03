/**
 * What saving a quiz does to the class's attempts.
 *
 * The editor used to save every change the same way: POST a new quiz,
 * DELETE the old one — and ``quiz_attempts.quiz_id`` cascades. A teacher
 * who fixed a typo deleted every attempt and grade, and was told «Тест
 * сохранён». These pin the new behaviour from the teacher's side, in
 * Russian, which is who is saving a quiz tomorrow:
 *
 * - a correction goes to the quiz that exists, each changed question sent
 *   whole with its options (``PUT /quizzes/questions/{id}``), nothing is
 *   deleted;
 * - a change that needs a rebuild asks first, with the number of attempts,
 *   and then replaces the quiz in one request — never create-then-delete,
 *   which left two quizzes on the lesson when the delete was refused
 *   (2026-10-03);
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
const replaceQuiz = vi.fn()
const deleteQuiz = vi.fn()
const updateQuiz = vi.fn()
const saveQuizQuestion = vi.fn()

/** Swapped in by a test that needs the create to fail. */
let createImpl: (...a: unknown[]) => Promise<unknown> = async (...a) => createQuiz(...a)
/** Swapped in by a test that needs the whole-question save to fail. */
let saveQuestionImpl: (...a: unknown[]) => Promise<unknown> = async (...a) => saveQuizQuestion(...a)

vi.mock("@/services/courses", () => ({
  coursesService: {
    getChapterQuizForEdit: (...a: unknown[]) => getChapterQuizForEdit(...a),
    getQuizAttempts: (...a: unknown[]) => getQuizAttempts(...a),
    createQuiz: (...a: unknown[]) => createImpl(...a),
    replaceQuiz: (...a: unknown[]) => replaceQuiz(...a),
    deleteQuiz: (...a: unknown[]) => deleteQuiz(...a),
    updateQuiz: (...a: unknown[]) => updateQuiz(...a),
    saveQuizQuestion: (...a: unknown[]) => saveQuestionImpl(...a),
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

function equipError(status: number, detail: { code: string; message: string; context: Record<string, unknown> }) {
  const err = new AxiosError("request failed")
  err.response = { status, statusText: "", headers: {}, config: { headers: undefined } as never, data: { detail } }
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
    saveQuestionImpl = async (...a) => saveQuizQuestion(...a)
    confirm.mockResolvedValue(true)
  })

  it("sends a typo fix to the question that exists — whole, with its options — and deletes nothing", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    const corrected = { ...savedQuiz() }
    corrected.questions[0]!.question_text = "Сколько было дней творения?"
    saveQuizQuestion.mockResolvedValue(corrected)

    const input = screen.getByDisplayValue("Сколько дней творения?")
    await user.clear(input)
    await user.type(input, "Сколько было дней творения?")
    await user.click(saveButton())

    await waitFor(() => expect(saveQuizQuestion).toHaveBeenCalledTimes(1))
    expect(saveQuizQuestion).toHaveBeenCalledWith(
      "q1",
      {
        question_text: "Сколько было дней творения?",
        question_type: "multiple_choice",
        order_index: 0,
        points: 1,
        min_words: null,
        options: [
          { id: "o1", option_text: "Пять", is_correct: false, order_index: 0 },
          { id: "o2", option_text: "Шесть", is_correct: true, order_index: 1 },
          { id: "o3", option_text: "Семь", is_correct: false, order_index: 2 },
        ],
      },
      "chap-1",
    )
    expect(createQuiz).not.toHaveBeenCalled()
    expect(replaceQuiz).not.toHaveBeenCalled()
    expect(deleteQuiz).not.toHaveBeenCalled()
    expect(confirm).not.toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "Тест сохранён", variant: "success" }))
  })

  it("moving the right answer is one request with both options — the server never sees a question without one", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    saveQuizQuestion.mockResolvedValue(savedQuiz())

    const radios = screen.getAllByRole("radio", { name: "Отметить как правильный" })
    await user.click(radios[2]!)
    await user.click(saveButton())

    await waitFor(() => expect(saveQuizQuestion).toHaveBeenCalledTimes(1))
    const [id, question, chapterId] = saveQuizQuestion.mock.calls[0]! as [
      string,
      { options: Array<{ id: string; is_correct: boolean }> },
      string,
    ]
    expect(id).toBe("q1")
    expect(chapterId).toBe("chap-1")
    expect(question.options.map((o) => [o.id, o.is_correct])).toEqual([
      ["o1", false],
      ["o2", false],
      ["o3", true],
    ])
    expect(createQuiz).not.toHaveBeenCalled()
    expect(replaceQuiz).not.toHaveBeenCalled()
    expect(deleteQuiz).not.toHaveBeenCalled()
  })

  it("a question the server refuses stays as typed, and the toast says why", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    saveQuestionImpl = async () => {
      throw pydantic422([
        { type: "quiz_no_correct_option", loc: ["body", "options"], msg: "Exactly one option must be marked correct" },
      ])
    }

    await user.type(screen.getByDisplayValue("Сколько дней творения?"), "!")
    await user.click(saveButton())

    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith({
        title: "Не удалось сохранить тест",
        description: "отметьте правильный ответ",
        variant: "destructive",
      }),
    )
    expect(screen.getByDisplayValue("Сколько дней творения?!")).toBeInTheDocument()
    expect(screen.getByText("Есть несохранённые изменения")).toBeInTheDocument()
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

  it("after «yes» replaces the quiz in one request, with force — the teacher has agreed", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    const rebuilt = { ...savedQuiz(), id: "quiz-2" }
    replaceQuiz.mockResolvedValue(rebuilt)

    await user.click(screen.getByRole("button", { name: "Удалить вариант 3" }))
    await user.click(saveButton())

    await waitFor(() => expect(replaceQuiz).toHaveBeenCalledTimes(1))
    const [oldId, body, chapterId, opts] = replaceQuiz.mock.calls[0]! as [
      string,
      { title: string; questions: Array<{ options: unknown[] }> },
      string,
      { force: boolean },
    ]
    expect(oldId).toBe("quiz-1")
    expect(chapterId).toBe("chap-1")
    expect(opts).toEqual({ force: true })
    expect(body.title).toBe("Бытие 1")
    expect(body.questions[0]!.options).toHaveLength(2)
    expect(body).not.toHaveProperty("chapter_id")
    // Never the two-step rebuild that could leave two quizzes on the lesson.
    expect(createQuiz).not.toHaveBeenCalled()
    expect(deleteQuiz).not.toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "Тест сохранён", variant: "success" }))
  })

  it("does not ask when there are no attempts to lose, and replaces without force", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz([])
    replaceQuiz.mockResolvedValue({ ...savedQuiz(), id: "quiz-2" })

    await user.click(screen.getByRole("button", { name: "Удалить вариант 3" }))
    await user.click(saveButton())

    await waitFor(() => expect(replaceQuiz).toHaveBeenCalledTimes(1))
    expect(replaceQuiz.mock.calls[0]![3]).toEqual({ force: false })
    expect(confirm).not.toHaveBeenCalled()
    expect(createQuiz).not.toHaveBeenCalled()
    expect(deleteQuiz).not.toHaveBeenCalled()
  })

  it("a refused replacement leaves the draft as typed and shows the server's reason", async () => {
    // A student finished an attempt between the editor's count and the
    // save: the server refuses, nothing was written, and the teacher is
    // told — not shown «Тест сохранён» over a lesson that still has the
    // old quiz.
    const user = userEvent.setup()
    await renderSavedQuiz([])
    const refused = new AxiosError("request failed")
    refused.response = {
      status: 409,
      statusText: "",
      headers: {},
      config: { headers: undefined } as never,
      data: { detail: { code: "quiz.has_attempts", message: "has attempts", context: { attempt_count: 1 } } },
    }
    replaceQuiz.mockRejectedValue(refused)

    await user.click(screen.getByRole("button", { name: "Удалить вариант 3" }))
    await user.click(saveButton())

    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({ title: "Не удалось сохранить тест", variant: "destructive" }),
      ),
    )
    expect(toast).not.toHaveBeenCalledWith(expect.objectContaining({ title: "Тест сохранён" }))
    expect(screen.getByText("Есть несохранённые изменения")).toBeInTheDocument()
    expect(createQuiz).not.toHaveBeenCalled()
    expect(deleteQuiz).not.toHaveBeenCalled()
  })

  it("when the quiz was rebuilt elsewhere, loads the server's quiz instead of retrying the draft", async () => {
    // ``quiz.options_changed``: the option ids this editor holds are not
    // the question's any more. The newer quiz is shown, the lesson is told
    // its id, and the toast says the edits were not saved.
    const user = userEvent.setup()
    const onQuizSaved = vi.fn()
    getChapterQuizForEdit.mockResolvedValueOnce(savedQuiz())
    getQuizAttempts.mockResolvedValue([])
    render(<QuizEditor chapterId="chap-1" onQuizSaved={onQuizSaved} />, { wrapper: Wrapper })
    await screen.findByDisplayValue("Сколько дней творения?")
    saveQuestionImpl = async () => {
      throw equipError(409, { code: "quiz.options_changed", message: "changed", context: {} })
    }
    const rebuilt = { ...savedQuiz(), id: "quiz-2", title: "Бытие 1 (новая версия)" }
    getChapterQuizForEdit.mockResolvedValueOnce(rebuilt)

    await user.type(screen.getByDisplayValue("Сколько дней творения?"), "!")
    await user.click(saveButton())

    await waitFor(() => expect(screen.getByDisplayValue("Бытие 1 (новая версия)")).toBeInTheDocument())
    expect(onQuizSaved).toHaveBeenCalledWith("quiz-2")
    expect(toast).toHaveBeenCalledWith({
      title: "Тест изменили в другом месте, и он перезагружен. Правки не сохранены — внесите их заново.",
      variant: "destructive",
    })
    expect(toast).not.toHaveBeenCalledWith(expect.objectContaining({ title: "Не удалось сохранить тест" }))
    expect(screen.queryByText("Есть несохранённые изменения")).not.toBeInTheDocument()
    expect(createQuiz).not.toHaveBeenCalled()
    expect(replaceQuiz).not.toHaveBeenCalled()
  })

  it("locks the type of a question somebody has answered, and says why", async () => {
    await renderSavedQuiz()

    const selectors = screen.getAllByRole("combobox", { name: "Тип вопроса" })
    expect(selectors[0]).toBeDisabled()
    expect(selectors[1]).not.toBeDisabled()
    // Said once for the quiz, not under every answered question.
    expect(screen.getAllByText(/Этот тест уже проходили, поэтому у вопросов с ответами тип не меняется/)).toHaveLength(1)
    expect(selectors[0]).toHaveAttribute("title", expect.stringMatching(/На этот вопрос уже отвечали/))
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
    saveQuestionImpl = async (...a) => saveQuizQuestion(...a)
    getChapterQuizForEdit.mockResolvedValue(null)
  })

  async function renderNewQuizWithOneQuestion() {
    const user = userEvent.setup()
    render(<QuizEditor chapterId="chap-1" />, { wrapper: Wrapper })
    await screen.findByText("Создать тест")
    await user.type(screen.getByPlaceholderText("напр. Тест по уроку"), "Бытие 1")
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
    expect(createQuiz.mock.calls[0]![0]).toMatchObject({ chapter_id: "chap-1", title: "Бытие 1" })
    expect(replaceQuiz).not.toHaveBeenCalled()
    expect(deleteQuiz).not.toHaveBeenCalled()
  })

  it("corrects the quiz it just created instead of building another", async () => {
    // A new quiz used to keep its client-side ids after the first save, so
    // the second save rebuilt the whole quiz.
    const user = await renderNewQuizWithOneQuestion()
    createQuiz.mockResolvedValue({
      ...savedQuiz(),
      id: "quiz-9",
      title: "Бытие 1",
      questions: [
        {
          id: "srv-q",
          quiz_id: "quiz-9",
          question_text: "Сколько дней творения?",
          question_type: "multiple_choice",
          order_index: 0,
          points: 1,
          min_words: null,
          options: [
            { id: "srv-o1", question_id: "srv-q", option_text: "Шесть", is_correct: true, order_index: 0 },
            { id: "srv-o2", question_id: "srv-q", option_text: "Семь", is_correct: false, order_index: 1 },
          ],
        },
      ],
    })
    saveQuizQuestion.mockResolvedValue({ ...savedQuiz(), id: "quiz-9" })
    await user.click(screen.getAllByRole("radio", { name: "Отметить как правильный" })[0]!)
    await user.click(saveButton())
    await waitFor(() => expect(createQuiz).toHaveBeenCalledTimes(1))

    await user.type(screen.getByDisplayValue("Сколько дней творения?"), "!")
    await user.click(saveButton())

    await waitFor(() => expect(saveQuizQuestion).toHaveBeenCalled())
    const [id, question] = saveQuizQuestion.mock.calls[0]! as [string, { options: Array<{ id: string }> }]
    expect(id).toBe("srv-q")
    expect(question.options.map((o) => o.id)).toEqual(["srv-o1", "srv-o2"])
    expect(createQuiz).toHaveBeenCalledTimes(1)
    expect(replaceQuiz).not.toHaveBeenCalled()
  })

  it("when the lesson already has a quiz, shows that quiz instead of an empty block", async () => {
    // A second quiz block, or an editor opened before the first save
    // landed: the server refuses to create another (``quiz.already_exists``).
    // The existing quiz is loaded here and the block is pointed at it.
    const onQuizSaved = vi.fn()
    const user = userEvent.setup()
    render(<QuizEditor chapterId="chap-1" onQuizSaved={onQuizSaved} />, { wrapper: Wrapper })
    await screen.findByText("Создать тест")
    await user.type(screen.getByPlaceholderText("напр. Тест по уроку"), "Черновик")
    await user.click(screen.getByRole("button", { name: "Добавить вопрос" }))
    await user.type(screen.getByPlaceholderText("Текст вопроса..."), "Сколько дней творения?")
    await user.type(screen.getByPlaceholderText("Вариант 1"), "Шесть")
    await user.type(screen.getByPlaceholderText("Вариант 2"), "Семь")
    await user.click(screen.getAllByRole("radio", { name: "Отметить как правильный" })[0]!)
    createImpl = async () => {
      throw equipError(409, {
        code: "quiz.already_exists",
        message: "exists",
        context: { chapter_id: "chap-1", existing_quiz_id: "quiz-1" },
      })
    }
    getChapterQuizForEdit.mockResolvedValueOnce(savedQuiz())
    getQuizAttempts.mockResolvedValue([])

    await user.click(saveButton())

    await waitFor(() => expect(screen.getByDisplayValue("Бытие 1")).toBeInTheDocument())
    expect(screen.getByText("Изменить тест")).toBeInTheDocument()
    expect(onQuizSaved).toHaveBeenCalledWith("quiz-1")
    expect(toast).toHaveBeenCalledWith({
      title: "В этом уроке уже есть тест — теперь он загружен здесь. Черновик не сохранён.",
      variant: "destructive",
    })
    expect(toast).not.toHaveBeenCalledWith(expect.objectContaining({ title: "Не удалось сохранить тест" }))
    expect(replaceQuiz).not.toHaveBeenCalled()
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

describe("the editor's own furniture", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage("en")
  })
  beforeEach(() => {
    vi.clearAllMocks()
    confirm.mockResolvedValue(true)
  })

  it("says there are unsaved changes, and only once there are", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    expect(screen.queryByText("Есть несохранённые изменения")).not.toBeInTheDocument()

    await user.type(screen.getByDisplayValue("Сколько дней творения?"), "!")

    expect(screen.getByText("Есть несохранённые изменения")).toBeInTheDocument()
  })

  it("keeps a line break in a question — the student's quiz shows it", async () => {
    const user = userEvent.setup()
    await renderSavedQuiz()
    const field = screen.getByDisplayValue("Сколько дней творения?")

    await user.type(field, "{Enter}Подумайте.")

    expect(field).toHaveValue("Сколько дней творения?\nПодумайте.")
  })

  it("names the delete button even where it shows only an icon", async () => {
    await renderSavedQuiz()
    expect(screen.getByRole("button", { name: "Удалить тест" })).toBeInTheDocument()
  })
})
