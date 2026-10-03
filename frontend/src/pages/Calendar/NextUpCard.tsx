import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Video } from "lucide-react"

import type { CalendarEvent } from "@/types"
import { Eyebrow } from "@/components/patterns"
import { EventCard } from "@/components/calendar/EventCard"
import { formatDateLong } from "@/i18n/format"
import { zonedDayKey } from "@/i18n/timeZone"
import { isOver } from "@/lib/eventTime"

/** `YYYY-MM-DD` of a local-midnight calendar day, as the grids hold them. */
function localDayKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/** A class further off than this is not "next" — it is the schedule. */
const HORIZON_MS = 7 * 24 * 60 * 60 * 1000

/**
 * The next class, on top of the page — the one thing most visits to the
 * calendar are for. Only a live class or an exam: a deadline is in the
 * list below and in the course, and a reminder that shouts about a
 * deadline every visit stops being read.
 */
export function NextUpCard({
  events,
  now,
  hideOnDay,
  compact = false,
}: {
  events: CalendarEvent[]
  now: number
  /** The day already open beside it: a class on that day is shown there, not twice. */
  hideOnDay?: Date | null
  compact?: boolean
}) {
  const { t } = useTranslation()
  const next = useMemo(
    () =>
      events
        .filter(
          (e) =>
            (e.event_type === "live_session" || e.event_type === "exam") &&
            !isOver(e, now) &&
            Date.parse(e.event_date) - now <= HORIZON_MS,
        )
        .sort((a, b) => a.event_date.localeCompare(b.event_date))[0],
    [events, now],
  )
  if (!next) return null
  if (hideOnDay && zonedDayKey(new Date(next.event_date)) === localDayKey(hideOnDay)) return null
  const sameDay = zonedDayKey(new Date(next.event_date)) === zonedDayKey(new Date(now))
  const day = sameDay
    ? t("calendar.today")
    : formatDateLong(next.event_date, { year: undefined, weekday: "long", month: "long", day: "numeric" })
  return (
    <section aria-labelledby="calendar-next-up" className="rounded-card border border-edge bg-muted/30 p-4">
      <Eyebrow id="calendar-next-up" className="mb-3 flex items-center gap-1.5">
        <Video className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        {t("calendar.nextUp")}
      </Eyebrow>
      <EventCard event={next} now={now} showDate={day} compact={compact} className="bg-surface" />
    </section>
  )
}
