import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { gradesService } from "@/services/grades"
import { rubricsService } from "@/services/rubrics"
import GradingQueue from "../GradingQueue"
import type { WaitingGroup, WaitingSubmission } from "@/types"

function group(over: Partial<WaitingGroup> = {}): WaitingGroup {
  return {
    kind: "assignment",
    item_id: "a1",
    course_id: "c1",
    chapter_id: "ch1",
    title: "Эссе про благодать",
    waiting: 3,
    oldest: "2026-08-01T09:00:00Z",
    ...over,
  }
}

function work(over: Partial<WaitingSubmission> = {}): WaitingSubmission {
  return {
    submission_id: "s1",
    student_id: "st1",
    student_name: "Пётр Иванов",
    submitted_at: "2026-08-01T09:00:00Z",
    content: "Благодать — это незаслуженная милость",
    file_url: null,
    ...over,
  }
}

function forbidden() {
  return Object.assign(new Error("Forbidden"), {
    isAxiosError: true,
    response: { status: 403, data: {} },
  })
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("GradingQueue", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("lists the work waiting, with how many and how long", async () => {
    vi.spyOn(gradesService, "getQueue").mockResolvedValue([group()])
    render(<GradingQueue />, { wrapper: Wrapper })

    expect(await screen.findByText("Эссе про благодать")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
  })

  it("says so when there is nothing left", async () => {
    vi.spyOn(gradesService, "getQueue").mockResolvedValue([])
    render(<GradingQueue />, { wrapper: Wrapper })

    // A teacher who cleared the queue should be told, not shown a blank page
    // that reads as a failure to load.
    expect(await screen.findByText(/Всё проверено/)).toBeInTheDocument()
  })

  it("does not call a queue that failed to load «all marked»", async () => {
    vi.spyOn(gradesService, "getQueue").mockRejectedValue(forbidden())
    render(<GradingQueue />, { wrapper: Wrapper })

    // The refusal stays on screen with a way to try again — a toast would
    // have faded and left the reassuring empty state behind it.
    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("errors.byStatus.403"))
    expect(screen.getByRole("button", { name: i18n.t("common.tryAgain") })).toBeInTheDocument()
    expect(screen.queryByText(i18n.t("grading.emptyTitle"))).toBeNull()
  })

  it("does not call a task whose work failed to load «marked»", async () => {
    vi.spyOn(gradesService, "getQueue").mockResolvedValue([group()])
    vi.spyOn(gradesService, "getAssignmentQueue").mockRejectedValue(forbidden())
    render(<GradingQueue />, { wrapper: Wrapper })

    await userEvent.click(await screen.findByRole("button", { name: /Проверить/ }))

    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("errors.byStatus.403"))
    // The green tick was the screen a failed fetch used to land on.
    expect(screen.queryByText(i18n.t("grading.groupDoneTitle"))).toBeNull()
    expect(screen.getByRole("button", { name: i18n.t("common.tryAgain") })).toBeInTheDocument()
  })

  it("opens a task and shows one piece of work at a time, oldest first", async () => {
    vi.spyOn(gradesService, "getQueue").mockResolvedValue([group()])
    vi.spyOn(gradesService, "getAssignmentQueue").mockResolvedValue([
      work({ student_name: "Первый", content: "Раньше" }),
      work({ submission_id: "s2", student_name: "Второй", content: "Позже" }),
    ])
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({
      rubric: null,
      marks: [],
      earned: null,
      out_of: null,
    })
    render(<GradingQueue />, { wrapper: Wrapper })

    await userEvent.click(await screen.findByRole("button", { name: /Проверить/ }))

    expect(await screen.findByText("Раньше")).toBeInTheDocument()
    // Where you are, so «дальше» is a known distance rather than an open-ended
    // commitment on a Sunday evening.
    expect(screen.getByText("1 / 2")).toBeInTheDocument()
    expect(screen.queryByText("Позже")).not.toBeInTheDocument()
  })

  it("does not carry one student's note into the next essay", async () => {
    vi.spyOn(gradesService, "getQueue").mockResolvedValue([group()])
    vi.spyOn(gradesService, "getAssignmentQueue").mockResolvedValue([
      work({ student_name: "Первый", content: "Раньше" }),
      work({ submission_id: "s2", student_name: "Второй", content: "Позже" }),
    ])
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({
      rubric: null,
      marks: [],
      earned: null,
      out_of: null,
    })
    const grade = vi.spyOn((await import("@/services/courses")).coursesService, "gradeSubmission")
    grade.mockResolvedValue({} as never)
    render(<GradingQueue />, { wrapper: Wrapper })
    await userEvent.click(await screen.findByRole("button", { name: /Проверить/ }))

    const note = await screen.findByPlaceholderText(/Что удалось/)
    await userEvent.type(note, "Хорошая работа")
    await userEvent.type(screen.getByRole("spinbutton", { name: "Оценка" }), "90")
    await userEvent.click(screen.getByRole("button", { name: /Сохранить и дальше/ }))

    // The one mistake this screen must never make.
    expect(await screen.findByText("Позже")).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Что удалось/)).toHaveValue("")
    expect(screen.getByRole("spinbutton", { name: "Оценка" })).toHaveValue(null)
    expect(grade).toHaveBeenCalledWith("s1", expect.objectContaining({ grade: 90 }))
  })

  it("will not save an essay nobody has scored as a zero", async () => {
    vi.spyOn(gradesService, "getQueue").mockResolvedValue([group({ max_score: 50 })])
    vi.spyOn(gradesService, "getAssignmentQueue").mockResolvedValue([
      work({ content: "", file_url: "https://drive.google.com/file/d/abc" }),
    ])
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({ rubric: null, marks: [], earned: null, out_of: null })
    const grade = vi.spyOn((await import("@/services/courses")).coursesService, "gradeSubmission")
    render(<GradingQueue />, { wrapper: Wrapper })
    await userEvent.click(await screen.findByRole("button", { name: /Проверить/ }))

    // Work handed in as a document: the teacher can open it.
    expect(await screen.findByRole("link", { name: /файл/i })).toHaveAttribute("href", "https://drive.google.com/file/d/abc")
    const save = screen.getByRole("button", { name: /Сохранить и закончить/ })
    expect(save).toBeDisabled()
    // Out of what: the grade route refuses anything above it.
    expect(screen.getByText("из 50")).toBeInTheDocument()
    await userEvent.click(save)
    expect(grade).not.toHaveBeenCalled()
    await userEvent.type(screen.getByRole("spinbutton", { name: "Оценка" }), "0")
    expect(save).toBeEnabled()
    // Above the maximum: the route would refuse it, so the button does first.
    const box = screen.getByRole("spinbutton", { name: "Оценка" })
    await userEvent.clear(box)
    await userEvent.type(box, "60")
    expect(save).toBeDisabled()
  })

  it("does not move on from a rubric essay with no level chosen", async () => {
    vi.spyOn(gradesService, "getQueue").mockResolvedValue([group()])
    vi.spyOn(gradesService, "getAssignmentQueue").mockResolvedValue([work()])
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({
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
    })
    render(<GradingQueue />, { wrapper: Wrapper })
    await userEvent.click(await screen.findByRole("button", { name: /Проверить/ }))

    expect(await screen.findByRole("button", { name: /Сохранить и закончить/ })).toBeDisabled()
  })

  it("does not count a mark left from a rubric that was swapped out", async () => {
    vi.spyOn(gradesService, "getQueue").mockResolvedValue([group()])
    vi.spyOn(gradesService, "getAssignmentQueue").mockResolvedValue([work()])
    vi.spyOn(rubricsService, "forSubmission").mockResolvedValue({
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
      // A mark on a criterion of the rubric this assignment used to have.
      marks: [{ criterion_id: "old", level_id: "lx", points: 5, comment: null }],
      earned: null,
      out_of: 10,
    })
    render(<GradingQueue />, { wrapper: Wrapper })
    await userEvent.click(await screen.findByRole("button", { name: /Проверить/ }))

    expect(await screen.findByRole("button", { name: /Сохранить и закончить/ })).toBeDisabled()
  })
})
