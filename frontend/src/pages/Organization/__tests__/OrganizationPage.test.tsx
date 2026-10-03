import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
    },
  },
}))

import i18n from "@/i18n/config"
import { organizationsService, type OrganizationPage as Page } from "@/services/organizations"
import OrganizationPage from "../OrganizationPage"

const page = (over: Partial<Page> = {}): Page => ({
  slug: "ucoat", public_name: "UCOAT", country: "US", city: "Индианаполис", active: true, verified: true,
  description: "Библейский колледж.", logo_url: null, website_url: "https://ucoat.org",
  directors: [{ id: "d1", full_name: "Дмитрий Константинов", avatar_url: null }],
  stats: { courses: 3, lessons: 12, certificates: 2, members: null, teachers: null },
  courses: [], locked_courses: [{ id: "c2", title: "Курс проповеди — I", image_url: null }],
  viewer_is_member: false, viewer_can_edit: false, id: null, show_member_count: null,
  since: "2026-08-30T00:00:00Z", ...over,
})

function renderPage() {
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/o/ucoat"]}>
        <Routes>
          <Route path="/o/:slug" element={<OrganizationPage />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("an organization's page", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(async () => {
    vi.restoreAllMocks()
    await i18n.changeLanguage("en")
  })

  it("names its director, shows a closed course as a lock, and offers no edit to a visitor", async () => {
    vi.spyOn(organizationsService, "getPage").mockResolvedValue(page())
    renderPage()
    expect(await screen.findByRole("heading", { level: 1, name: "UCOAT" })).toBeInTheDocument()
    expect(screen.getByText("Дмитрий Константинов")).toBeInTheDocument()
    expect(screen.getByText("Курс проповеди — I")).toBeInTheDocument()
    expect(screen.getAllByText("По приглашению").length).toBeGreaterThan(0)
    expect(screen.queryByRole("button", { name: "Редактировать страницу" })).toBeNull()
    // No member count below the threshold: the server sent null.
    expect(screen.queryByText(/^участник/)).toBeNull()
  })

  it("shows how many teach there once the server sends the number", async () => {
    // The server computed ``stats.teachers`` and the page never rendered
    // it (2026-10-03). Same contract as members: null is "not shown".
    vi.spyOn(organizationsService, "getPage").mockResolvedValue(
      page({ stats: { courses: 3, lessons: 12, certificates: 2, members: 14, teachers: 5 } }),
    )
    renderPage()
    expect(await screen.findByText("5")).toBeInTheDocument()
    expect(screen.getByText("преподавателей")).toBeInTheDocument()
    expect(screen.getByText("участников")).toBeInTheDocument()
  })

  it("leaves out a count that is still zero", async () => {
    vi.spyOn(organizationsService, "getPage").mockResolvedValue(
      page({ stats: { courses: 3, lessons: 0, certificates: 0, members: null, teachers: null } }),
    )
    renderPage()
    expect(await screen.findByText("курса")).toBeInTheDocument()
    expect(screen.queryByText(/^уроков$/)).toBeNull()
    expect(screen.queryByText(/сертификатов выдано/)).toBeNull()
  })

  it("offers its director the edit form", async () => {
    vi.spyOn(organizationsService, "getPage").mockResolvedValue(page({ viewer_can_edit: true, id: "o1", show_member_count: true }))
    renderPage()
    expect(await screen.findByRole("button", { name: "Редактировать страницу" })).toBeInTheDocument()
  })
})
