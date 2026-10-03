import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import type { CalendarEvent } from "@/types"
import { EventCard } from "../EventCard"

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

const NOW = Date.parse("2026-10-03T12:00:00Z")

function session(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: "e1",
    title: "Разбор проповеди",
    description: null,
    event_type: "live_session",
    event_date: "2026-10-10T20:00:00Z",
    meeting_url: null,
    duration_minutes: 90,
    course_id: "c1",
    course_title: "Курс проповеди",
    source: "course_event",
    ...overrides,
  }
}

describe("EventCard — the title line", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("names the event under its kind", () => {
    render(<EventCard event={session()} now={NOW} />, { wrapper: Wrapper })
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Разбор проповеди")
    expect(screen.getByText("Живое занятие")).toBeInTheDocument()
  })

  it("does not say the kind twice when that is all the title is", () => {
    // A title still being translated arrives as «Живое занятие»; the
    // kind line already says so, and the card read «Живое занятие /
    // Живое занятие».
    render(<EventCard event={session({ title: "Живое занятие" })} now={NOW} />, { wrapper: Wrapper })
    expect(screen.queryByRole("heading", { level: 3 })).toBeNull()
    expect(screen.getAllByText("Живое занятие")).toHaveLength(1)
  })

  it("says which lesson of the series this is, beside the repeat mark", () => {
    // Eight Saturdays all read «Урок»; the fourth could not be told from the first.
    render(
      <EventCard event={session({ title: "Урок", series_id: "s1", series_index: 2, series_count: 4 })} now={NOW} />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText("2 из 4")).toBeInTheDocument()
    expect(screen.getByText("Повторяющееся занятие")).toBeInTheDocument()
  })

  it("shows the repeat mark alone when the server did not number the lesson", () => {
    render(<EventCard event={session({ title: "Урок", series_id: "s1" })} now={NOW} />, { wrapper: Wrapper })
    expect(screen.getByText("Повторяющееся занятие")).toBeInTheDocument()
    expect(screen.queryByText(/из/)).toBeNull()
  })
})
