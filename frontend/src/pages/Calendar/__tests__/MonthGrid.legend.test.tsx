import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { CalendarEvent } from "@/types"
import { MonthGrid } from "../MonthGrid"
import { calendarDayKey } from "../utils"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const lesson = (id: string, type: CalendarEvent["event_type"]): CalendarEvent =>
  ({ id, title: "Урок", event_type: type, event_date: "2026-10-10T20:00:00Z", source: "course_event" }) as CalendarEvent

function renderOctober(eventsByDate: Map<string, CalendarEvent[]>) {
  const days = Array.from({ length: 35 }, (_, i) => ({ date: new Date(2026, 8, 28 + i), inMonth: i >= 3 && i < 34 }))
  render(
    <MonthGrid
      year={2026}
      month={9}
      today={new Date(2026, 9, 3)}
      calendarDays={days}
      eventsByDate={eventsByDate}
      selectedDay={null}
      onSelectDay={vi.fn()}
      onPrevMonth={vi.fn()}
      onNextMonth={vi.fn()}
      onGoToday={vi.fn()}
    />,
    { wrapper: Wrapper },
  )
}

/**
 * The legend used to explain all four kinds of dot under every month,
 * including months with one kind — a line on a phone telling the reader
 * to look for deadlines and exams that were not on the grid.
 */
describe("MonthGrid — the legend", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("explains only the kinds of event on the visible grid", () => {
    const map = new Map<string, CalendarEvent[]>()
    map.set(calendarDayKey(new Date(2026, 9, 10)), [lesson("a", "live_session")])
    map.set(calendarDayKey(new Date(2026, 9, 17)), [lesson("b", "live_session"), lesson("c", "deadline")])
    renderOctober(map)
    expect(screen.getByText("Живое занятие")).toBeInTheDocument()
    expect(screen.getByText("Срок сдачи")).toBeInTheDocument()
    expect(screen.queryByText("Экзамен")).toBeNull()
    expect(screen.queryByText("Другое")).toBeNull()
  })

  it("has no legend at all for an empty month", () => {
    renderOctober(new Map())
    expect(screen.queryByText("Живое занятие")).toBeNull()
    expect(screen.queryByText("Срок сдачи")).toBeNull()
  })
})
