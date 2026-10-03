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

  it("offers a way into today's live session, and none into one days away", () => {
    // A week early the join button sat beside a date a week away —
    // something to press now, which it was not. The link belongs to the
    // day of the class.
    const zoom = "https://zoom.us/j/1234567890?pwd=aB3dEf"
    const inThreeDays = new Date()
    inThreeDays.setDate(inThreeDays.getDate() + 3)
    const { unmount } = render(<UpcomingEvents events={[eventAt(inThreeDays, { meeting_url: zoom })]} />, {
      wrapper: Wrapper,
    })
    expect(screen.queryByRole("link", { name: /Присоединиться/ })).toBeNull()
    unmount()

    const laterToday = new Date(Date.now() + 2 * 60 * 60 * 1000)
    // Near midnight "two hours on" is tomorrow; the case does not exist then.
    if (laterToday.getDate() !== new Date().getDate()) return
    render(<UpcomingEvents events={[eventAt(laterToday, { meeting_url: zoom })]} />, { wrapper: Wrapper })
    const link = screen.getByRole("link", { name: /Присоединиться/ })
    expect(link).toHaveAttribute("href", zoom)
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
    // Hours away, it is a line of text, not a button.
    expect(link).toHaveTextContent("Ссылка на занятие")
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

  it("leads with the class on now, not with yesterday's", () => {
    // Yesterday's lesson, an hour long, with its recording; today's class
    // started ten minutes ago. The first row is the one going on.
    const yesterday = new Date(Date.now() - 20 * 60 * 60 * 1000)
    const started = new Date(Date.now() - 10 * 60 * 1000)
    const zoom = "https://zoom.us/j/1234567890"
    render(
      <UpcomingEvents
        events={[
          eventAt(yesterday, { id: "past", title: "Вчерашний урок", duration_minutes: 60, recording_url: "https://youtu.be/x" }),
          eventAt(started, { id: "now", title: "Сегодняшний урок", duration_minutes: 90, meeting_url: zoom }),
        ]}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.queryByText("Вчерашний урок")).toBeNull()
    expect(screen.getByText("Сегодняшний урок")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Присоединиться/ }).className).toContain("bg-brand ")
  })

  it("keeps a deadline missed today on top as a warning", () => {
    const missed = new Date(Date.now() - 2 * 60 * 60 * 1000)
    render(<UpcomingEvents events={[eventAt(missed, { event_type: "deadline", title: "Эссе" })]} />, {
      wrapper: Wrapper,
    })
    expect(screen.getByText("Эссе")).toBeInTheDocument()
  })

  it("keeps a class with no length while it may still be on, and lets it go after", () => {
    // Older events carry no length: "over" is three hours after the start.
    const startedAnHourAgo = new Date(Date.now() - 60 * 60 * 1000)
    const { unmount } = render(<UpcomingEvents events={[eventAt(startedAnHourAgo, { title: "Без длительности" })]} />, {
      wrapper: Wrapper,
    })
    expect(screen.getByText("Без длительности")).toBeInTheDocument()
    unmount()
    const startedFourHoursAgo = new Date(Date.now() - 4 * 60 * 60 * 1000)
    const { container } = render(<UpcomingEvents events={[eventAt(startedFourHoursAgo)]} />, { wrapper: Wrapper })
    expect(container.firstChild).toBeNull()
  })

  it("shows a group's first day on that day, and not the day after", () => {
    const today = new Date()
    const key = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
    const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000)
    render(
      <UpcomingEvents
        events={[
          eventAt(yesterday, { id: "y", title: "Вчера начало", event_type: "other", all_day: true, day: key(yesterday) }),
          eventAt(today, { id: "t", title: "Сегодня начало", event_type: "other", all_day: true, day: key(today) }),
        ]}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText("Сегодня начало")).toBeInTheDocument()
    expect(screen.queryByText("Вчера начало")).toBeNull()
  })
})
