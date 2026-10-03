import type { CalendarEvent } from "@/types"

type Timed = Pick<CalendarEvent, "event_date" | "event_type"> & { duration_minutes?: number | null }

/**
 * An event without a stored length is treated as an hour long — the length
 * the calendar feed has always written for one (`calendar_ical._duration`) —
 * and is still "on" for a while after that: a class that runs over keeps
 * its join button. Three hours from the start covers both, as before.
 */
const UNKNOWN_LENGTH_OVER_AFTER_MS = 3 * 60 * 60 * 1000
const MINUTE = 60 * 1000

/** A join button lights up this long before the start. */
export const JOIN_OPENS_BEFORE_MS = 15 * MINUTE
/** …and stays this long past the scheduled end: classes run over. */
export const JOIN_STAYS_AFTER_MS = 10 * MINUTE

/** When the event ends, or `null` for a moment (a deadline) or an unknown length. */
export function eventEnd(event: Timed): Date | null {
  const start = Date.parse(event.event_date)
  if (!Number.isFinite(start) || !event.duration_minutes) return null
  return new Date(start + event.duration_minutes * MINUTE)
}

/** Over: nothing left to join or to add to a calendar, only a recording to watch. */
export function isOver(event: Timed, now = Date.now()): boolean {
  const start = Date.parse(event.event_date)
  if (!Number.isFinite(start)) return false
  const end = eventEnd(event)
  if (end) return now >= end.getTime()
  return now - start > UNKNOWN_LENGTH_OVER_AFTER_MS
}

/** Under way, or about to be: the moment "Join" is the one thing on the card.
 *  A class with a length stays joinable a little past its end — the one that
 *  runs ten minutes over still has a door. */
export function isJoinableNow(event: Timed, now = Date.now()): boolean {
  const start = Date.parse(event.event_date)
  if (!Number.isFinite(start)) return false
  if (now < start - JOIN_OPENS_BEFORE_MS) return false
  const end = eventEnd(event)
  return end ? now < end.getTime() + JOIN_STAYS_AFTER_MS : !isOver(event, now)
}

/** Whole minutes until the start, or `null` once it has started. */
export function minutesUntil(event: Timed, now = Date.now()): number | null {
  const start = Date.parse(event.event_date)
  if (!Number.isFinite(start) || start <= now) return null
  return Math.ceil((start - now) / MINUTE)
}

/**
 * The last day of a weekly series as `YYYY-MM-DD`, from the first class's
 * local `YYYY-MM-DDTHH:mm` value. Pure date arithmetic on the calendar day,
 * so a clock change in between cannot push it across midnight.
 */
export function seriesLastDay(firstLocal: string, everyWeeks: number, count: number): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(firstLocal)
  if (!m || count < 1 || everyWeeks < 1) return null
  const day = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  day.setUTCDate(day.getUTCDate() + (count - 1) * everyWeeks * 7)
  return day.toISOString().slice(0, 10)
}
