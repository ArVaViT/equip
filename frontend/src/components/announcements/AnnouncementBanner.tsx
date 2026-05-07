import { useState, useEffect } from "react"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import type { Announcement } from "@/types"
import { Megaphone, X } from "lucide-react"

export default function AnnouncementBanner() {
  const { user } = useAuth()
  const [announcement, setAnnouncement] = useState<Announcement | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    if (!user) {
      setAnnouncement(null)
      return
    }
    let cancelled = false
    coursesService.getAnnouncements().then((list) => {
      if (cancelled) return
      const systemWide = list.find((a) => !a.course_id)
      if (systemWide) setAnnouncement(systemWide)
    }).catch(() => {
      /* non-critical UI, degrade silently */
    })
    return () => { cancelled = true }
  }, [user])

  if (!announcement || dismissed) return null

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
          onClick={() => setDismissed(true)}
          className="rounded p-1 text-muted-foreground hover:bg-muted"
          aria-label="Dismiss announcement"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
