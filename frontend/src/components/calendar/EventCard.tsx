import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { BookOpen, Repeat, Upload } from "lucide-react"

import type { CalendarEvent } from "@/types"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { isJoinableNow, isOver, minutesUntil } from "@/lib/eventTime"
import { getEventColor } from "@/pages/Calendar/constants"
import { AddToCalendarButton } from "./AddToCalendarButton"
import { JoinMeetingLink } from "./JoinMeetingLink"
import { LinkifiedText } from "./LinkifiedText"
import { RecordingLink } from "./RecordingLink"
import { formatEventTimeRange } from "./eventTimeFormat"
import { useCalendarEditing } from "./calendarEditing"

/** The join button when it is the one thing on the card. */
const PROMINENT_JOIN =
  "border-brand bg-brand px-3 py-1.5 text-sm text-brand-foreground hover:bg-brand/90 [&_svg]:h-4 [&_svg]:w-4"

/**
 * One event as the reader needs it at this moment.
 *
 * The card changes with the clock rather than staying one static block:
 * a class an hour away says so and offers "add to calendar"; from fifteen
 * minutes before until it ends, "Join" is the solid button and the card
 * says "on now" or "in 12 min"; afterwards the join and the calendar
 * buttons go, and the recording — when there is one — is what is left to
 * do. A deadline that has passed says "overdue".
 */
export function EventCard({
  event,
  now,
  showDate,
  compact = false,
  className,
}: {
  event: CalendarEvent
  now: number
  /** The day too, for a list that is not already grouped by day. */
  showDate?: string
  /** For a narrow column: the time sits on the kind line, not in a column of its own. */
  compact?: boolean
  className?: string
}) {
  const { t } = useTranslation()
  const editing = useCalendarEditing()
  const color = getEventColor(event.event_type)
  const over = isOver(event, now)
  const joinable = Boolean(event.meeting_url) && isJoinableNow(event, now)
  const until = minutesUntil(event, now)
  const overdue = event.event_type === "deadline" && over
  const typeLabel = t(`calendar.eventTypes.${event.event_type}`, {
    defaultValue: event.event_type.replace("_", " "),
  })

  return (
    <article
      // ``className`` first, the state after it: the "next class" card hands
      // in its own background, and the live green must still win over it.
      className={cn(
        "rounded-lg border p-3 transition-colors",
        className,
        joinable
          ? "border-success/40 bg-success/5"
          : overdue
            ? "border-destructive/30 bg-destructive/5"
            : over
              ? "border-edge bg-muted/40"
              : "border-edge bg-surface",
      )}
    >
      <div className="flex items-start gap-3">
        {!compact && (
          <div className="hidden w-24 shrink-0 pt-0.5 sm:block">
            {showDate && <p className="text-xs text-ink-muted">{showDate}</p>}
            <p className="text-sm font-medium tabular-nums">{formatEventTimeRange(event)}</p>
          </div>
        )}
        <div className="min-w-0 flex-1">
          {/* On a phone, and in a narrow column, the time heads the card
              instead of taking a column of its own. */}
          <p className={cn("mb-1 text-sm font-medium tabular-nums", !compact && "sm:hidden")}>
            {showDate && <span className="font-normal text-ink-muted">{showDate} · </span>}
            {formatEventTimeRange(event)}
          </p>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={cn("inline-flex items-center gap-1.5 text-xs", color.text)}>
              <span className={cn("h-2 w-2 shrink-0 rounded-full", color.dot)} aria-hidden />
              {typeLabel}
            </span>
            {event.series_id && (
              <span className="inline-flex items-center text-ink-muted" title={t("eventSeries.partOfSeries")}>
                <Repeat className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                <span className="sr-only">{t("eventSeries.partOfSeries")}</span>
              </span>
            )}
            {joinable && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success-ink">
                {until === null && <span className="h-1.5 w-1.5 rounded-full bg-success motion-safe:animate-pulse" aria-hidden />}
                {until === null ? t("calendar.card.onNow") : t("calendar.card.inMinutes", { count: until })}
              </span>
            )}
            {overdue && (
              <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive-ink">
                {t("calendar.overdue")}
              </span>
            )}
          </div>
          {/* Past: quieter by colour, not by opacity — faded text fell below 4.5:1. */}
          <h3 className={cn("mt-1 text-sm font-semibold text-wrap-safe", over && !overdue && "text-ink-muted")}>
            {event.title}
          </h3>
          {event.course_title && (
            <Link
              to={`/courses/${event.course_id}`}
              className="mt-0.5 inline-flex max-w-full items-center gap-1 text-xs text-ink-muted underline-offset-4 hover:text-brand hover:underline"
            >
              <BookOpen className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden />
              <span className="truncate">{event.course_title}</span>
            </Link>
          )}
          {event.description && (
            <p className="mt-1.5 line-clamp-3 whitespace-pre-line text-xs text-ink-muted">
              <LinkifiedText text={event.description} />
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2 empty:hidden">
            {(!over || joinable) && (
              <JoinMeetingLink
                url={event.meeting_url}
                title={event.title}
                className={joinable ? PROMINENT_JOIN : undefined}
              />
            )}
            <RecordingLink url={event.recording_url} title={event.title} />
            {/* The teacher's one job after a class: put the recording where
                the class will find it. Here, not three screens away. */}
            {over && !event.recording_url && event.event_type === "live_session" && editing?.canEdit(event) && (
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => editing.addRecording(event)}>
                <Upload className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                {t("calendar.card.addRecording")}
              </Button>
            )}
            {!over && <AddToCalendarButton event={event} />}
          </div>
        </div>
      </div>
    </article>
  )
}
