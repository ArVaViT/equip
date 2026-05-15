import { useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import type { Announcement } from "@/types"
import { Megaphone, X } from "lucide-react"

export default function AnnouncementBanner() {
  const { user } = useAuth()
  const { t } = useTranslation()
  const [announcement, setAnnouncement] = useState<Announcement | null>(null)
  // ``dismissedId`` rather than a plain boolean: a fresh announcement
  // (different ID) auto-resets the dismiss state, while the user's
  // X click on the *current* one stays sticky. Pre-fix the flag was
  // global, so:
  //   * a user who dismissed banner A, then admin published banner B
  //     — the user never saw B until they reloaded.
  //   * a user who dismissed banner A and logged out — the next user
  //     in the same browser tab also saw B as dismissed.
  const [dismissedId, setDismissedId] = useState<string | null>(null)

  useEffect(() => {
    if (!user) {
      setAnnouncement(null)
      setDismissedId(null)
      return
    }
    let cancelled = false
    coursesService.getAnnouncements().then((list) => {
      if (cancelled) return
      // ``setAnnouncement(null)`` for the no-match case is load-
      // bearing: without it a previously-shown banner stays mounted
      // after the system-wide announcement is unpublished. The
      // ``if (systemWide)`` guard pre-fix made that stale.
      setAnnouncement(list.find((a) => !a.course_id) ?? null)
    }).catch(() => {
      /* non-critical UI, degrade silently */
    })
    return () => { cancelled = true }
  }, [user])

  if (!announcement || announcement.id === dismissedId) return null

  return (
    <div className="border-b border-border bg-muted/40">
      <div className="container mx-auto flex items-center gap-3 px-4 py-2.5">
        <Megaphone className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden="true" />
        <div className="min-w-0 flex-1 text-wrap-safe">
          <span className="text-sm font-medium text-foreground">{announcement.title}</span>
          {announcement.content && (
            <span className="ml-2 text-sm text-muted-foreground">
              {announcement.content.length > 150
                ? `${announcement.content.slice(0, 150).trimEnd()}…`
                : announcement.content}
            </span>
          )}
        </div>
        <button
          onClick={() => setDismissedId(announcement.id)}
          className="rounded p-1 text-muted-foreground hover:bg-muted"
          aria-label={t("common.dismissAnnouncement")}
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
