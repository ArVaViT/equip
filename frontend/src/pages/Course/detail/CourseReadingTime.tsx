import { useTranslation } from "react-i18next"

import { useAsyncData } from "@/hooks/useAsyncData"
import { activeIntlTag } from "@/i18n/config"
import { coursesService } from "@/services/courses"

/**
 * "≈ 2 h of reading" in the course's at-a-glance line.
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
  const { t, i18n } = useTranslation()
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
  let label: string
  if (minutes < 60) {
    label = t("chapter.readingTime", { count: minutes })
  } else {
    // To the nearest half hour: "≈ 2,5 ч", not "≈ 2,4 ч" — an estimate that
    // pretends to a tenth of an hour is not more honest, only noisier.
    const hours = Math.round(minutes / 30) / 2
    const formatted = new Intl.NumberFormat(activeIntlTag(i18n.resolvedLanguage ?? i18n.language), {
      maximumFractionDigits: 1,
    }).format(hours)
    label = t("courseDetail.readingHours", { hours: formatted })
  }
  return (
    <>
      <span aria-hidden className="text-ink-muted">·</span>
      <span>{label}</span>
    </>
  )
}
