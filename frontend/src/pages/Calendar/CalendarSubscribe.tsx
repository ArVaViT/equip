import { useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { CalendarPlus, Check, Copy, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { toast } from "@/lib/toast"
import { calendarService } from "@/services/calendar"

/** `webcal://` opens the subscribe flow in Apple Calendar and Outlook. */
function webcalOf(feedUrl: string): string {
  return feedUrl.replace(/^https?:\/\//, "webcal://")
}

/** Google Calendar takes a subscription through `?cid=` with the webcal address. */
function googleOf(feedUrl: string): string {
  return `https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcalOf(feedUrl))}`
}

/**
 * Subscribe to the course calendar from a phone or desktop calendar.
 *
 * The feed has existed on the server for months (`/calendar/ical/feed`)
 * with nothing in the interface pointing at it. The subscribing calendar
 * shows each live lesson and deadline in its own zone, which is what the
 * lessons in several time zones need.
 *
 * A link is created only when asked: each new one switches the previous
 * one off, so opening this dialog must not quietly break a subscription
 * somebody already has.
 */
export function CalendarSubscribe() {
  const { t } = useTranslation()
  const descriptionId = useId()
  const [open, setOpen] = useState(false)
  const [feedUrl, setFeedUrl] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [copied, setCopied] = useState(false)

  const create = async () => {
    setCreating(true)
    try {
      const feed = await calendarService.issueIcalFeed()
      setFeedUrl(feed.feed_url)
    } catch {
      toast({ title: t("calendar.subscribe.failed"), variant: "destructive" })
    } finally {
      setCreating(false)
    }
  }

  const copy = async () => {
    if (!feedUrl) return
    try {
      await navigator.clipboard.writeText(feedUrl)
      setCopied(true)
    } catch {
      toast({ title: t("calendar.subscribe.copyFailed"), variant: "destructive" })
    }
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <CalendarPlus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("calendar.subscribe.open")}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) setCopied(false)
        }}
      >
        <DialogContent aria-describedby={descriptionId} className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("calendar.subscribe.title")}</DialogTitle>
          </DialogHeader>
          <p id={descriptionId} className="text-sm text-ink-muted">
            {t("calendar.subscribe.description")}
          </p>

          {feedUrl ? (
            <div className="space-y-3">
              <div className="flex flex-col gap-2 sm:flex-row">
                <Button asChild className="flex-1">
                  <a href={webcalOf(feedUrl)}>{t("calendar.subscribe.apple")}</a>
                </Button>
                <Button asChild variant="outline" className="flex-1">
                  <a href={googleOf(feedUrl)} target="_blank" rel="noopener noreferrer">
                    {t("calendar.subscribe.google")}
                  </a>
                </Button>
              </div>
              <Button variant="ghost" size="sm" onClick={() => void copy()}>
                {copied ? (
                  <Check className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Copy className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                )}
                {copied ? t("calendar.subscribe.copied") : t("calendar.subscribe.copy")}
              </Button>
              <p className="text-xs text-ink-muted">{t("calendar.subscribe.private")}</p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-ink-muted">{t("calendar.subscribe.replaces")}</p>
              <Button onClick={() => void create()} disabled={creating}>
                {creating && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />}
                {t("calendar.subscribe.create")}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
