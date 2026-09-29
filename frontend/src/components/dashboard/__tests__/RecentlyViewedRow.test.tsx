import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { RECENT_ROW_SIZE, RecentlyViewedRow } from "../RecentlyViewedRow"

const getMyCoursesMock = vi.fn()
vi.mock("@/services/courses", () => ({
  coursesService: { getMyCourses: (...args: unknown[]) => getMyCoursesMock(...args) },
}))
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "u-1" } }) }))

const getRecentCoursesMock = vi.fn()
vi.mock("@/lib/recentlyViewed", () => ({
  getRecentCourses: () => getRecentCoursesMock(),
}))

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

const enrolled = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    id: `e-${i}`,
    course_id: `c-${i}`,
    course: { id: `c-${i}`, title: `Course ${i}`, image_url: null },
  }))

describe("RecentlyViewedRow", () => {
  beforeEach(() => {
    getMyCoursesMock.mockReset()
    getRecentCoursesMock.mockReset()
  })

  it("stays hidden below a full row — no strip of one tile and empty space", async () => {
    const four = enrolled(RECENT_ROW_SIZE - 1)
    getMyCoursesMock.mockResolvedValue(four)
    getRecentCoursesMock.mockReturnValue(four.map((e) => ({ id: e.course.id })))

    render(<RecentlyViewedRow />, { wrapper: Wrapper })

    await waitFor(() => expect(getMyCoursesMock).toHaveBeenCalled())
    // Let the resolved fetch render before asserting absence.
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByRole("list")).not.toBeInTheDocument()
  })

  it("shows exactly a full row once there are enough", async () => {
    const seven = enrolled(RECENT_ROW_SIZE + 2)
    getMyCoursesMock.mockResolvedValue(seven)
    getRecentCoursesMock.mockReturnValue(seven.map((e) => ({ id: e.course.id })))

    render(<RecentlyViewedRow />, { wrapper: Wrapper })

    const links = await screen.findAllByRole("link")
    expect(links).toHaveLength(RECENT_ROW_SIZE)
    expect(links[0]).toHaveAttribute("href", "/courses/c-0")
  })

  it("counts only courses still enrolled in", async () => {
    getMyCoursesMock.mockResolvedValue(enrolled(3))
    getRecentCoursesMock.mockReturnValue(
      ["c-0", "c-1", "c-2", "gone-1", "gone-2"].map((id) => ({ id })),
    )

    render(<RecentlyViewedRow />, { wrapper: Wrapper })

    await waitFor(() => expect(getMyCoursesMock).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByRole("list")).not.toBeInTheDocument()
  })
})
