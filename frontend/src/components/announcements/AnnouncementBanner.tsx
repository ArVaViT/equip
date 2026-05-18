import { useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import type { Announcement } from "@/types"
import { Megaphone, X } from "lucide-react"

export default function AnnouncementBanner() {
  const { user } = useAuth()
  const { t, i18n } = useTranslation()
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
    if (!user?.id) {
      setAnnouncement(null)
      setDismissedId(null)
      return
    }
    let cancelled = false
    coursesService.getAnnouncements().then((list) => {
      if (cancelled) return
      // ``setAnnouncement(null)`` for the no-match case is load-
      // bearing: without it a previously-shown banner stays mounted
      // after the system-wide announcement is unpublished.
      setAnnouncement(list.find((a) => !a.course_id) ?? null)
    }).catch(() => {
      /* non-critical UI, degrade silently */
    })
    return () => { cancelled = true }
    // ``user?.id`` not ``user``: the AuthContext rewrites the user
    // object on every Supabase ``TOKEN_REFRESHED`` tick (~hourly), so
    // depending on the whole object re-fetched announcements on every
    // refresh. ``i18n.language`` is in the deps so a locale flip
    // re-pulls localised announcement content without a hard reload.
  }, [user?.id, i18n.language])

  if (!announcement || announcement.id === dismissedId) return null

  return (
    // role="status" surfaces the banner to AT as a polite live region — the
    // banner mounts mid-session whenever the user finishes loading or a new
    // announcement is published, and a screen-reader user shouldn't have to
    // re-Tab past the page just to discover it.
    <div role="status" aria-live="polite" className="border-b border-border bg-muted/40">
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
          type="button"
          onClick={() => setDismissedId(announcement.id)}
          className="rounded p-1 text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label={t("common.dismissAnnouncement")}
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
