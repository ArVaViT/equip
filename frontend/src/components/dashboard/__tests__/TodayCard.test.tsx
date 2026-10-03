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

function makeEvent(
  overrides: Partial<{
    id: string
    title: string
    event_date: string
    course_title: string | null
    event_type: string
    duration_minutes: number
    recording_url: string
  }> = {},
) {
  return {
    id: overrides.id ?? "e-1",
    title: overrides.title ?? "Assignment due",
    description: null,
    event_type: (overrides.event_type ?? "assignment") as never,
    event_date: overrides.event_date ?? new Date().toISOString(),
    duration_minutes: overrides.duration_minutes,
    recording_url: overrides.recording_url,
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

  it("on an empty day, names what comes next instead of an empty state", async () => {
    // Most days have nothing on them, and the card answered every one of
    // them with an icon and "no events" — «Раздел сегодня будто не
    // работает». Now the next events, soonest first, and never a past one.
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    const inDays = (n: number) => {
      const d = new Date()
      d.setDate(d.getDate() + n)
      return d.toISOString()
    }
    getCalendarEventsMock.mockResolvedValueOnce([
      makeEvent({ id: "late", title: "Final exam", event_date: inDays(9) }),
      makeEvent({ id: "past", title: "Old deadline", event_date: inDays(-3) }),
      makeEvent({ id: "soon", title: "Essay due", event_date: inDays(2) }),
      makeEvent({ id: "later", title: "Quiz 3", event_date: inDays(20) }),
    ])

    render(<TodayCard />, { wrapper: Wrapper })

    await waitFor(() => expect(screen.getByText("Essay due")).toBeInTheDocument())
    expect(screen.getByText(/nothing scheduled today|сегодня ничего/i)).toBeInTheDocument()
    const titles = screen.getAllByRole("listitem").map((li) => li.textContent ?? "")
    expect(titles).toHaveLength(2)
    expect(titles[0]).toContain("Essay due")
    expect(titles[1]).toContain("Final exam")
    expect(screen.queryByText("Old deadline")).not.toBeInTheDocument()
  })

  it("says plainly when nothing is coming up at all", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    getCalendarEventsMock.mockResolvedValueOnce([])

    render(<TodayCard />, { wrapper: Wrapper })

    await waitFor(() =>
      expect(screen.getByText(/nothing coming up|ближайших событий нет/i)).toBeInTheDocument(),
    )
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()
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

  describe("a class that has already ended", () => {
    // The Home card showed the day's class long after it had ended with
    // nothing to tell it from one still ahead — not even that it was over.
    const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString()
    const inDays = (n: number) => {
      const d = new Date()
      d.setDate(d.getDate() + n)
      return d.toISOString()
    }

    it("is marked over, and offers its recording", async () => {
      useAuthMock.mockReturnValue({ user: { id: "u-1" } })
      getCalendarEventsMock.mockResolvedValueOnce([
        makeEvent({
          title: "Урок 3",
          event_type: "live_session",
          event_date: hoursAgo(3),
          duration_minutes: 60,
          recording_url: "https://youtu.be/abc",
        }),
      ])
      render(<TodayCard />, { wrapper: Wrapper })
      await waitFor(() => expect(screen.getByText("Урок 3")).toBeInTheDocument())
      expect(screen.getByText(/^over$|^прошло$/i)).toBeInTheDocument()
      expect(screen.getByRole("link", { name: /Урок 3/ })).toHaveAttribute("href", "https://youtu.be/abc")
    })

    it("lists what comes next beneath, once everything today is over", async () => {
      useAuthMock.mockReturnValue({ user: { id: "u-1" } })
      getCalendarEventsMock.mockResolvedValueOnce([
        makeEvent({ id: "done", title: "Урок 3", event_type: "live_session", event_date: hoursAgo(3), duration_minutes: 60 }),
        makeEvent({ id: "next", title: "Урок 4", event_type: "live_session", event_date: inDays(7), duration_minutes: 60 }),
      ])
      render(<TodayCard />, { wrapper: Wrapper })
      await waitFor(() => expect(screen.getByText("Урок 4")).toBeInTheDocument())
      const lists = screen.getAllByRole("list")
      expect(lists).toHaveLength(2)
      expect(lists[0]).toHaveTextContent("Урок 3")
      expect(lists[1]).toHaveTextContent("Урок 4")
    })

    it("keeps the day to itself while a class is still ahead", async () => {
      useAuthMock.mockReturnValue({ user: { id: "u-1" } })
      const soon = new Date(Date.now() + 2 * 3_600_000)
      // Only when "soon" is still today; near midnight the case does not exist.
      if (soon.getDate() !== new Date().getDate()) return
      getCalendarEventsMock.mockResolvedValueOnce([
        makeEvent({ id: "done", title: "Урок 3", event_type: "live_session", event_date: hoursAgo(3), duration_minutes: 60 }),
        makeEvent({ id: "later", title: "Урок 3б", event_type: "live_session", event_date: soon.toISOString(), duration_minutes: 60 }),
        makeEvent({ id: "next", title: "Урок 4", event_type: "live_session", event_date: inDays(7), duration_minutes: 60 }),
      ])
      render(<TodayCard />, { wrapper: Wrapper })
      await waitFor(() => expect(screen.getByText("Урок 3б")).toBeInTheDocument())
      expect(screen.queryByText("Урок 4")).toBeNull()
      expect(screen.getAllByRole("list")).toHaveLength(1)
    })
  })
})
