import { PlayCircle } from "lucide-react"
import { useTranslation } from "react-i18next"

import { isAbsoluteHttpUrl } from "@/lib/url"
import { cn } from "@/lib/utils"

/**
 * "Watch the recording" — beside "Join", for the half of a live class that
 * watches later. Same rules as `JoinMeetingLink`: nothing when there is no
 * link, and the scheme checked again before it becomes an `href`.
 */
export function RecordingLink({ url, title, className }: { url: string | null | undefined; title: string; className?: string }) {
  const { t } = useTranslation()
  if (!isAbsoluteHttpUrl(url)) return null
  return (
    <a
      href={url as string}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={t("meeting.recordingAria", { title })}
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-md border border-edge px-2 py-1",
        "text-xs font-medium text-ink transition-colors hover:bg-muted/40",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        className,
      )}
    >
      <PlayCircle className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
      {t("meeting.recording")}
    </a>
  )
}
