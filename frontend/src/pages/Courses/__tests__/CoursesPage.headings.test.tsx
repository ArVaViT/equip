/**
 * The catalogue's outline. A card straight under the page's h1 is an h2.
 * When the reader's organizations have sections of their own — each an h2,
 * then the «Open catalogue» h2 before the public grid — the cards under
 * them are h3: a card is never at the level of the heading that names its
 * section (2026-10-19).
 */
import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import { organizationsService } from "@/services/organizations"
import type { Course } from "@/types"
import CoursesPage from "../CoursesPage"

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "u-1", role: "student" }, loading: false }) }))
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: () => undefined }))

const course = (id: string, title: string, access_mode: "public" | "institute" = "public") =>
  ({ id, title, description: null, image_url: null, status: "published", access_mode }) as Course

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/courses"]}>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("CoursesPage — heading levels", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
    vi.spyOn(coursesService, "getCourses").mockResolvedValue([course("c-1", "Genesis")])
    vi.spyOn(coursesService, "getMyCourses").mockResolvedValue([])
  })

  it("a card straight under the page's h1 is an h2", async () => {
    vi.spyOn(organizationsService, "mine").mockResolvedValue([])
    render(<CoursesPage />, { wrapper: Wrapper })

    expect(await screen.findByRole("heading", { level: 2, name: "Genesis" })).toBeInTheDocument()
  })

  it("under the organization sections every card is an h3, beneath its section's h2", async () => {
    vi.spyOn(organizationsService, "mine").mockResolvedValue([
      {
        organization_id: "o-1",
        organization_slug: "ucoat",
        organization_name: "UCOAT",
        role: "student",
        courses: [course("c-2", "Preaching", "institute")],
      },
    ])
    render(<CoursesPage />, { wrapper: Wrapper })

    expect(await screen.findByRole("heading", { level: 3, name: "Preaching" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 2, name: "UCOAT" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 2, name: "Open catalogue" })).toBeInTheDocument()
    expect(await screen.findByRole("heading", { level: 3, name: "Genesis" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { level: 2, name: "Genesis" })).not.toBeInTheDocument()
  })
})
