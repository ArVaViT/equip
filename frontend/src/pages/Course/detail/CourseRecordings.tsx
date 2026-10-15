import { useState } from "react"
import { ChevronDown, PlayCircle } from "lucide-react"
import { useTranslation } from "react-i18next"

import type { CalendarEvent } from "@/types"
import { RecordingLink } from "@/components/calendar/RecordingLink"
import { formatDateLong } from "@/i18n/format"

/** Shown before "show all": the last few classes are what a student catching up needs. */
const VISIBLE = 3

/**
 * Every class of the course that has a recording, newest first — the place
 * a student who missed Saturday goes. Before, a recording lived only on its
 * own day in the calendar and in one bell notification that scrolled away.
 * Renders nothing until there is one.
 */
export function CourseRecordings({ events }: { events: CalendarEvent[] }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const recorded = events
    .filter((e) => e.recording_url)
    .sort((a, b) => b.event_date.localeCompare(a.event_date))
  if (recorded.length === 0) return null
  const shown = expanded ? recorded : recorded.slice(0, VISIBLE)

  return (
    <section className="mb-5" aria-labelledby="course-recordings-heading">
      <h2
        id="course-recordings-heading"
        className="mb-2 flex items-center gap-2 font-serif text-sm font-semibold tracking-tight text-ink-muted"
      >
        <PlayCircle className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
        {t("courseDetail.recordings.heading")}
      </h2>
      <ul className="space-y-1.5">
        {shown.map((evt) => (
          <li
            key={evt.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border border-edge px-3 py-2 text-sm"
          >
            <span className="min-w-0 flex-1 truncate">{evt.title}</span>
            <time dateTime={evt.event_date} className="whitespace-nowrap text-xs tabular-nums text-ink-muted">
              {formatDateLong(evt.event_date, { year: undefined, month: "long", day: "numeric", weekday: "short" })}
            </time>
            <RecordingLink url={evt.recording_url} title={evt.title} />
          </li>
        ))}
      </ul>
      {recorded.length > VISIBLE && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-ink-muted hover:text-ink"
        >
          {expanded
            ? t("courseDetail.recordings.showLess")
            : t("courseDetail.recordings.showAll", { count: recorded.length })}
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
            strokeWidth={1.75}
            aria-hidden
          />
        </button>
      )}
    </section>
  )
}
