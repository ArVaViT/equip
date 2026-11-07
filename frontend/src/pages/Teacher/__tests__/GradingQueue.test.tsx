import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
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
    submitted_at: "2026-08-01T09:00:00Z",
    content: "Благодать — это незаслуженная милость",
    file_url: null,
    max_points: 100,
    is_late: false,
    ...over,
  }
}

const NO_RUBRIC: SubmissionRubric = { rubric: null, marks: [], earned: null, out_of: null }

const ONE_CRITERION: SubmissionRubric = {
  rubric: {
    id: "r1",
    course_id: "c1",
    title: "Эссе",
    max_score: 10,
    criteria: [
      {
        id: "cr1",
        title: "Аргумент опирается на текст",
        description: null,
        order_index: 0,
        levels: [{ id: "l1", label: "Да", points: 10, description: null, order_index: 0 }],
      },
    ],
  },
  marks: [],
  earned: null,
  out_of: 10,
}

function forbidden() {
  return Object.assign(new Error("Forbidden"), {
    isAxiosError: true,
    response: { status: 403, data: {} },
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
    vi.spyOn(gradesService, "getRun").mockResolvedValue([
      work(),
      work({ id: "s2", student_name: "Анна" }),
      work({ id: "q1", kind: "quiz_answer", item_id: "qq", course_id: "c2", course_title: "Деяния", title: "Тест" }),
    ])
    renderAt()

    expect(await screen.findByText("3 работы ждут")).toBeInTheDocument()
    expect(screen.getByText("Эссе про благодать")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("Тест")).toBeInTheDocument()
    expect(screen.getByText(/Деяния/)).toBeInTheDocument()
  })

  it("says «Всё проверено» when nothing is waiting, with a way back", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue([])
    renderAt()

    expect(await screen.findByText("Всё проверено")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "На главную" })).toHaveAttribute("href", "/teacher")
  })

  it("does not call a run that failed to load «all marked»", async () => {
    vi.spyOn(gradesService, "getRun").mockRejectedValue(forbidden())
    renderAt()

    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("errors.byStatus.403"))
    expect(screen.getByRole("button", { name: i18n.t("common.tryAgain") })).toBeInTheDocument()
    expect(screen.queryByText("Всё проверено")).toBeNull()
  })

  it("from a course card, shows only that course and points to the rest", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue([
      work(),
      work({ id: "q1", kind: "quiz_answer", item_id: "qq", course_id: "c2", course_title: "Деяния", title: "Тест" }),
    ])
    renderAt("/teacher/review?course=c2")

    expect(await screen.findByText("Тест")).toBeInTheDocument()
    expect(screen.queryByText("Эссе про благодать")).toBeNull()
    expect(screen.getByRole("link", { name: "В других курсах ждёт ещё 1" })).toHaveAttribute("href", "/teacher/review")
  })

  it("marks one after another across courses, and «Назад» returns to the last with its mark", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue([
      work({ content: "Первая работа" }),
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
    ])
    const grade = vi.spyOn(coursesService, "gradeSubmission").mockResolvedValue({} as never)
    const answer = vi.spyOn(quizzesService, "gradeQuizAnswer").mockResolvedValue({} as never)
    renderAt()
    await startRun()

    expect(await screen.findByText("Первая работа")).toBeInTheDocument()
    expect(screen.getByText("1 из 2")).toBeInTheDocument()
    await userEvent.type(screen.getByRole("spinbutton", { name: "Оценка" }), "90")
    await userEvent.click(screen.getByRole("button", { name: "Хорошо раскрыта тема." }))
    await userEvent.click(next())

    expect(grade).toHaveBeenCalledWith("s1", expect.objectContaining({ grade: 90, feedback: "Хорошо раскрыта тема." }))
    // The question, beside the answer to it.
    expect(await screen.findByText("Что такое благодать?")).toBeInTheDocument()
    // The previous student's note never follows into the next work.
    expect(note()).toHaveValue("")
    // Up to ten points the mark is a row of buttons, not a keyboard.
    await userEvent.click(screen.getByRole("button", { name: "4" }))

    await userEvent.click(screen.getByRole("button", { name: /Назад/ }))
    expect(await screen.findByText("Первая работа")).toBeInTheDocument()
    expect(screen.getByRole("spinbutton", { name: "Оценка" })).toHaveValue(90)
    expect(note()).toHaveValue("Хорошо раскрыта тема.")
    // Unchanged: «Дальше» moves on without sending it twice.
    await userEvent.click(next())
    expect(grade).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("button", { name: "4" })).toHaveAttribute("aria-pressed", "true")

    await userEvent.click(screen.getByRole("button", { name: /Готово/ }))
    expect(answer).toHaveBeenCalledWith("q1", 4, null)
  })

  it("will not save work nobody has scored as a zero — it skips it instead", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue([
      work({ content: "", file_url: "https://drive.google.com/file/d/abc", max_points: 50 }),
      work({ id: "s2", content: "Вторая" }),
    ])
    const grade = vi.spyOn(coursesService, "gradeSubmission")
    renderAt()
    await startRun()

    expect(await screen.findByRole("link", { name: /файл/i })).toHaveAttribute("href", "https://drive.google.com/file/d/abc")
    expect(screen.getByText("из 50")).toBeInTheDocument()
    // Above the maximum: the route would refuse it, so the button does first.
    await userEvent.type(screen.getByRole("spinbutton", { name: "Оценка" }), "60")
    expect(next()).toBeDisabled()
    await userEvent.clear(screen.getByRole("spinbutton", { name: "Оценка" }))
    expect(next()).toHaveTextContent("Пропустить")
    await userEvent.click(next())

    expect(await screen.findByText("Вторая")).toBeInTheDocument()
    expect(grade).not.toHaveBeenCalled()
  })

  it("does not move on from a rubric half-chosen, nor count a mark left from a swapped rubric", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue([work()])
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({
      ...ONE_CRITERION,
      rubric: {
        ...ONE_CRITERION.rubric!,
        criteria: [
          ...ONE_CRITERION.rubric!.criteria,
          {
            id: "cr2",
            title: "Ясность",
            description: null,
            order_index: 1,
            levels: [{ id: "l2", label: "Ясно", points: 5, description: null, order_index: 0 }],
          },
        ],
      },
      // One chosen, plus a mark from the rubric this assignment used to have.
      marks: [
        { criterion_id: "cr1", level_id: "l1", points: 10, comment: null },
        { criterion_id: "old", level_id: "lx", points: 5, comment: null },
      ],
    })
    renderAt()
    await startRun()

    await waitFor(() => expect(next()).toBeDisabled())
  })

  it("keeps the note the teacher typed when the rubric is asked for again", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue([work()])
    const rubric = vi
      .spyOn(rubricsService, "forSubmission")
      .mockRejectedValueOnce(forbidden())
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

  it("keeps the first criterion's mark when the second is tapped before the first was answered", async () => {
    vi.spyOn(gradesService, "getRun").mockResolvedValue([work()])
    const level = (id: string, label: string) => ({ id, label, points: 5, description: null, order_index: 0 })
    const twoCriteria = {
      id: "r1",
      course_id: "c1",
      title: "Эссе",
      max_score: 10,
      criteria: [
        { id: "cr1", title: "Опора на текст", description: null, order_index: 0, levels: [level("l1", "Да")] },
        { id: "cr2", title: "Ясность", description: null, order_index: 1, levels: [level("l2", "Ясно")] },
      ],
    }
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({ rubric: twoCriteria, marks: [], earned: null, out_of: 10 })
    const releases: (() => void)[] = []
    const setMarks = vi.spyOn(rubricsService, "setMarks").mockImplementation(
      (_id, marks) =>
        new Promise((resolve) =>
          releases.push(() =>
            resolve({ rubric: twoCriteria, marks: marks.map((m) => ({ ...m, points: 5, comment: null })), earned: 10, out_of: 10 }),
          ),
        ),
    )
    renderAt()
    await startRun()

    await userEvent.click(await screen.findByRole("button", { name: /Да/ }))
    await userEvent.click(screen.getByRole("button", { name: /Ясно/ }))
    expect(setMarks).toHaveBeenCalledTimes(2)
    expect(setMarks.mock.calls[1]?.[1].map((m) => m.criterion_id).sort()).toEqual(["cr1", "cr2"])
    releases.forEach((release) => release())
    await waitFor(() => expect(screen.getByRole("button", { name: /Готово/ })).toBeEnabled())
  })

  it("ends on «Всё проверено» once the last one is marked", async () => {
    const run = vi
      .spyOn(gradesService, "getRun")
      .mockResolvedValueOnce([work({ max_points: 5 })])
      .mockResolvedValue([])
    vi.spyOn(coursesService, "gradeSubmission").mockResolvedValue({} as never)
    renderAt()
    await startRun()

    await userEvent.click(await screen.findByRole("button", { name: "5" }))
    await userEvent.click(screen.getByRole("button", { name: /Готово/ }))

    expect(await screen.findByText("Всё проверено")).toBeInTheDocument()
    expect(screen.getByText("Только что проверено: 1")).toBeInTheDocument()
    // Asked again rather than assumed: the server says what is left.
    expect(run).toHaveBeenCalledTimes(2)
  })
})
