import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/hooks/useUserTour", () => ({ useUserTour: () => undefined }))
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "t1", role: "teacher" } }) }))

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import TeacherAnalytics from "../TeacherAnalytics"

describe("TeacherAnalytics", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
  })

  it("asks again from a failed load instead of only offering the way back", async () => {
    const read = vi
      .spyOn(coursesService, "getCourseAnalyticsAPI")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue({ total_students: 2, enrollments: [], avg_progress: 50, completion_count: 1, course_title: "Acts" } as never)
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={["/teacher/courses/k1/analytics"]}>
          <Routes>
            <Route path="/teacher/courses/:courseId/analytics" element={<TeacherAnalytics />} />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(await screen.findByRole("alert")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Try again" }))
    expect((await screen.findAllByText("Acts")).length).toBeGreaterThan(0)
    expect(read).toHaveBeenCalledTimes(2)
  })
})
