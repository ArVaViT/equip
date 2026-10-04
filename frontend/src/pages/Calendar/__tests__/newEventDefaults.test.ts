import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { setDisplayTimeZone } from "@/i18n/timeZone"
import type { CalendarEvent } from "@/types"
import { courseOfRecentLiveSession, newEventDefaults, recentLiveSession } from "../newEventDefaults"

/**
 * «Новое событие» from the calendar used to open blank, and the teacher
 * typed the same class — kind, hour, length, Zoom room — for the ninth
 * time. The course's last class says what the next one looks like; the
 * date is the one thing left to pick.
 */

const NOW = Date.parse("2026-10-03T16:00:00Z")
const ZOOM = "https://us02web.zoom.us/j/4959692097"

const session = (id: string, course_id: string, event_date: string, extra: Partial<CalendarEvent> = {}): CalendarEvent =>
  ({
    id, course_id, event_date, title: "Урок", description: null, event_type: "live_session",
    meeting_url: ZOOM, duration_minutes: 75, course_title: null, source: "course_event", ...extra,
  }) as CalendarEvent

describe("newEventDefaults", () => {
  beforeEach(() => setDisplayTimeZone("America/Indiana/Indianapolis"))
  afterEach(() => setDisplayTimeZone(null))

  it("reads the hour, the length and the room off the course's last class, and leaves the date empty", () => {
    const events = [
      session("old", "c1", "2026-09-26T23:00:00Z", { duration_minutes: 60 }),
      session("last", "c1", "2026-10-02T23:00:00Z"), // Fri 19:00 in Indianapolis
      session("next", "c1", "2026-10-10T00:00:00Z", { duration_minutes: 120 }),
    ]
    const { form, defaultTime } = newEventDefaults(events, "c1", NOW)
    expect(form).toEqual({ event_type: "live_session", duration_minutes: "75", meeting_url: ZOOM })
    expect(form).not.toHaveProperty("event_date")
    expect(defaultTime).toEqual({ hh: 19, mm: 0 })
  })

  it("on a course that has not met yet, takes the first class ahead", () => {
    const events = [session("soon", "c1", "2026-10-10T00:00:00Z"), session("later", "c1", "2026-10-17T00:00:00Z")]
    expect(recentLiveSession(events, "c1", NOW)?.id).toBe("soon")
    // Sat 20:00 in Indianapolis.
    expect(newEventDefaults(events, "c1", NOW).defaultTime).toEqual({ hh: 20, mm: 0 })
  })

  it("with no class to copy, is a 90-minute live session and nothing more", () => {
    const deadlineOnly = [session("d", "c1", "2026-10-05T04:00:00Z", { event_type: "deadline", meeting_url: null })]
    expect(newEventDefaults(deadlineOnly, "c1", NOW)).toEqual({
      form: { event_type: "live_session", duration_minutes: "90", meeting_url: "" },
    })
    expect(newEventDefaults([], undefined, NOW).form.duration_minutes).toBe("90")
  })

  it("names the course the teacher last held a class on, among the ones they teach", () => {
    const events = [
      session("a", "c1", "2026-09-26T23:00:00Z"),
      session("b", "c2", "2026-10-02T23:00:00Z"),
      session("c", "c3", "2026-10-03T10:00:00Z"), // not theirs
    ]
    expect(courseOfRecentLiveSession(events, new Set(["c1", "c2"]), NOW)).toBe("c2")
    expect(courseOfRecentLiveSession(events, new Set(["c9"]), NOW)).toBeNull()
  })
})
