import { useMemo } from "react"
import { useAsyncData } from "@/hooks/useAsyncData"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowRight, CalendarDays } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import type { CalendarEvent } from "@/types"

const MAX_EVENTS_SHOWN = 3

function ymdKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/**
 * "What's today" surface for the Dashboard side rail.
 *
 * Replaced the earlier MiniCalendar (month grid) because the Dashboard
 * couldn't fit a 6×7 grid + the Verse + Streak in one viewport. The
 * card now answers the single question students actually have at the
 * top of the day — "what do I need to do" — by listing today's
 * calendar events with the source course, plus a link to the full
 * calendar for anything further out.
 *
 * Locale: re-fetches on ``i18n.language`` change so localised course
 * titles propagate without a hard reload; date/weekday label is built
 * via ``toLocaleDateString(i18n.language, …)`` so it switches with the
 * UI language too.
 */
export function TodayCard() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()

  // Silent on error: the dashboard is more important than this card.
  // The empty state below covers both "no events today" and "fetch
  // failed" — both surface as "nothing to do, open the full calendar
  // to look further". We catch inside the fetcher so useAsyncData's
  // error stays null and never reaches the render branch.
  const { data: events = [], loading } = useAsyncData<CalendarEvent[]>(
    async () => {
      if (!user) return []
      try {
        return await coursesService.getCalendarEvents()
      } catch {
        return []
      }
    },
    // user object identity changes on unrelated context refreshes, so
    // key the dep on ``id`` to avoid spurious re-fetches.
    [user?.id, i18n.language],
  )

  const today = useMemo(() => new Date(), [])
  const todayKey = ymdKey(today)

  // Only the events that fall on the local calendar day. The
  // backend may ship full ISO timestamps; convert each to the
  // browser's local day before bucketing so a 23:30Z event lands on
  // the same date a student sees in the calendar page.
  const todayEvents = useMemo(
    () =>
      events
        .filter((e) => {
          const d = new Date(e.event_date)
          return !Number.isNaN(d.getTime()) && ymdKey(d) === todayKey
        })
        .slice(0, MAX_EVENTS_SHOWN),
    [events, todayKey],
  )

  const dateLabel = today.toLocaleDateString(i18n.language, {
    weekday: "long",
    day: "numeric",
    month: "long",
  })

  return (
    <section
      aria-labelledby="today-card-heading"
      className="animate-fade-in flex h-full flex-col overflow-hidden rounded-md border border-border bg-card transition-[border-color] duration-300 hover:border-primary/25"
    >
      <header className="flex items-center justify-between gap-3 border-b border-border bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          <div className="min-w-0">
            <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {t("dashboard.today.eyebrow")}
            </p>
            <h2
              id="today-card-heading"
              className="truncate font-serif text-sm font-semibold capitalize tracking-tight text-foreground"
            >
              {dateLabel}
            </h2>
          </div>
        </div>
        <Link
          to="/calendar"
          className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary transition-opacity hover:opacity-80"
        >
          {t("dashboard.today.openFull")}
          <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </Link>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-5 sm:py-4">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-3.5 w-3/4" />
          </div>
        ) : todayEvents.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("dashboard.today.empty")}</p>
        ) : (
          <ul className="space-y-2">
            {todayEvents.map((e) => (
              <li key={e.id} className="flex items-start gap-2.5 text-xs">
                <span
                  aria-hidden
                  className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
                />
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">{e.title}</p>
                  {e.course_title && (
                    <p className="truncate text-muted-foreground">{e.course_title}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
