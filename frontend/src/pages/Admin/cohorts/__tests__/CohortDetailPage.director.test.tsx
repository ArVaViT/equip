import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { cohortsService } from "@/services/cohorts"

const auth = vi.hoisted(() => ({ role: "director" as string }))
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: { id: "d1", role: auth.role, email: "d@example.com" }, loading: false }),
}))

import CohortDetailPage from "../CohortDetailPage"

function open() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/admin/cohorts/k1"]}>
        <Routes>
          <Route path="/admin/cohorts/:cohortId" element={<CohortDetailPage />} />
          <Route path="/" element={<p>home</p>} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("a cohort's page", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
    vi.spyOn(cohortsService, "getCohort").mockResolvedValue({
      id: "k1",
      name: "Осень 2026",
      start_date: "2026-10-01",
      end_date: "2026-12-20",
      enrollment_start: null,
      enrollment_end: null,
      status: "active",
      max_students: null,
      created_by: null,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: null,
      course_ids: [],
    } as never)
    vi.spyOn(cohortsService, "listCohortStudents").mockResolvedValue([])
  })

  it("opens for the school's director, who reached it from the cohorts tab", async () => {
    auth.role = "director"
    open()
    expect((await screen.findAllByText("Осень 2026")).length).toBeGreaterThan(0)
    expect(screen.queryByText("home")).not.toBeInTheDocument()
    // An active cohort still takes students and courses.
    expect(screen.getAllByRole("button", { name: /Добавить студента/ }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole("button", { name: /Добавить курс/ }).length).toBeGreaterThan(0)
  })

  it("is still closed to a teacher", () => {
    auth.role = "teacher"
    open()
    expect(screen.getByText("home")).toBeInTheDocument()
    expect(cohortsService.getCohort).not.toHaveBeenCalled()
  })

  it("offers nothing to add once the cohort is completed", async () => {
    auth.role = "director"
    vi.mocked(cohortsService.getCohort).mockResolvedValue({
      id: "k1",
      name: "Весна 2026",
      start_date: "2026-02-01",
      end_date: "2026-05-20",
      enrollment_start: null,
      enrollment_end: null,
      status: "completed",
      max_students: null,
      created_by: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: null,
      course_ids: [],
    } as never)
    open()
    expect((await screen.findAllByText("Весна 2026")).length).toBeGreaterThan(0)
    expect(screen.queryByRole("button", { name: /Добавить студента/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Добавить курс/ })).not.toBeInTheDocument()
  })
})
