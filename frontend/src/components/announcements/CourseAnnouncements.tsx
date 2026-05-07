import { useState, useEffect } from "react"
import { coursesService } from "@/services/courses"
import type { Announcement } from "@/types"
import { Megaphone } from "lucide-react"
import { formatDate } from "@/i18n/format"

interface Props {
  courseId: string
}

export default function CourseAnnouncements({ courseId }: Props) {
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoaded(false)
    coursesService.getAnnouncements(courseId).then((data) => {
      if (!cancelled) setAnnouncements(data)
    }).catch(() => {
      if (!cancelled) setAnnouncements([])
    }).finally(() => {
      if (!cancelled) setLoaded(true)
    })
    return () => { cancelled = true }
  }, [courseId])

  if (!loaded || announcements.length === 0) return null

  return (
    <div className="space-y-3 mb-6">
      {announcements.map((a) => (
        <div key={a.id} className="flex gap-3 rounded-md border border-border border-l-[3px] border-l-info bg-info/5 p-4">
          <Megaphone className="mt-0.5 h-4 w-4 shrink-0 text-info" />
          <div className="min-w-0 flex-1 text-wrap-safe">
            <h4 className="text-sm font-medium">{a.title}</h4>
            <p className="mt-1 text-xs text-muted-foreground whitespace-pre-line">{a.content}</p>
            <time className="mt-1 block text-[10px] text-muted-foreground/60">
              {formatDate(a.created_at)}
            </time>
          </div>
        </div>
      ))}
    </div>
  )
}
