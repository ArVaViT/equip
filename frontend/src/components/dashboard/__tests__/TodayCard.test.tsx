import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { TodayCard } from "../TodayCard"

const getCalendarEventsMock = vi.fn()
vi.mock("@/services/courses", () => ({
  coursesService: {
    getCalendarEvents: (...args: unknown[]) => getCalendarEventsMock(...args),
  },
}))

const useAuthMock = vi.fn()
vi.mock("@/context/useAuth", () => ({
  useAuth: () => useAuthMock(),
}))

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function makeEvent(overrides: Partial<{ id: string; title: string; event_date: string; course_title: string | null }> = {}) {
  return {
    id: overrides.id ?? "e-1",
    title: overrides.title ?? "Assignment due",
    description: null,
    event_type: "assignment" as const,
    event_date: overrides.event_date ?? new Date().toISOString(),
    course_id: "c-1",
    course_title: overrides.course_title ?? "Acts of the Apostles",
    source: "assignment" as const,
  }
}

describe("TodayCard", () => {
  beforeEach(() => {
    getCalendarEventsMock.mockReset()
    useAuthMock.mockReset()
  })

  it("renders the 'open full calendar' link to /calendar", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    getCalendarEventsMock.mockResolvedValueOnce([])

    render(<TodayCard />, { wrapper: Wrapper })

    const link = screen.getByRole("link", { name: /full calendar|календарь/i })
    expect(link).toHaveAttribute("href", "/calendar")
  })

  it("lists today's events with title + course", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    getCalendarEventsMock.mockResolvedValueOnce([
      makeEvent({ title: "Read Acts 1", course_title: "Acts course" }),
    ])

    render(<TodayCard />, { wrapper: Wrapper })

    await waitFor(() => expect(screen.getByText("Read Acts 1")).toBeInTheDocument())
    expect(screen.getByText("Acts course")).toBeInTheDocument()
  })

  it("renders empty-state copy when no events fall on today", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    // Event date one week from now -> not today
    const future = new Date()
    future.setDate(future.getDate() + 7)
    getCalendarEventsMock.mockResolvedValueOnce([makeEvent({ event_date: future.toISOString() })])

    render(<TodayCard />, { wrapper: Wrapper })

    await waitFor(() =>
      expect(screen.getByText(/no events|нет событий/i)).toBeInTheDocument(),
    )
  })

  it("caps the visible list at MAX_EVENTS_SHOWN (3)", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    const today = new Date().toISOString()
    getCalendarEventsMock.mockResolvedValueOnce([
      makeEvent({ id: "1", title: "One", event_date: today }),
      makeEvent({ id: "2", title: "Two", event_date: today }),
      makeEvent({ id: "3", title: "Three", event_date: today }),
      makeEvent({ id: "4", title: "Four", event_date: today }),
      makeEvent({ id: "5", title: "Five", event_date: today }),
    ])

    render(<TodayCard />, { wrapper: Wrapper })

    await waitFor(() => expect(screen.getByText("One")).toBeInTheDocument())
    const items = screen.getAllByRole("listitem")
    expect(items).toHaveLength(3)
  })

  it("raises the first letter of the date, not every word", async () => {
    // The date read "Понедельник, 31 Августа" in production: the heading
    // carried CSS `capitalize`, which raises every word, and Russian writes
    // month names in lower case. Ukrainian had it too ("31 Серпня"), and the
    // month picker went further — "август 2026 г." became "Август 2026 Г.".
    //
    // jsdom applies no stylesheet, so `text-transform` cannot be observed
    // here; the class list is what decides it, and that is what is asserted.
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    getCalendarEventsMock.mockResolvedValueOnce([])

    render(<TodayCard />, { wrapper: Wrapper })

    const heading = await screen.findByRole("heading", { level: 2 })
    expect(heading.className).not.toContain("capitalize")
    expect(heading.className).toContain("first-letter:uppercase")
  })

  it("does NOT fetch events for unauthenticated visitors", () => {
    useAuthMock.mockReturnValue({ user: null })
    render(<TodayCard />, { wrapper: Wrapper })
    expect(getCalendarEventsMock).not.toHaveBeenCalled()
  })
})
