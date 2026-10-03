import { CalendarPlus } from "lucide-react"
import { useTranslation } from "react-i18next"

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { eventToIcs, googleCalendarUrl, icsFileName } from "@/lib/ics"
import { cn } from "@/lib/utils"
import type { CalendarEvent } from "@/types"

interface Props {
  event: CalendarEvent
  className?: string
}

/**
 * "Add to calendar" for one event: Google, or an `.ics` file for the rest.
 *
 * The file opens the "Add event" sheet on an iPhone and the default app on
 * a desktop, and Apple and Outlook import it. On an Android phone it lands
 * in Downloads and stops there — and that phone's calendar is Google — so
 * Google gets its own "add" link beside the file (2026-10-03). The subscription button on the
 * calendar page is the other half — the whole schedule, kept up to date;
 * this is one deadline or one class, kept by hand.
 *
 * Built in the browser from what the row already has; nothing is asked of
 * the server, so it works for every event the reader can see.
 */
export function AddToCalendarButton({ event, className }: Props) {
  const { t } = useTranslation()

  const download = () => {
    const blob = new Blob([eventToIcs(event, new Date(), t("meeting.recording"))], { type: "text/calendar;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = icsFileName(event)
    document.body.appendChild(a)
    a.click()
    a.remove()
    // Revoked a second later, not on the next tick: iOS Safari hands the
    // file to the Calendar sheet asynchronously and drops it if the URL is
    // already gone.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          // The calendar cell and the notification row are buttons themselves.
          onClick={(e) => e.stopPropagation()}
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
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" onClick={(e) => e.stopPropagation()}>
        <DropdownMenuItem asChild>
          <a href={googleCalendarUrl(event, t("meeting.recording"))} target="_blank" rel="noopener noreferrer">
            {t("calendar.addOne.google")}
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => download()}>{t("calendar.addOne.file")}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
