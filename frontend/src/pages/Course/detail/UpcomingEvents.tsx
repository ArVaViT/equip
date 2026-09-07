import { AlertTriangle, CalendarDays } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { CalendarEvent } from "@/types"
import { formatDateLong, formatDateTime } from "@/i18n/format"

interface Props {
  events: CalendarEvent[]
}

export function UpcomingEvents({ events }: Props) {
  const { t } = useTranslation()
  if (events.length === 0) return null

  const now = new Date()
  const upcoming = events
    .filter((e) => {
      if (!e.event_date) return false
      const ts = new Date(e.event_date).getTime()
      return !Number.isNaN(ts) && ts > now.getTime() - 24 * 60 * 60 * 1000
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
        {upcoming.map((evt) => {
          const evtDate = new Date(evt.event_date)
          const overdue = evtDate < now && evt.event_type === "deadline"
          return (
            <div
              key={evt.id}
              className={`flex items-center gap-2 px-3 py-2 rounded-md border text-sm ${
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
              {/* Date AND time, in the reader's zone. This row used to say
                  «23 апр.» and nothing more — a live session at 19:00 and a
                  deadline at midnight looked the same, and a student in
                  another time zone had no way to tell which evening. */}
              <time
                dateTime={evt.event_date}
                title={formatDateTime(evt.event_date)}
                className="text-xs text-ink-muted whitespace-nowrap tabular-nums"
              >
                {formatDateLong(evtDate, {
                  year: undefined,
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>
            </div>
          )
        })}
      </div>
    </div>
  )
}
