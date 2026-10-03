/**
 * «Load more» belongs to the list it was pressed under. A page of the
 * previous search that arrived after the new one was appended to it: 25
 * cards under «x», one of them matching nothing (2026-10-03).
 */
import type { ReactNode } from "react"
import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import type { Course } from "@/types"
import CoursesPage from "../CoursesPage"

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: null, loading: false }) }))
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: () => undefined }))

const course = (id: string) =>
  ({ id, title: `Course ${id}`, description: null, image_url: null, status: "published", access_mode: "public" }) as Course

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/courses"]}>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("CoursesPage — load more", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
  })

  it("drops a page of the previous search that arrives late", async () => {
    let releaseStale: (rows: Course[]) => void = () => {}
    vi.spyOn(coursesService, "getCourses").mockImplementation(async (query, opts) => {
      if (query === "x") return [course("x-only")]
      if ((opts?.skip ?? 0) > 0) return new Promise<Course[]>((resolve) => (releaseStale = resolve))
      return Array.from({ length: 24 }, (_, i) => course(`first-${i}`))
    })
    const user = userEvent.setup()
    render(<CoursesPage />, { wrapper: Wrapper })

    await user.click(await screen.findByRole("button", { name: /Load more courses/i }))
    await user.type(screen.getByPlaceholderText(/Search courses/i), "x")
    await waitFor(() => expect(screen.getByText("Course x-only")).toBeInTheDocument(), { timeout: 3000 })

    await act(async () => releaseStale([course("stale-0")]))

    expect(screen.queryByText("Course stale-0")).not.toBeInTheDocument()
  })
})
