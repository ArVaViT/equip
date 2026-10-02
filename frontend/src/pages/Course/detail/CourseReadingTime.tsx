import { useTranslation } from "react-i18next"

import { ReadingMinutes } from "@/components/course/ReadingMinutes"
import { useAsyncData } from "@/hooks/useAsyncData"
import { coursesService } from "@/services/courses"

/**
 * The course's reading time — a clock and "≈ 2 h" — in its at-a-glance line.
 *
 * An adult decides whether to start a course in about ten seconds, and "can I
 * manage this" has a number for an answer. Counted on the server from the
 * text in the reader's language, at the lesson page's own speeds, so this and
 * the "≈ 12 min read" on each lesson agree.
 *
 * Says nothing until it knows, when it is nothing, or when the request fails:
 * it is a courtesy beside the lesson count, not something to show an error for.
 * Starts with the separator so it can sit at the end of the line it joins.
 */
export function CourseReadingTime({ courseId }: { courseId: string }) {
  const { i18n } = useTranslation()
  const { data } = useAsyncData(
    async () => {
      try {
        return await coursesService.getReadingTime(courseId)
      } catch {
        return null
      }
    },
    [courseId, i18n.language],
  )
  const minutes = data?.total_minutes ?? 0
  if (minutes <= 0) return null
  return (
    <>
      <span aria-hidden className="text-ink-muted">·</span>
      <ReadingMinutes minutes={minutes} className="inline-flex items-center gap-1 tabular-nums" />
    </>
  )
}
