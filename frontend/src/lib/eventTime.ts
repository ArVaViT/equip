import type { CalendarEvent } from "@/types"

/**
 * An event carries a start and no length. Three hours after it began it is
 * over: nothing to join or add to a calendar, only its recording to watch.
 */
const OVER_AFTER_MS = 3 * 60 * 60 * 1000

export function isOver(event: Pick<CalendarEvent, "event_date">, now = Date.now()): boolean {
  const start = Date.parse(event.event_date)
  return Number.isFinite(start) && now - start > OVER_AFTER_MS
}
