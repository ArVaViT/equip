import { isoToLocalInput } from "@/i18n/format"
import { DEFAULT_LIVE_SESSION_MINUTES, type EventFormState } from "@/pages/Teacher/editor/types"
import type { CalendarEvent } from "@/types"

/**
 * The course's most recent live session: the latest one already begun,
 * or — on a course that has not met yet — the first one ahead. Only
 * these two carry the teacher's habits (hour, length, room).
 */
export function recentLiveSession(events: CalendarEvent[], courseId: string, now: number): CalendarEvent | null {
  const sessions = events
    .filter((e) => e.course_id === courseId && e.event_type === "live_session" && Number.isFinite(Date.parse(e.event_date)))
    .sort((a, b) => Date.parse(a.event_date) - Date.parse(b.event_date))
  const begun = sessions.filter((e) => Date.parse(e.event_date) <= now)
  return begun[begun.length - 1] ?? sessions[0] ?? null
}

/** The course the teacher last held a class on, among those they teach. */
export function courseOfRecentLiveSession(events: CalendarEvent[], teachingIds: Set<string>, now: number): string | null {
  const candidates = [...teachingIds]
    .map((id) => recentLiveSession(events, id, now))
    .filter((e): e is CalendarEvent => e !== null)
  if (candidates.length === 0) return null
  // The same rule across courses: the latest already begun, else the soonest ahead.
  const begun = candidates.filter((e) => Date.parse(e.event_date) <= now)
  const pick = begun.length
    ? begun.reduce((a, b) => (Date.parse(a.event_date) >= Date.parse(b.event_date) ? a : b))
    : candidates.reduce((a, b) => (Date.parse(a.event_date) <= Date.parse(b.event_date) ? a : b))
  return pick.course_id
}

export interface NewEventDefaults {
  form: Partial<EventFormState>
  /** The hour the picked day starts at; the date itself stays empty. */
  defaultTime?: { hh: number; mm: number }
}

/**
 * What «Новое событие» opens with, from the calendar.
 *
 * A teacher adding next Saturday's class had every field blank and typed
 * «Живое занятие, 20:00, 90 минут, the same Zoom link» for the ninth
 * time. From the calendar the kind is a live session, and the hour, the
 * length and the room come from the course's last one; the date is the
 * one thing left to pick. A course with no class yet gets the usual
 * 90 minutes and nothing else.
 */
export function newEventDefaults(events: CalendarEvent[], courseId: string | undefined, now: number): NewEventDefaults {
  const recent = courseId ? recentLiveSession(events, courseId, now) : null
  const form: Partial<EventFormState> = {
    event_type: "live_session",
    duration_minutes: String(recent?.duration_minutes || DEFAULT_LIVE_SESSION_MINUTES),
    meeting_url: recent?.meeting_url ?? "",
  }
  if (!recent) return { form }
  const local = isoToLocalInput(recent.event_date)
  const m = /T(\d{2}):(\d{2})$/.exec(local)
  return m ? { form, defaultTime: { hh: Number(m[1]), mm: Number(m[2]) } } : { form }
}
