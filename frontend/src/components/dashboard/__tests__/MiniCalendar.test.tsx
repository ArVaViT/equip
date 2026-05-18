import type { ReactNode } from "react"
import { render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { MiniCalendar } from "../MiniCalendar"

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

describe("MiniCalendar", () => {
  beforeEach(() => {
    getCalendarEventsMock.mockReset()
    useAuthMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("renders 42 grid cells (6 weeks × 7 days) plus the 7 weekday headers", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    getCalendarEventsMock.mockResolvedValueOnce([])

    render(<MiniCalendar />, { wrapper: Wrapper })

    await waitFor(() => expect(getCalendarEventsMock).toHaveBeenCalled())

    // Each day cell has an aria-label like "Monday, May 17, 2026" — that
    // gives us a stable selector that doesn't depend on the visible digit
    // colliding with weekday-head text or month-label digits.
    const dayCells = screen.getAllByLabelText(
      /^[A-Za-zА-Яа-я]+,\s|\d.+\d/, // weekday-prefixed or contains digits
    )
    expect(dayCells.length).toBeGreaterThanOrEqual(42)
  })

  it('exposes "Open full calendar" link pointing to /calendar', async () => {
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    getCalendarEventsMock.mockResolvedValueOnce([])

    render(<MiniCalendar />, { wrapper: Wrapper })

    const link = screen.getByRole("link", { name: /full calendar|календарь/i })
    expect(link).toHaveAttribute("href", "/calendar")
  })

  it("marks today's cell with aria-current=date", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    getCalendarEventsMock.mockResolvedValueOnce([])

    render(<MiniCalendar />, { wrapper: Wrapper })
    await waitFor(() => expect(getCalendarEventsMock).toHaveBeenCalled())

    const todayCell = screen
      .getAllByLabelText(/./)
      .find((el) => el.getAttribute("aria-current") === "date")
    expect(todayCell).toBeDefined()
  })

  it("renders an event dot on the day a calendar event falls on", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u-1" } })
    const today = new Date()
    const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1)
    getCalendarEventsMock.mockResolvedValueOnce([
      {
        id: "e-1",
        title: "Test event",
        description: null,
        event_type: "assignment",
        event_date: tomorrow.toISOString(),
        course_id: "c-1",
        course_title: "Course",
        source: "assignment",
      },
    ])

    render(<MiniCalendar />, { wrapper: Wrapper })

    await waitFor(() => expect(getCalendarEventsMock).toHaveBeenCalled())

    // Tomorrow's cell should pick up an aria-hidden dot child.
    const tomorrowCell = await screen.findByLabelText(
      tomorrow.toLocaleDateString(i18n.language, {
        weekday: "long",
        day: "numeric",
        month: "long",
      }),
    )
    // The dot is a <span class="...bg-primary..."> child.
    const dot = within(tomorrowCell).getByText("", { selector: "span.bg-primary, span.bg-primary-foreground" })
    expect(dot).toBeInTheDocument()
  })

  it("does NOT fetch events for unauthenticated visitors", async () => {
    useAuthMock.mockReturnValue({ user: null })

    render(<MiniCalendar />, { wrapper: Wrapper })

    // Effect path early-returns when user is null.
    expect(getCalendarEventsMock).not.toHaveBeenCalled()
  })
})
