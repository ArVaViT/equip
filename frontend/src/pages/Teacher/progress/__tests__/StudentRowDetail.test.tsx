import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { StudentRow } from "../StudentRow"
import type { StudentData } from "../helpers"

const getStudentProgressDetail = vi.fn()
vi.mock("@/services/courses", () => ({
  coursesService: {
    getStudentProgressDetail: (...args: unknown[]) => getStudentProgressDetail(...args),
  },
}))
vi.mock("@/services/grades", () => ({
  gradesService: { getGradeHistory: vi.fn().mockResolvedValue([]) },
}))

function makeStudent(): StudentData {
  return {
    id: "s-1",
    full_name: "Anna Petrenko-Vasylenko-Shevchenko",
    email: "anna@example.com",
    progress: 50,
    chapters_completed: 2,
    total_chapters: 4,
    quiz_avg: null,
    assignment_avg: null,
    last_activity: null,
    enrolled_at: "2026-09-20T00:00:00Z",
    overall_grade: null,
    current_grade: null,
    current_letter_grade: null,
    scores_differ: false,
    manual_grade: null,
    result_state: "not_graded_yet",
    letter_grade: null,
  }
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <table>
          <tbody>{children}</tbody>
        </table>
      </MemoryRouter>
    </I18nextProvider>
  )
}

function show() {
  return render(
    <StudentRow
      student={makeStudent()}
      isExpanded
      onToggle={vi.fn()}
      quizAvg={null}
      assignmentAvg={null}
      courseId="c-1"
      onChapterUpdate={vi.fn()}
    />,
    { wrapper: Wrapper },
  )
}

describe("StudentRow — opening a student", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    getStudentProgressDetail.mockReset()
  })

  it("shows the lesson breakdown once it arrives, instead of loading for ever", async () => {
    getStudentProgressDetail.mockResolvedValue({
      student_id: "s-1",
      chapters: [{ id: "ch-1", title: "Lesson one", completed: true, completed_by: "self" }],
      quiz_results: [],
      assignment_results: [],
    })
    show()

    // An h3: the row sits in the students' card, whose title is the page's h2.
    expect(
      await screen.findByRole("heading", { level: 3, name: i18n.t("studentProgress.row.chapterBreakdown") }),
    ).toBeInTheDocument()
    expect(screen.queryByText(i18n.t("studentProgress.row.loadingDetail"))).not.toBeInTheDocument()
    expect(getStudentProgressDetail).toHaveBeenCalledTimes(1)
  })
})

describe("StudentRow — on a phone", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    getStudentProgressDetail.mockReset()
    getStudentProgressDetail.mockResolvedValue({ student_id: "s-1", chapters: [], quiz_results: [], assignment_results: [] })
  })

  function showAsListItem(expanded: boolean) {
    return render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <ul>
            <StudentRow
              layout="list"
              student={makeStudent()}
              isExpanded={expanded}
              onToggle={vi.fn()}
              quizAvg={null}
              assignmentAvg={null}
              courseId="c-1"
              onChapterUpdate={vi.fn()}
            />
          </ul>
        </MemoryRouter>
      </I18nextProvider>,
    )
  }

  it("is one button: the name on one line, the progress, a chevron — no address, no table", () => {
    showAsListItem(false)
    const row = screen.getByRole("button", { expanded: false })
    expect(row.querySelector(".truncate")).toHaveTextContent("Anna Petrenko-Vasylenko-Shevchenko")
    expect(row).toHaveTextContent("50%")
    expect(screen.queryByText("anna@example.com")).not.toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("opens into the details, which carry what the row leaves out", async () => {
    showAsListItem(true)
    expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument()
    expect(screen.getByText("anna@example.com")).toBeInTheDocument()
    expect(screen.getByText(i18n.t("studentProgress.table.lastActive"))).toBeInTheDocument()
  })
})
