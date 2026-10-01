import { render, screen, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { analyticsService } from "@/services/analytics"

let role = "teacher"
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "u1", role } }) }))

import { TeacherAtRiskCard } from "../TeacherAtRiskCard"

function show() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <TeacherAtRiskCard />
      </MemoryRouter>
    </I18nextProvider>,
  )
}

const rows = [
  { student_id: "s1", full_name: "Мария", course_id: "c1", course_title: "Деяния", last_activity: "", quiet_days: 1, missed_deadlines: 2 },
  { student_id: "s2", full_name: "Иван", course_id: "c1", course_title: "Деяния", last_activity: "", quiet_days: 10, missed_deadlines: 0 },
]

/** The students to write to this week — a nudge, so nothing when there is nobody. */
describe("TeacherAtRiskCard", () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    role = "teacher"
    await i18n.changeLanguage("ru")
  })

  it("names who and why, and opens the course's progress board", async () => {
    vi.spyOn(analyticsService, "getStudentsAtRisk").mockResolvedValue(rows)
    show()
    const maria = await screen.findByRole("link", { name: /Мария/ })
    expect(maria).toHaveAttribute("href", "/teacher/courses/c1/progress")
    expect(maria).toHaveTextContent(i18n.t("dashboard.atRisk.missed", { count: 2 }))
    expect(screen.getByRole("link", { name: /Иван/ })).toHaveTextContent(i18n.t("dashboard.atRisk.quiet", { count: 10 }))
  })

  it("says nothing when nobody is slipping, and nothing to a student", async () => {
    const spy = vi.spyOn(analyticsService, "getStudentsAtRisk").mockResolvedValue([])
    const { container, unmount } = show()
    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
    unmount()
    role = "student"
    spy.mockClear()
    const again = show()
    expect(again.container).toBeEmptyDOMElement()
    expect(spy).not.toHaveBeenCalled()
  })
})
