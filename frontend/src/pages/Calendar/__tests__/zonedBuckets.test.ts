import { renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { setDisplayTimeZone } from "@/i18n/timeZone"
import type { CalendarEvent } from "@/types"

import { useMonthGrid } from "../useMonthGrid"
import { calendarDayKey, formatTime } from "../utils"

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

// Saturdays at 19:00 in Indianapolis, as the server stores them: before Kyiv's
// change (Oct 25), the week between it and Indiana's (Nov 1), and after both.
const INDY_SATURDAYS = [
  "2026-10-17T23:00:00Z",
  "2026-10-24T23:00:00Z",
  "2026-10-31T23:00:00Z",
  "2026-11-08T00:00:00Z",
].map((event_date, i) => ({ id: `s${i}`, title: "Урок", event_date }) as unknown as CalendarEvent)

describe("the week between Kyiv's and Indiana's clock changes", () => {
  afterEach(async () => {
    setDisplayTimeZone(null)
    await i18n.changeLanguage("en")
  })

  it("keeps an Indiana series on Saturdays in Indiana, whatever the browser's zone", () => {
    setDisplayTimeZone("America/Indiana/Indianapolis")
    const { result } = renderHook(() => useMonthGrid(INDY_SATURDAYS))
    for (const day of [new Date(2026, 9, 17), new Date(2026, 9, 24), new Date(2026, 9, 31), new Date(2026, 10, 7)]) {
      expect(result.current.eventsByDate.get(calendarDayKey(day))).toHaveLength(1)
    }
    expect(result.current.eventsByDate.size).toBe(4)
  })

  it("files every one of them under Sunday in Kyiv, the hour-earlier week included", async () => {
    await i18n.changeLanguage("uk")
    setDisplayTimeZone("Europe/Kyiv")
    const { result } = renderHook(() => useMonthGrid(INDY_SATURDAYS))
    for (const day of [new Date(2026, 9, 18), new Date(2026, 9, 25), new Date(2026, 10, 1), new Date(2026, 10, 8)]) {
      expect(result.current.eventsByDate.get(calendarDayKey(day))).toHaveLength(1)
    }
    expect(result.current.eventsByDate.size).toBe(4)
    // 02:00 on Kyiv's clock, except the one week Kyiv has changed and Indiana has not.
    expect(INDY_SATURDAYS.map((e) => formatTime(e.event_date))).toEqual(["02:00", "02:00", "01:00", "02:00"])
  })
})
