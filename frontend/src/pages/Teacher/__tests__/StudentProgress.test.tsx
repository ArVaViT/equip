import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type { StudentProgressEntry, StudentProgressResponse } from "@/types"
import StudentProgress from "../StudentProgress"

const getStudentProgress = vi.fn<(courseId: string) => Promise<StudentProgressResponse>>()

vi.mock("@/services/courses", () => ({
  coursesService: {
    getStudentProgress: (courseId: string) => getStudentProgress(courseId),
    getStudentProgressDetail: vi.fn(),
  },
}))
vi.mock("@/services/grades", () => ({
  gradesService: { getRetakeRequests: vi.fn().mockResolvedValue([]) },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

function board(students: StudentProgressEntry[]): StudentProgressResponse {
  return {
    course_id: "c-1",
    course_title: "Teaching Course - I",
    total_chapters: 4,
    total_students: students.length,
    modules: [],
    students,
  }
}

function student(overrides: Partial<StudentProgressEntry> = {}): StudentProgressEntry {
  return {
    id: "s-1",
    full_name: "Anna Petrenko",
    email: "anna@example.com",
    enrolled_at: "2026-09-20T00:00:00Z",
    progress: 0,
    chapters_completed: 0,
    total_chapters: 4,
    quiz_avg: null,
    assignment_avg: null,
    overall_grade: null,
    current_grade: null,
    current_letter_grade: null,
    scores_differ: false,
    manual_grade: null,
    result_state: "not_graded_yet",
    letter_grade: null,
    last_activity: null,
    ...overrides,
  }
}

function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/teacher/courses/c-1/progress"]}>
        <Routes>
          <Route path="/teacher/courses/:courseId/progress" element={<StudentProgress />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("StudentProgress — a course nobody has enrolled in yet", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    getStudentProgress.mockReset()
  })

  it("says so once, instead of three zeros, a search box and an empty table", async () => {
    getStudentProgress.mockResolvedValue(board([]))
    renderPage()

    expect(await screen.findByText(i18n.t("studentProgress.table.emptyNoStudents"))).toBeInTheDocument()
    expect(screen.queryByText(i18n.t("studentProgress.stats.averageProgress"))).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText(i18n.t("studentProgress.searchPlaceholder"))).not.toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("lists the students once there are some", async () => {
    getStudentProgress.mockResolvedValue(board([student()]))
    renderPage()

    expect(await screen.findByText("Anna Petrenko")).toBeInTheDocument()
    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.queryByText(i18n.t("studentProgress.table.emptyNoStudents"))).not.toBeInTheDocument()
  })
})

describe("StudentProgress — a small class on a phone", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    getStudentProgress.mockReset()
  })

  it("does not put a search box or a third tile between the teacher and three names", async () => {
    const three = [1, 2, 3].map((i) => student({ id: `s-${i}`, full_name: `Student ${i}` }))
    getStudentProgress.mockResolvedValue(board(three))
    renderPage()

    expect(await screen.findByText("Student 1")).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(i18n.t("studentProgress.searchPlaceholder"))).not.toBeInTheDocument()
    expect(screen.getByText(i18n.t("studentProgress.stats.averageProgress"))).toBeInTheDocument()
  })

  it("offers search once the class is bigger than that", async () => {
    const four = [1, 2, 3, 4].map((i) => student({ id: `s-${i}`, full_name: `Student ${i}` }))
    getStudentProgress.mockResolvedValue(board(four))
    renderPage()

    expect(await screen.findByText("Student 4")).toBeInTheDocument()
    expect(screen.getByPlaceholderText(i18n.t("studentProgress.searchPlaceholder"))).toBeInTheDocument()
  })
})
