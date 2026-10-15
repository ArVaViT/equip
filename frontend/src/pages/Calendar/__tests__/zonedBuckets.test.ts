import { renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import { setDisplayTimeZone } from "@/i18n/timeZone"
import type { CalendarEvent } from "@/types"

import { useMonthGrid } from "../useMonthGrid"
import { calendarDayKey } from "../utils"

const lesson = { id: "e1", title: "Урок", event_date: "2026-10-06T02:30:00Z" } as unknown as CalendarEvent

describe("the calendar places an event on the reader's day", () => {
  afterEach(() => setDisplayTimeZone(null))

  it("in California, 02:30Z on the 6th is the evening of the 5th", () => {
    setDisplayTimeZone("America/Los_Angeles")
    const { result } = renderHook(() => useMonthGrid([lesson]))
    expect(result.current.eventsByDate.get(calendarDayKey(new Date(2026, 9, 5)))).toHaveLength(1)
    expect(result.current.eventsByDate.get(calendarDayKey(new Date(2026, 9, 6)))).toBeUndefined()
  })

  it("in Berlin it is the morning of the 6th", () => {
    setDisplayTimeZone("Europe/Berlin")
    const { result } = renderHook(() => useMonthGrid([lesson]))
    expect(result.current.eventsByDate.get(calendarDayKey(new Date(2026, 9, 6)))).toHaveLength(1)
  })

  it("a group's first day is the day it was set for, wherever the reader is", () => {
    // Set for the 5th in Kyiv (21:30Z on the 4th); California is still on the 4th.
    const groupStart = {
      id: "cohort_start-c1",
      title: "Начало занятий группы",
      event_date: "2026-10-04T21:30:00Z",
      all_day: true,
      day: "2026-10-05",
    } as unknown as CalendarEvent
    setDisplayTimeZone("America/Los_Angeles")
    const { result } = renderHook(() => useMonthGrid([groupStart]))
    expect(result.current.eventsByDate.get(calendarDayKey(new Date(2026, 9, 5)))).toHaveLength(1)
    expect(result.current.eventsByDate.get(calendarDayKey(new Date(2026, 9, 4)))).toBeUndefined()
  })
})
