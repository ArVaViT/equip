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

    await userEvent.click(await screen.findByRole("button", { name: /Проверять/ }))

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
    await userEvent.click(await screen.findByRole("button", { name: /Проверять/ }))

    const note = await screen.findByPlaceholderText(/Что удалось/)
    await userEvent.type(note, "Хорошая работа")
    await userEvent.click(screen.getByRole("button", { name: /Сохранить и дальше/ }))

    // The one mistake this screen must never make.
    expect(await screen.findByText("Позже")).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Что удалось/)).toHaveValue("")
  })
})
