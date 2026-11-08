import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import * as toastModule from "@/lib/toast"
import { gradesService } from "@/services/grades"
import { rubricsService } from "@/services/rubrics"
import { coursesService } from "@/services/courses"
import { quizzesService } from "@/services/quizzes"
import GradingQueue from "../GradingQueue"
import type { SubmissionRubric, WaitingWork } from "@/types"

function work(over: Partial<WaitingWork> = {}): WaitingWork {
  return {
    kind: "assignment",
    id: "s1",
    item_id: "a1",
    course_id: "c1",
    course_title: "Основы веры",
    chapter_id: "ch1",
    title: "Эссе про благодать",
    prompt: null,
    student_name: "Пётр Иванов",
    student_locale: "ru",
    submitted_at: "2026-08-01T09:00:00Z",
    content: "Благодать — это незаслуженная милость",
    file_url: null,
    max_points: 100,
    is_late: false,
    ...over,
  }
}

function run(items: WaitingWork[], total = items.length) {
  return { items, total }
}

const NO_RUBRIC: SubmissionRubric = { rubric: null, marks: [], earned: null, out_of: null }

const level = (id: string, label: string) => ({ id, label, points: 5, description: null, order_index: 0 })
const criterion = (id: string, title: string, lvl: string, label: string, order = 0) => ({
  id,
  title,
  description: null,
  order_index: order,
  levels: [level(lvl, label)],
})
const RUBRIC = {
  id: "r1",
  course_id: "c1",
  title: "Эссе",
  max_score: 15,
  criteria: [
    criterion("cr1", "Опора на текст", "l1", "Да"),
    criterion("cr2", "Ясность", "l2", "Ясно", 1),
    criterion("cr3", "Применение", "l3", "Есть", 2),
  ],
}

function failure(status: number) {
  return Object.assign(new Error("HTTP " + status), {
    isAxiosError: true,
    response: { status, data: {} },
  })
}

function renderAt(path = "/teacher/review") {
  return render(<GradingQueue />, {
    wrapper: ({ children }: { children: ReactNode }) => (
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
      </I18nextProvider>
    ),
  })
}

async function startRun() {
  await userEvent.click(await screen.findByRole("button", { name: /Начать проверку/ }))
}

const note = () => screen.getByRole("textbox", { name: "Комментарий для студента" })
const next = () => screen.getByRole("button", { name: /Дальше|Готово|Пропустить/ })

describe("GradingQueue", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue(NO_RUBRIC)
  })

  it("lists what is waiting across courses, gathered by what was asked", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(
      run([
        work(),
        work({ id: "s2", student_name: "Анна" }),
        work({ id: "q1", kind: "quiz_answer", item_id: "qq", course_id: "c2", course_title: "Деяния", title: "Тест" }),
      ]),
    )
    renderAt()

    expect(await screen.findByText("3 работы ждут")).toBeInTheDocument()
    expect(screen.getByText("Эссе про благодать")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText(/Деяния/)).toBeInTheDocument()
  })

  it("counts the whole queue when only its first stretch was sent, and says the rest comes next", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(run([work()], 251))
    renderAt()

    expect(await screen.findByText("251 работа ждёт")).toBeInTheDocument()
    expect(screen.getByText("После этих ждут ещё 250 — они будут следующими")).toBeInTheDocument()
  })

  it("says «Всё проверено» when nothing is waiting, with a way back", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(run([]))
    renderAt()

    expect(await screen.findByText("Всё проверено")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "На главную" })).toHaveAttribute("href", "/teacher")
  })

  it("does not call a run that failed to load «all marked»", async () => {
    vi.spyOn(gradesService, "getRun").mockRejectedValue(failure(403))
    renderAt()

    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("errors.byStatus.403"))
    expect(screen.getByRole("button", { name: i18n.t("common.tryAgain") })).toBeInTheDocument()
    expect(screen.queryByText("Всё проверено")).toBeNull()
  })

  it("from a course card, shows only that course and points to the rest", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(
      run([
        work(),
        work({ id: "q1", kind: "quiz_answer", item_id: "qq", course_id: "c2", course_title: "Деяния", title: "Тест" }),
      ]),
    )
    renderAt("/teacher/review?course=c2")

    expect(await screen.findByText("Тест")).toBeInTheDocument()
    expect(screen.queryByText("Эссе про благодать")).toBeNull()
    expect(screen.getByRole("link", { name: "В других курсах ждёт ещё 1" })).toHaveAttribute("href", "/teacher/review")
  })

  it("marks one after another across courses, and «Назад» returns to the last with its mark", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(
      run([
        work({ content: "Первая работа", prompt: "<p>Напишите о благодати</p>" }),
        work({
          id: "q1",
          kind: "quiz_answer",
          item_id: "qq",
          course_id: "c2",
          course_title: "Деяния",
          title: "Тест",
          prompt: "Что такое благодать?",
          content: "Ответ на вопрос",
          max_points: 5,
        }),
      ]),
    )
    const grade = vi.spyOn(coursesService, "gradeSubmission").mockResolvedValue({} as never)
    const answer = vi.spyOn(quizzesService, "gradeQuizAnswer").mockResolvedValue({} as never)
    renderAt()
    await startRun()

    expect(await screen.findByText("Первая работа")).toBeInTheDocument()
    // The assignment's own instructions, as plain text.
    expect(screen.getByText("Напишите о благодати")).toBeInTheDocument()
    expect(screen.getByText("1 из 2")).toBeInTheDocument()
    await userEvent.type(screen.getByRole("spinbutton", { name: "Оценка" }), "90")
    await userEvent.click(screen.getByRole("button", { name: "Хорошо раскрыта тема." }))
    await userEvent.click(next())

    // The first save says it expects the work to be waiting still.
    expect(grade).toHaveBeenCalledWith(
      "s1",
      expect.objectContaining({ grade: 90, feedback: "Хорошо раскрыта тема.", expect_waiting: true }),
    )
    expect(await screen.findByText("Что такое благодать?")).toBeInTheDocument()
    expect(note()).toHaveValue("")
    await userEvent.click(screen.getByRole("button", { name: "4" }))

    await userEvent.click(screen.getByRole("button", { name: /Назад/ }))
    expect(await screen.findByText("Первая работа")).toBeInTheDocument()
    expect(screen.getByRole("spinbutton", { name: "Оценка" })).toHaveValue(90)
    expect(note()).toHaveValue("Хорошо раскрыта тема.")
    // Unchanged: «Дальше» moves on without sending it twice.
    await userEvent.click(next())
    expect(grade).toHaveBeenCalledTimes(1)

    await userEvent.click(screen.getByRole("button", { name: /Готово/ }))
    expect(answer).toHaveBeenCalledWith("q1", 4, null, { expectWaiting: true })
  })

  it("does not let a second tap clear a score that was already saved", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(
      run([work({ max_points: 5 }), work({ id: "s2", content: "Вторая", max_points: 5 })]),
    )
    vi.spyOn(coursesService, "gradeSubmission").mockResolvedValue({} as never)
    renderAt()
    await startRun()

    await userEvent.click(await screen.findByRole("button", { name: "3" }))
    await userEvent.click(next())
    await screen.findByText("Вторая")
    await userEvent.click(screen.getByRole("button", { name: /Назад/ }))

    const three = await screen.findByRole("button", { name: "3" })
    await userEvent.click(three)
    expect(three).toHaveAttribute("aria-pressed", "true")
  })

  it("skips untouched work, and asks for a score when only a note was written", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(
      run([
        work({ content: "", file_url: "https://drive.google.com/file/d/abc", max_points: 50 }),
        work({ id: "s2", content: "Вторая" }),
      ]),
    )
    const grade = vi.spyOn(coursesService, "gradeSubmission")
    renderAt()
    await startRun()

    expect(await screen.findByRole("link", { name: /файл/i })).toHaveAttribute("href", "https://drive.google.com/file/d/abc")
    await userEvent.type(screen.getByRole("spinbutton", { name: "Оценка" }), "60")
    expect(next()).toBeDisabled()
    expect(screen.getByRole("status")).toHaveTextContent("Не больше 50 баллов")

    await userEvent.clear(screen.getByRole("spinbutton", { name: "Оценка" }))
    await userEvent.type(note(), "Хорошо")
    // A note with no score would be lost: the button says what is missing.
    expect(next()).toBeDisabled()
    expect(screen.getByRole("status")).toHaveTextContent("Поставьте оценку")

    await userEvent.clear(note())
    expect(next()).toHaveTextContent("Пропустить")
    await userEvent.click(next())
    expect(await screen.findByText("Вторая")).toBeInTheDocument()
    expect(grade).not.toHaveBeenCalled()
  })

  it("says how many criteria are left, and does not count a mark from a swapped rubric", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(run([work()]))
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({
      rubric: RUBRIC,
      marks: [
        { criterion_id: "cr1", level_id: "l1", points: 5, comment: null },
        { criterion_id: "old", level_id: "lx", points: 5, comment: null },
      ],
      earned: null,
      out_of: 15,
    })
    renderAt()
    await startRun()

    expect(await screen.findByText("Выберите уровень по всем критериям: 1 из 3")).toBeInTheDocument()
    expect(next()).toBeDisabled()
  })

  it("lets the teacher move on when the rubric will not load", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(run([work(), work({ id: "s2", content: "Вторая" })]))
    vi.spyOn(rubricsService, "forSubmission").mockRejectedValueOnce(failure(500)).mockResolvedValue(NO_RUBRIC)
    renderAt()
    await startRun()

    expect(await screen.findByText("Не удалось загрузить рубрику")).toBeInTheDocument()
    expect(next()).toHaveTextContent("Пропустить")
    await userEvent.click(next())
    expect(await screen.findByText("Вторая")).toBeInTheDocument()
  })

  it("keeps the note the teacher typed when the rubric is asked for again", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(run([work()]))
    const rubric = vi
      .spyOn(rubricsService, "forSubmission")
      .mockRejectedValueOnce(failure(403))
      .mockResolvedValue(NO_RUBRIC)
    renderAt()
    await startRun()

    expect(await screen.findByText("Не удалось загрузить рубрику")).toBeInTheDocument()
    await userEvent.type(note(), "Хорошо, но коротко")
    await userEvent.click(screen.getByRole("button", { name: "Повторить" }))

    expect(await screen.findByRole("spinbutton", { name: "Оценка" })).toBeInTheDocument()
    expect(rubric).toHaveBeenCalledTimes(2)
    expect(note()).toHaveValue("Хорошо, но коротко")
  })

  it("waits for level taps in flight, and sends the finished grid once, with the note", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(run([work()]))
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({ rubric: RUBRIC, marks: [], earned: null, out_of: 15 })
    const releases: (() => void)[] = []
    const setMarks = vi.spyOn(rubricsService, "setMarks").mockImplementation(
      (_id, marks) =>
        new Promise((resolve) =>
          releases.push(() =>
            resolve({ rubric: RUBRIC, marks: marks.map((m) => ({ ...m, points: 5, comment: null })), earned: 10, out_of: 15 }),
          ),
        ),
    )
    renderAt()
    await startRun()

    await userEvent.click(await screen.findByRole("button", { name: /Да/ }))
    await userEvent.click(screen.getByRole("button", { name: /Ясно/ }))
    expect(setMarks).toHaveBeenCalledTimes(2)
    // The second request carries both marks, not only its own.
    expect(setMarks.mock.calls[1]?.[1].map((m) => m.criterion_id).sort()).toEqual(["cr1", "cr2"])
    // The tap that completes the grid is not sent on its own …
    await userEvent.click(screen.getByRole("button", { name: /Есть/ }))
    expect(setMarks).toHaveBeenCalledTimes(2)
    // … and «Дальше» waits while the earlier taps are still on their way.
    expect(next()).toBeDisabled()
    releases.forEach((release) => release())
    await waitFor(() => expect(next()).toBeEnabled())
    // The total counts the level not yet sent; late answers did not undo it.
    expect(screen.getByText("15 / 15")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: "Структура ясная." }))
    setMarks.mockResolvedValue({ rubric: RUBRIC, marks: [], earned: 15, out_of: 15 })
    await userEvent.click(next())
    expect(setMarks).toHaveBeenCalledTimes(3)
    expect(setMarks.mock.calls[2]?.[1]).toHaveLength(3)
    expect(setMarks.mock.calls[2]?.[2]).toBe("Структура ясная.")
    expect(setMarks.mock.calls[2]?.[3]).toEqual({ expectWaiting: true })
  })

  it("moves on with a plain word when somebody marked the work meanwhile", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(
      run([work({ max_points: 5 }), work({ id: "s2", content: "Вторая", max_points: 5 })]),
    )
    vi.spyOn(coursesService, "gradeSubmission").mockRejectedValue(failure(409))
    const toast = vi.spyOn(toastModule, "toast")
    renderAt()
    await startRun()

    await userEvent.click(await screen.findByRole("button", { name: "4" }))
    await userEvent.click(next())

    expect(await screen.findByText("Вторая")).toBeInTheDocument()
    expect(toast).toHaveBeenCalledWith({ title: "Эту работу уже проверили" })
  })

  it("puts ready comments in the student's language", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue(run([work({ student_locale: "en" })]))
    renderAt()
    await startRun()

    await userEvent.click(await screen.findByRole("button", { name: "You covered the topic well." }))
    expect(note()).toHaveValue("You covered the topic well.")
  })

  it("ends on «Всё проверено» once the last one is marked", async () => {
    const getRun = vi
      .spyOn(gradesService, "getRun")
      .mockResolvedValueOnce(run([work({ max_points: 5 })]))
      .mockResolvedValue(run([]))
    vi.spyOn(coursesService, "gradeSubmission").mockResolvedValue({} as never)
    renderAt()
    await startRun()

    await userEvent.click(await screen.findByRole("button", { name: "5" }))
    await userEvent.click(screen.getByRole("button", { name: /Готово/ }))

    expect(await screen.findByText("Всё проверено")).toBeInTheDocument()
    expect(screen.getByText("Только что проверено: 1")).toBeInTheDocument()
    // Asked again rather than assumed: the server says what is left.
    expect(getRun).toHaveBeenCalledTimes(2)
  })
})
