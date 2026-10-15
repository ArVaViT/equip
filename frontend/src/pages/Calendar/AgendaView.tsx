import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { CalendarCheck, ChevronDown, History } from "lucide-react"

import type { CalendarEvent } from "@/types"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/patterns"
import { EventCard } from "@/components/calendar/EventCard"
import { formatDateLong } from "@/i18n/format"
import { zonedDayKey } from "@/i18n/timeZone"
import { eventDayKey, isJoinableNow, isOver } from "@/lib/eventTime"

/** How far back "past classes" reaches: a term's worth of recordings. */
const PAST_DAYS = 120
const DAY_MS = 24 * 60 * 60 * 1000
/** A missed deadline stays on top this long: late work is still accepted
 *  and marked late, so it is still something to do, not history. */
const OVERDUE_STAYS_DAYS = 3

interface DayGroup {
  key: string
  label: string
  events: CalendarEvent[]
}

function shiftDayKey(key: string, days: number): string {
  const [y, m, d] = key.split("-").map(Number)
  const day = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, (d ?? 1) + days))
  return day.toISOString().slice(0, 10)
}

function groupByDay(events: CalendarEvent[], now: number, t: (k: string) => string): DayGroup[] {
  // Neighbouring days by the calendar, not by 24 hours: on the night the
  // clocks change, now + 24h lands two days on.
  const today = zonedDayKey(new Date(now))
  const tomorrow = shiftDayKey(today, 1)
  const yesterday = shiftDayKey(today, -1)
  const groups = new Map<string, DayGroup>()
  for (const evt of events) {
    const key = eventDayKey(evt)
    if (!key) continue
    let group = groups.get(key)
    if (!group) {
      // The heading is the day itself, not the first event's instant: an
      // all-day item may lead a day its instant is not on here.
      const date = formatDateLong(`${key}T12:00:00Z`, {
        year: undefined,
        weekday: "long",
        month: "long",
        day: "numeric",
        timeZone: "UTC",
      })
      const label =
        key === today
          ? `${t("calendar.today")} · ${date}`
          : key === tomorrow
            ? `${t("calendar.tomorrow")} · ${date}`
            : key === yesterday
              ? `${t("calendar.yesterday")} · ${date}`
              : date
      group = { key, label, events: [] }
      groups.set(key, group)
    }
    group.events.push(evt)
  }
  return [...groups.values()]
}

/**
 * The schedule as a list of days — what a phone shows first, and what a
 * student actually asks of a calendar: "what's next, and when". Days with
 * nothing on them are not drawn. Past classes fold away underneath, newest
 * first, because that is where their recordings are.
 */
export function AgendaView({ events, now }: { events: CalendarEvent[]; now: number }) {
  const { t } = useTranslation()
  const [showPast, setShowPast] = useState(false)

  const { ahead, past } = useMemo(() => {
    const ahead: CalendarEvent[] = []
    const past: CalendarEvent[] = []
    const floor = now - PAST_DAYS * DAY_MS
    for (const evt of events) {
      const at = Date.parse(evt.event_date)
      if (!Number.isFinite(at)) continue
      const recentlyMissed = evt.event_type === "deadline" && at >= now - OVERDUE_STAYS_DAYS * DAY_MS
      // A class running over is still "on" while its door is open.
      const stillOpen = Boolean(evt.meeting_url) && isJoinableNow(evt, now)
      if (!isOver(evt, now) || recentlyMissed || stillOpen) ahead.push(evt)
      else if (at >= floor) past.push(evt)
    }
    ahead.sort((a, b) => a.event_date.localeCompare(b.event_date))
    past.sort((a, b) => b.event_date.localeCompare(a.event_date))
    return { ahead, past }
  }, [events, now])

  const aheadGroups = useMemo(() => groupByDay(ahead, now, t), [ahead, now, t])
  const pastGroups = useMemo(() => groupByDay(past, now, t), [past, now, t])

  return (
    <div className="space-y-6">
      {aheadGroups.length === 0 ? (
        <EmptyState
          icon={<CalendarCheck strokeWidth={1.75} aria-hidden />}
          title={t("calendar.agenda.emptyTitle")}
          description={t("calendar.agenda.emptyDescription")}
        />
      ) : (
        aheadGroups.map((group) => <DaySection key={group.key} group={group} now={now} />)
      )}

      {past.length > 0 && (
        <section aria-labelledby="calendar-past-heading" className="border-t border-edge pt-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowPast((v) => !v)}
            aria-expanded={showPast}
            aria-controls="calendar-past-list"
            id="calendar-past-heading"
          >
            <History className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("calendar.agenda.past", { count: past.length })}
            <ChevronDown
              className={`ml-1 h-4 w-4 transition-transform ${showPast ? "rotate-180" : ""}`}
              strokeWidth={1.75}
              aria-hidden
            />
          </Button>
          {showPast && (
            <div id="calendar-past-list" className="mt-4 space-y-6">
              {pastGroups.map((group) => (
                <DaySection key={group.key} group={group} now={now} />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  )
}

function DaySection({ group, now }: { group: DayGroup; now: number }) {
  return (
    <section>
      <h2 className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted first-letter:uppercase">
        {group.label}
      </h2>
      <div className="space-y-2">
        {group.events.map((evt) => (
          <EventCard key={evt.id} event={evt} now={now} />
        ))}
      </div>
    </section>
  )
}
