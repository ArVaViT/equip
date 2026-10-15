import { useTranslation } from "react-i18next"
import { ChevronLeft, ChevronRight } from "lucide-react"

import type { CalendarEvent } from "@/types"
import { Button } from "@/components/ui/button"
import { formatEventTimeRange } from "@/components/calendar/eventTimeFormat"
import { formatCalendarDay } from "@/i18n/format"
import { isJoinableNow, isOver } from "@/lib/eventTime"
import { cn } from "@/lib/utils"
import { getEventColor } from "./constants"
import { calendarDayKey, isSameDay } from "./utils"

/**
 * Seven days, Monday first. On a wide screen they stand side by side as
 * columns; on a phone they stack, and a day with nothing on it is one
 * quiet line rather than an empty box. Each event is a chip — time,
 * title, kind — and pressing it opens the day's full cards below.
 */
export function WeekView({
  weekDays,
  eventsByDate,
  today,
  selectedDay,
  now,
  onSelectDay,
  onPrevWeek,
  onNextWeek,
  onGoToday,
}: {
  weekDays: Date[]
  eventsByDate: Map<string, CalendarEvent[]>
  today: Date
  selectedDay: Date | null
  now: number
  onSelectDay: (day: Date) => void
  onPrevWeek: () => void
  onNextWeek: () => void
  onGoToday: () => void
}) {
  const { t } = useTranslation()
  const first = weekDays[0] ?? today
  const last = weekDays[6] ?? today
  const range = `${formatCalendarDay(first, { year: undefined, weekday: undefined, month: "long", day: "numeric" })} – ${formatCalendarDay(last, { weekday: undefined, month: "long", day: "numeric", year: "numeric" })}`

  return (
    <div className="rounded-card border border-edge bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-edge px-4 py-3">
        <h2 className="text-base font-semibold tabular-nums">{range}</h2>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={onPrevWeek} aria-label={t("calendar.prevWeek")}>
            <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={onGoToday}>
            {t("calendar.today")}
          </Button>
          <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={onNextWeek} aria-label={t("calendar.nextWeek")}>
            <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        </div>
      </div>
      <ol className="grid grid-cols-1 divide-y divide-edge lg:grid-cols-7 lg:divide-x lg:divide-y-0">
        {weekDays.map((day) => {
          const events = eventsByDate.get(calendarDayKey(day)) ?? []
          const isToday = isSameDay(day, today)
          const isSelected = selectedDay != null && isSameDay(day, selectedDay)
          const weekday = formatCalendarDay(day, { year: undefined, month: undefined, day: undefined, weekday: "short" })
          return (
            <li key={calendarDayKey(day)} className={cn("min-w-0 lg:min-h-[14rem]", isSelected && "bg-muted/30")}>
              <button
                type="button"
                onClick={() => onSelectDay(day)}
                aria-pressed={isSelected}
                className="flex w-full items-center gap-2 px-3 pb-1 pt-2.5 text-left hover:bg-muted/40 lg:flex-col lg:items-start lg:gap-0.5"
              >
                <span className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">{weekday}</span>
                <span
                  className={cn(
                    "inline-flex h-7 min-w-7 items-center justify-center rounded-full px-1 text-sm font-semibold tabular-nums",
                    isToday && "bg-brand text-brand-foreground",
                  )}
                >
                  {day.getDate()}
                </span>
                {events.length === 0 && (
                  <span className="text-xs text-ink-muted lg:hidden">{t("calendar.week.free")}</span>
                )}
              </button>
              {events.length > 0 && (
                <ul className="space-y-1.5 px-2 pb-3">
                  {events.map((evt) => {
                    const color = getEventColor(evt.event_type)
                    const live = Boolean(evt.meeting_url) && isJoinableNow(evt, now)
                    const past = isOver(evt, now) && !live
                    return (
                      <li key={evt.id}>
                        <button
                          type="button"
                          onClick={() => onSelectDay(day)}
                          className={cn(
                            "w-full rounded-md border-l-2 px-2 py-1.5 text-left text-xs transition-colors hover:brightness-95",
                            // Past chips go grey by colour; opacity took the text below AA.
                            past ? "bg-muted" : color.bg,
                            live ? "border-l-brand ring-1 ring-brand/40" : color.bar,
                          )}
                        >
                          <span className="block font-medium tabular-nums text-ink">{formatEventTimeRange(evt)}</span>
                          <span className={cn("block text-wrap-safe line-clamp-2", past ? "text-ink-muted" : color.text)}>
                            {evt.title}
                          </span>
                          {evt.course_title && (
                            <span className="mt-0.5 block truncate text-ink">{evt.course_title}</span>
                          )}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
