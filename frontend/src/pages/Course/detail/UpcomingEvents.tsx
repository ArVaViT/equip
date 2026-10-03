import { useState } from "react"
import { AlertTriangle, CalendarDays, ChevronDown } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { CalendarEvent } from "@/types"
import { JoinMeetingLink } from "@/components/calendar/JoinMeetingLink"
import { isJoinableNow, isOver } from "@/lib/eventTime"
import { formatEventTimeRange } from "@/components/calendar/eventTimeFormat"
import { RecordingLink } from "@/components/calendar/RecordingLink"
import { formatDateLong, formatDateTime } from "@/i18n/format"

interface Props {
  events: CalendarEvent[]
}

/**
 * What is coming, with the next one first and the rest folded away.
 *
 * The list used to render five rows permanently. On a course with a
 * month of deadlines that is a wall above the lessons, and the only row
 * anybody reads is the first one: the next thing due. The rest are now
 * behind a count — one click, no navigation — and they stay put once
 * opened.
 */
export function UpcomingEvents({ events }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  if (events.length === 0) return null

  const now = new Date()
  // Still ahead, or on now — and a deadline missed within the day, which
  // stays on top as a warning. A class already over is not "upcoming":
  // it led this list with yesterday's lesson while today's ran folded
  // away, and its recording is listed under "Recordings" anyway.
  const upcoming = events
    .filter((e) => {
      if (!e.event_date) return false
      const ts = new Date(e.event_date).getTime()
      if (Number.isNaN(ts)) return false
      if (!isOver(e, now.getTime())) return true
      return e.event_type === "deadline" && ts > now.getTime() - 24 * 60 * 60 * 1000
    })
    .slice(0, 5)

  if (upcoming.length === 0) return null

  return (
    <div className="mb-5">
      <h2 className="mb-2 flex items-center gap-2 font-serif text-sm font-semibold tracking-tight text-ink-muted">
        <CalendarDays className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
        {t("courseDetail.upcoming.heading")}
      </h2>
      <div className="space-y-1.5">
        {(expanded ? upcoming : upcoming.slice(0, 1)).map((evt) => {
          const evtDate = new Date(evt.event_date)
          const overdue = evtDate < now && evt.event_type === "deadline"
          return (
            <div
              key={evt.id}
              className={`flex flex-wrap items-center gap-x-2 gap-y-2 px-3 py-2 rounded-md border text-sm ${
                overdue
                  ? "border-l-stripe border-l-destructive border-edge bg-destructive/5"
                  : "border-edge hover:bg-muted/40"
              }`}
            >
              {overdue ? (
                <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" strokeWidth={1.75} aria-hidden />
              ) : (
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    evt.event_type === "deadline"
                      ? "bg-destructive"
                      : evt.event_type === "live_session"
                        ? "bg-info"
                        : evt.event_type === "exam"
                          ? "bg-warning"
                          : "bg-ink-muted/50"
                  }`}
                />
              )}
              <span className={`flex-1 truncate ${overdue ? "text-destructive" : ""}`}>
                {evt.title}
              </span>
              {/* Between the title and the date, so the row still ends
                  with the time — the thing a student scans this list
                  for. On a phone they take a line of their own under it:
                  two buttons beside the title pushed the row off the
                  screen. Renders nothing when there is nothing to open. */}
              <span className="order-last flex basis-full flex-wrap gap-2 pl-4 empty:hidden sm:order-none sm:basis-auto sm:pl-0">
                {!isOver(evt, now.getTime()) && (
                  <JoinMeetingLink
                    url={evt.meeting_url}
                    title={evt.title}
                    prominent={isJoinableNow(evt, now.getTime())}
                  />
                )}
                <RecordingLink url={evt.recording_url} title={evt.title} />
              </span>
              {/* Date AND time, in the reader's zone. This row used to say
                  «23 апр.» and nothing more — a live session at 19:00 and a
                  deadline at midnight looked the same, and a student in
                  another time zone had no way to tell which evening. */}
              <time
                dateTime={evt.event_date}
                title={formatDateTime(evt.event_date)}
                className="text-xs text-ink-muted whitespace-nowrap tabular-nums"
              >
                {formatDateLong(evtDate, { year: undefined, month: "short", day: "numeric" })},{" "}
                {formatEventTimeRange(evt)}
              </time>
            </div>
          )
        })}
        {upcoming.length > 1 && (
          <button
            type="button"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
            className="flex w-full items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs text-ink-muted transition-colors hover:bg-muted/40"
          >
            <ChevronDown
              className={`h-3.5 w-3.5 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
              strokeWidth={1.75}
              aria-hidden
            />
            {expanded
              ? t("courseDetail.upcoming.collapse")
              : t("courseDetail.upcoming.expand", { count: upcoming.length - 1 })}
          </button>
        )}
      </div>
    </div>
  )
}
