import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import { tabsFor } from "../dashboard/constants"

const auth = vi.hoisted(() => ({ role: "director" as string }))
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: { id: "d1", role: auth.role, email: "d@example.com" }, loading: false }),
}))
vi.mock("../cohorts/CohortsTab", () => ({ CohortsTab: () => <p>cohorts list</p> }))

import AdminDashboard from "../AdminDashboard"

function Wrapper({ path, children }: { path: string; children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("a director in /admin", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    auth.role = "director"
    vi.restoreAllMocks()
  })

  it("is given the school's tabs, not the platform's", () => {
    expect(tabsFor("director")).toEqual(["cohorts", "invitations", "school"])
    expect(tabsFor("admin")).toContain("audit")
  })

  it("lands on cohorts, even from a link to a staff-only tab, and sees certificates to sign without a reject button", async () => {
    const certs = vi.spyOn(coursesService, "getAdminPendingCerts").mockResolvedValue([
      {
        id: "c1",
        student_name: "Мария Коваль",
        course_title: "Деяния апостолов",
        requested_at: "2026-10-01T00:00:00Z",
        teacher_approved_at: "2026-10-02T00:00:00Z",
        teacher_approver_name: "Иван Петренко",
      } as never,
    ])
    const users = vi.spyOn(coursesService, "getAllUsers")
    render(
      <Wrapper path="/admin?tab=audit">
        <AdminDashboard />
      </Wrapper>,
    )

    expect(await screen.findByText("cohorts list")).toBeInTheDocument()
    const tabs = screen.getAllByRole("tab").map((t) => t.id)
    expect(tabs).toEqual(["admin-tab-cohorts", "admin-tab-invitations", "admin-tab-school"])
    expect(await screen.findByText("Мария Коваль")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Отклонить/ })).not.toBeInTheDocument()
    expect(certs).toHaveBeenCalled()
    // The user list is staff-only; a director's page never asks for it.
    expect(users).not.toHaveBeenCalled()
  })

  it("is not for a teacher", () => {
    auth.role = "teacher"
    render(
      <Wrapper path="/admin">
        <AdminDashboard />
      </Wrapper>,
    )
    expect(screen.queryByRole("tab")).not.toBeInTheDocument()
  })
})
