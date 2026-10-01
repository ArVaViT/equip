import type { MouseEvent } from "react"
import { CalendarPlus } from "lucide-react"
import { useTranslation } from "react-i18next"

import { eventToIcs, icsFileName } from "@/lib/ics"
import { cn } from "@/lib/utils"
import type { CalendarEvent } from "@/types"

interface Props {
  event: CalendarEvent
  className?: string
}

/**
 * "Add to calendar" for one event: hands the reader an `.ics` file.
 *
 * A file rather than a link to one provider: on an iPhone it opens the
 * system's "Add event" sheet, on a desktop the default calendar app, and
 * Google, Apple and Outlook all import it. The subscription button on the
 * calendar page is the other half — the whole schedule, kept up to date;
 * this is one deadline or one class, kept by hand.
 *
 * Built in the browser from what the row already has; nothing is asked of
 * the server, so it works for every event the reader can see.
 */
export function AddToCalendarButton({ event, className }: Props) {
  const { t } = useTranslation()

  const download = (e: MouseEvent) => {
    // The calendar cell and the notification row are buttons themselves.
    e.stopPropagation()
    const blob = new Blob([eventToIcs(event)], { type: "text/calendar;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = icsFileName(event)
    document.body.appendChild(a)
    a.click()
    a.remove()
    // Revoked on the next tick: Safari drops the download if the URL dies first.
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  return (
    <button
      type="button"
      onClick={download}
      aria-label={t("calendar.addOne.aria", { title: event.title })}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-md border border-edge px-2 py-1",
        "text-xs font-medium text-ink-muted transition-colors hover:bg-muted/40 hover:text-ink",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        className,
      )}
    >
      <CalendarPlus className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
      {t("calendar.addOne.label")}
    </button>
  )
}
