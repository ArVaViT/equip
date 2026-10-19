/**
 * A summary that could not be read is not a class with nobody in it.
 *
 * Answered with `null`, a 500 or a dropped connection rendered «No students
 * enrolled» and the default 40/60 weights in an editable card — one «Save»
 * away from writing the defaults over the course's real configuration.
 */
import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "t1", role: "teacher" } }) }))
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: () => undefined }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import TeacherGradebook from "../TeacherGradebook"

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/teacher/courses/k1/gradebook"]}>
        <Routes>
          <Route path="/teacher/courses/:courseId/gradebook" element={children} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>
  )
}

describe("TeacherGradebook when the summary cannot be read", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
    vi.spyOn(coursesService, "getCourse").mockResolvedValue({ id: "k1", title: "Acts" } as never)
    vi.spyOn(coursesService, "getCourseGrades").mockResolvedValue([])
    vi.spyOn(coursesService, "getGradebookMatrix").mockResolvedValue(null as never)
  })

  it("shows the failure with a retry, not an empty class with editable default weights", async () => {
    const summary = vi
      .spyOn(coursesService, "getGradeSummary")
      .mockRejectedValueOnce(
        Object.assign(new Error("Server Error"), { isAxiosError: true, response: { status: 500, data: {} } }),
      )
      .mockResolvedValue({
        course_id: "k1",
        config: { quiz_weight: 70, assignment_weight: 30, participation_weight: 0 },
        students: [],
        class_average: null,
      } as never)
    render(<TeacherGradebook />, { wrapper: Wrapper })

    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.queryByText(/No students enrolled/i)).toBeNull()

    await userEvent.click(screen.getByRole("button", { name: "Try again" }))
    expect((await screen.findAllByText("Acts")).length).toBeGreaterThan(0)
    expect(summary).toHaveBeenCalledTimes(2)
  })
})
