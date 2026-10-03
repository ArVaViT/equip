import { activeIntlTag } from "@/i18n/config"
import { getDisplayTimeZone, zonedToday } from "@/i18n/timeZone"
import { useZonedTodayKey } from "@/i18n/useZonedToday"
import { parseYmd } from "@/lib/calendar"
import { useMemo } from "react"
import { useAsyncData } from "@/hooks/useAsyncData"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowRight, CalendarDays } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { Eyebrow } from "@/components/patterns"
import { JoinMeetingLink } from "@/components/calendar/JoinMeetingLink"
import { eventDayKey, isJoinableNow, isOver } from "@/lib/eventTime"
import { formatEventTimeRange } from "@/components/calendar/eventTimeFormat"
import { useNow } from "@/hooks/useNow"
import { RecordingLink } from "@/components/calendar/RecordingLink"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import type { CalendarEvent } from "@/types"

const MAX_EVENTS_SHOWN = 3
/** Events further out, shown when today itself is empty. */
const MAX_AHEAD_SHOWN = 2

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
  const now = useNow()
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

  // Today on the reader's calendar (profile zone, else the browser's),
  // moving on at the reader's midnight in a tab left open.
  const dayKey = useZonedTodayKey()
  const today = useMemo(() => parseYmd(dayKey) ?? zonedToday(), [dayKey])
  const todayKey = ymdKey(today)

  // Only the events that fall on the reader's calendar day: each instant
  // is placed on its day in the reader's zone, as the calendar page does,
  // so a 23:30Z event lands on the same date in both.
  const todayEvents = useMemo(
    () =>
      events
        .filter((e) => eventDayKey(e) === todayKey)
        .slice(0, MAX_EVENTS_SHOWN),
    [events, todayKey],
  )

  // Once the last class of the day has ended, today is answered: the next
  // question is "what comes next", the same as on an empty day.
  const allOver = todayEvents.length > 0 && todayEvents.every((e) => isOver(e, now))

  // What comes next, for the day that has nothing. The card used to answer
  // an empty day with a large empty state — an icon, «На сегодня нет
  // событий» and advice to open the calendar — and most days are empty, so
  // to the people using it the card looked broken: «Раздел сегодня будто не
  // работает». The calendar already knows the answer to the next question.
  const aheadEvents = useMemo(() => {
    if (todayEvents.length > 0 && !allOver) return []
    return events
      .filter((e) => {
        const key = eventDayKey(e)
        return key !== null && key > todayKey
      })
      .sort((a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime())
      .slice(0, MAX_AHEAD_SHOWN)
  }, [events, todayKey, todayEvents.length, allOver])

  const shortDate = (iso: string) =>
    new Date(iso).toLocaleDateString(activeIntlTag(i18n.resolvedLanguage ?? i18n.language), {
      weekday: "short",
      day: "numeric",
      month: "short",
      timeZone: getDisplayTimeZone(),
    })

  // Rendered with `first-letter:uppercase`, never CSS `capitalize`: the
  // latter raises every word, and Russian read "Понедельник, 31 Августа".
  // `today` is already the reader's calendar date (a local midnight), so
  // it is formatted without a zone.
  const dateLabel = today.toLocaleDateString(activeIntlTag(i18n.resolvedLanguage ?? i18n.language), {
    weekday: "long",
    day: "numeric",
    month: "long",
  })

  const aheadList = (
    <ul className="space-y-2" aria-label={t("dashboard.today.ahead")}>
      {aheadEvents.map((e) => (
        <li key={e.id} className="flex items-baseline gap-2.5">
          <span className="min-w-[5.5rem] shrink-0 whitespace-nowrap tabular-nums text-ink-muted first-letter:uppercase">
            {shortDate(e.event_date)}
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium text-ink">{e.title}</p>
            {e.course_title && <p className="truncate text-ink-muted">{e.course_title}</p>}
          </div>
        </li>
      ))}
    </ul>
  )

  return (
    <section
      aria-labelledby="today-card-heading"
      className="animate-fade-in flex h-full flex-col overflow-hidden rounded-card border border-edge dark:border-transparent bg-card shadow-card transition-[border-color] duration-300 hover:border-brand/25"
    >
      <header className="flex items-center justify-between gap-3 border-b border-edge bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <CalendarDays className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
          <div className="min-w-0">
            <Eyebrow>{t("dashboard.today.eyebrow")}</Eyebrow>
            <h2
              id="today-card-heading"
              className="truncate font-serif text-sm font-semibold tracking-tight text-ink first-letter:uppercase"
            >
              {dateLabel}
            </h2>
          </div>
        </div>
        <Link
          to="/calendar"
          className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-brand transition-opacity hover:opacity-80"
        >
          {/* Words from `sm`, the arrow alone on a phone — the label cut
              the date to «28 сентя…». The words stay the link's name. */}
          <span className="max-sm:sr-only">{t("dashboard.today.openFull")}</span>
          <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </Link>
      </header>

      <div className="flex min-h-0 flex-1 flex-col [justify-content:safe_center] overflow-y-auto px-4 py-3 sm:px-5 sm:py-4">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-3.5 w-3/4" />
          </div>
        ) : todayEvents.length === 0 ? (
          <div className="space-y-2.5 text-xs">
            <p className="text-ink-muted">
              {aheadEvents.length > 0 ? t("dashboard.today.empty") : t("dashboard.today.nothingAhead")}
            </p>
            {aheadEvents.length > 0 && aheadList}
          </div>
        ) : (
          <div className="space-y-2.5 text-xs">
            <ul className="space-y-2">
              {todayEvents.map((e) => {
                const over = isOver(e, now)
                return (
                  <li key={e.id} className="flex items-start gap-2.5 text-xs">
                    <span
                      aria-hidden
                      className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${over ? "bg-ink-muted/50" : "bg-brand"}`}
                    />
                    <div className="min-w-0">
                      {/* The time first: on the day itself it is the question.
                          A class that has ended says so — it sat there as the
                          day's item with nothing to tell it from one still
                          ahead — and its recording is what is left to do. */}
                      <p className="tabular-nums text-ink-muted">
                        {formatEventTimeRange(e)}
                        {e.meeting_url && isJoinableNow(e, now) && (
                          <span className="ml-1.5 font-medium text-success-ink">
                            · {Date.parse(e.event_date) <= now ? t("calendar.card.onNow") : t("calendar.card.inMinutes", { count: Math.ceil((Date.parse(e.event_date) - now) / 60000) })}
                          </span>
                        )}
                        {over && (
                          <span className="ml-1.5 rounded-full bg-muted px-1.5 py-0.5 text-[11px] font-medium text-ink-muted">
                            {t("dashboard.today.over")}
                          </span>
                        )}
                      </p>
                      <p className="truncate font-medium text-ink">{e.title}</p>
                      {e.course_title && <p className="truncate text-ink-muted">{e.course_title}</p>}
                      {/* The card answers "what do I need to do today", and
                          for a Saturday Zoom class the answer is a button,
                          not an instruction to go and find one. */}
                      <div className="mt-1.5 flex flex-wrap gap-1.5 empty:hidden">
                        {!over && (
                          <JoinMeetingLink url={e.meeting_url} title={e.title} prominent={isJoinableNow(e, now)} />
                        )}
                        <RecordingLink url={e.recording_url} title={e.title} />
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
            {/* Today is answered once its last class has ended; what comes
                next is the question then, as on an empty day. */}
            {allOver && aheadEvents.length > 0 && (
              <>
                <p className="text-ink-muted">{t("dashboard.today.ahead")}:</p>
                {aheadList}
              </>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
