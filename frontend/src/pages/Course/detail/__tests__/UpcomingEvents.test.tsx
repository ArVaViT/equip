import React from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import type { CalendarEvent } from "@/types"
import { UpcomingEvents } from "@/pages/Course/detail/UpcomingEvents"

/**
 * The course page's «Ближайшие дедлайны и события» used to print the day
 * and nothing else — a live session at 19:00 read the same as a
 * deadline at midnight. The row now carries the time, in the reader's
 * zone, and the full stamp on hover.
 */

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function eventAt(local: Date, overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: "evt-1",
    title: "Разбор Деяний",
    description: null,
    event_type: "live_session",
    event_date: local.toISOString(),
    meeting_url: null,
    course_id: "c1",
    course_title: "Карта в кармане",
    source: "course_event",
    ...overrides,
  }
}

describe("UpcomingEvents", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("shows the time of day next to the date, in the reader's zone", () => {
    const soon = new Date()
    soon.setDate(soon.getDate() + 3)
    soon.setHours(19, 30, 0, 0)
    render(<UpcomingEvents events={[eventAt(soon)]} />, { wrapper: Wrapper })
    const time = screen.getByText(/19:30/)
    expect(time.tagName).toBe("TIME")
    // The month is Russian and in the genitive, not «Апр» dressed by CSS.
    expect(time.textContent).toMatch(/^\d{1,2} \p{Ll}/u)
    expect(time).toHaveAttribute("datetime", soon.toISOString())
  })

  it("renders nothing when every event is long past", () => {
    const past = new Date()
    past.setDate(past.getDate() - 10)
    const { container } = render(<UpcomingEvents events={[eventAt(past)]} />, { wrapper: Wrapper })
    expect(container.firstChild).toBeNull()
  })

  it("offers a way into a live session that has one", () => {
    const soon = new Date()
    soon.setDate(soon.getDate() + 3)
    const zoom = "https://zoom.us/j/1234567890?pwd=aB3dEf"
    render(<UpcomingEvents events={[eventAt(soon, { meeting_url: zoom })]} />, { wrapper: Wrapper })
    const link = screen.getByRole("link", { name: /Присоединиться/ })
    expect(link).toHaveAttribute("href", zoom)
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("shows no join button on an event with nowhere to be", () => {
    // A deadline is a moment, not a room. An empty button here would be
    // a promise the row cannot keep.
    const soon = new Date()
    soon.setDate(soon.getDate() + 3)
    render(<UpcomingEvents events={[eventAt(soon, { event_type: "deadline" })]} />, {
      wrapper: Wrapper,
    })
    expect(screen.queryByRole("link")).toBeNull()
  })
})
