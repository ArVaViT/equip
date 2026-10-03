import i18n, { activeIntlTag } from "@/i18n/config"
import { getDisplayTimeZone } from "@/i18n/timeZone"
import { eventEnd } from "@/lib/eventTime"
import type { CalendarEvent } from "@/types"

type Timed = Pick<CalendarEvent, "event_date" | "event_type"> & { duration_minutes?: number | null }

function unit(value: number, unitName: "hour" | "minute", locale: string): string {
  return new Intl.NumberFormat(locale, { style: "unit", unit: unitName, unitDisplay: "short" }).format(value)
}

/** «1 ч 30 мин», «45 min», «2 Std.» — a length as a person says it. */
export function formatDurationMinutes(minutes: number, language: string = i18n.language): string {
  const locale = activeIntlTag(language)
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h === 0) return unit(m, "minute", locale)
  if (m === 0) return unit(h, "hour", locale)
  return `${unit(h, "hour", locale)} ${unit(m, "minute", locale)}`
}

/**
 * «20:00–21:30» when the event has a length, «20:00» when it has none — in
 * the reader's zone. An end past midnight is still written as a time: a
 * class at 23:00 for ninety minutes reads «23:00–00:30», which nobody misreads.
 */
export function formatEventTimeRange(event: Timed, language: string = i18n.language): string {
  const locale = activeIntlTag(language)
  const fmt = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: getDisplayTimeZone(),
  })
  const start = new Date(event.event_date)
  if (Number.isNaN(start.getTime())) return ""
  const end = eventEnd(event)
  return end ? `${fmt.format(start)}–${fmt.format(end)}` : fmt.format(start)
}
