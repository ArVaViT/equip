import { useState, useEffect } from "react"
import { coursesService } from "@/services/courses"
import type { Announcement } from "@/types"
import { AnnouncementPager } from "./AnnouncementPager"

interface Props {
  courseId: string
}

/**
 * Student-facing list of course announcements rendered above the
 * chapter list. Uses the shared ``AnnouncementPager`` so a course
 * with months of weekly posts collapses to a single card the student
 * can step through with arrows or keyboard — same UX as the teacher
 * editor's announcement panel, just read-only (``onDelete`` omitted).
 */
export default function CourseAnnouncements({ courseId }: Props) {
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoaded(false)
    coursesService
      .getAnnouncements(courseId)
      .then((data) => {
        if (!cancelled) setAnnouncements(data)
      })
      .catch(() => {
        if (!cancelled) setAnnouncements([])
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [courseId])

  if (!loaded || announcements.length === 0) return null

  return (
    <div className="mb-6">
      <AnnouncementPager announcements={announcements} />
    </div>
  )
}
