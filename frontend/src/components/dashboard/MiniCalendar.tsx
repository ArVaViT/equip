import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowRight, CalendarDays } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import type { CalendarEvent } from "@/types"
import { cn } from "@/lib/utils"

const DAYS_IN_WEEK = 7

// 0=Sun..6=Sat from getDay(); rotate so the row reads Mon..Sun, the
// week-start convention used elsewhere (Calendar page, StreakCard).
function weekdayMonStart(date: Date): number {
  const sunStart = date.getDay()
  return (sunStart + 6) % DAYS_IN_WEEK
}

interface MonthCell {
  date: Date
  inCurrentMonth: boolean
  isToday: boolean
  hasEvent: boolean
}

function ymdKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/**
 * Build the 6×7 grid that fits any month. Always renders the leading
 * trailing-month days + the trailing leading-month days so cell count
 * is constant (42), which keeps card height stable across months.
 */
function buildMonthGrid(anchor: Date, eventsByDay: Set<string>): MonthCell[] {
  const year = anchor.getFullYear()
  const month = anchor.getMonth()
  const firstOfMonth = new Date(year, month, 1)
  const offset = weekdayMonStart(firstOfMonth)
  const gridStart = new Date(year, month, 1 - offset)
  const today = new Date()
  const todayKey = ymdKey(today)

  const cells: MonthCell[] = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i)
    const key = ymdKey(d)
    cells.push({
      date: d,
      inCurrentMonth: d.getMonth() === month,
      isToday: key === todayKey,
      hasEvent: eventsByDay.has(key),
    })
  }
  return cells
}

/**
 * Compact 5- or 6-row month grid for the Dashboard side rail.
 *
 * Mirrors the data path of the full ``/calendar`` page (same
 * ``coursesService.getCalendarEvents`` call) so a day with a course
 * event surfaces a dot here as soon as it does there. ``i18n.language``
 * is in the dep list so the locale flip re-pulls the localised event
 * payload without a hard reload — same pattern the Dashboard's
 * MyCoursesSection uses.
 *
 * Guests fall through to a minimal "sign in to see your calendar" hint
 * so the card slot still has a designed shape on the public Dashboard
 * splash.
 */
export function MiniCalendar() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!user) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setFailed(false)
    coursesService
      .getCalendarEvents()
      .then((evts) => {
        if (cancelled) return
        setEvents(evts)
      })
      .catch(() => {
        if (cancelled) return
        setFailed(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // Effect re-runs on auth change (user?.id) and locale change
    // (i18n.language) — those are the only inputs to the fetched data
    // and the early-return branch. Including ``user`` as the object
    // reference would refire on every unrelated context re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, i18n.language])

  const today = useMemo(() => new Date(), [])
  const eventsByDay = useMemo(() => {
    const s = new Set<string>()
    for (const e of events) {
      // ``event_date`` is an ISO date string. ``new Date()`` parses both
      // ``YYYY-MM-DD`` and full ISO timestamps; we then re-key against the
      // local YMD so a 2026-05-17T03:00Z event lands on May 16/17 per the
      // user's local timezone, matching the Calendar page's bucketing.
      const d = new Date(e.event_date)
      if (!Number.isNaN(d.getTime())) s.add(ymdKey(d))
    }
    return s
  }, [events])

  const cells = useMemo(() => buildMonthGrid(today, eventsByDay), [today, eventsByDay])

  const weekdayHeads = [
    t("streak.days.mon"),
    t("streak.days.tue"),
    t("streak.days.wed"),
    t("streak.days.thu"),
    t("streak.days.fri"),
    t("streak.days.sat"),
    t("streak.days.sun"),
  ]

  // Localised "May 2026" style title. ``toLocaleDateString`` honours
  // the active i18n language without us shipping a month-name table.
  const monthLabel = today.toLocaleDateString(i18n.language, {
    month: "long",
    year: "numeric",
  })

  return (
    <section
      aria-labelledby="mini-calendar-heading"
      className="animate-fade-in flex h-full flex-col overflow-hidden rounded-md border border-border bg-card transition-[border-color] duration-300 hover:border-primary/25"
    >
      <header className="flex items-center justify-between gap-3 border-b border-border bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          <h2
            id="mini-calendar-heading"
            className="truncate font-serif text-sm font-semibold capitalize tracking-tight text-foreground"
          >
            {monthLabel}
          </h2>
        </div>
        <Link
          to="/calendar"
          className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary transition-opacity hover:opacity-80"
        >
          {t("dashboard.miniCalendar.openFull")}
          <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </Link>
      </header>

      <div className="flex-1 px-4 py-3 sm:px-5 sm:py-4">
        {/* Weekday header row. ``tracking-[0.18em] uppercase text-[10px]``
            matches the editorial-eyebrow recipe used on the rest of the
            dashboard so the calendar header doesn't read as a separate
            visual vocabulary. */}
        <div className="grid grid-cols-7 gap-1">
          {weekdayHeads.map((d, i) => (
            <div
              key={i}
              className="pb-1 text-center text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground"
            >
              {d}
            </div>
          ))}

          {loading
            ? Array.from({ length: 42 }).map((_, i) => (
                <Skeleton key={i} className="aspect-square w-full rounded-sm" />
              ))
            : cells.map((c, i) => (
                <div
                  key={i}
                  className={cn(
                    "relative flex aspect-square items-center justify-center rounded-sm text-xs tabular-nums",
                    c.inCurrentMonth ? "text-foreground" : "text-muted-foreground/40",
                    c.isToday && "bg-primary text-primary-foreground font-medium",
                  )}
                  aria-label={c.date.toLocaleDateString(i18n.language, {
                    weekday: "long",
                    day: "numeric",
                    month: "long",
                  })}
                  aria-current={c.isToday ? "date" : undefined}
                >
                  <span>{c.date.getDate()}</span>
                  {c.hasEvent && !c.isToday && (
                    <span
                      aria-hidden
                      className="absolute bottom-1 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-primary"
                    />
                  )}
                  {c.hasEvent && c.isToday && (
                    <span
                      aria-hidden
                      className="absolute bottom-1 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-primary-foreground"
                    />
                  )}
                </div>
              ))}
        </div>

        {failed && (
          <p className="mt-3 text-xs text-muted-foreground">
            {t("dashboard.miniCalendar.loadFailed")}
          </p>
        )}
      </div>
    </section>
  )
}
