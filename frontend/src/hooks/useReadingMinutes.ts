import { useTranslation } from "react-i18next"

import { useAsyncData } from "@/hooks/useAsyncData"
import { coursesService } from "@/services/courses"

/**
 * Minutes of reading per lesson of a course, in the reader's language —
 * the same numbers as the course's "≈ 2 h" and each lesson's "≈ 12 min
 * read". `null` until known or when the request fails: the outline then
 * simply shows no times, never an error.
 */
export function useReadingMinutes(courseId: string | undefined): Record<string, number> | null {
  const { i18n } = useTranslation()
  const { data } = useAsyncData(
    async () => {
      if (!courseId) return null
      try {
        return (await coursesService.getReadingTime(courseId)).chapters
      } catch {
        return null
      }
    },
    [courseId, i18n.language],
  )
  return data ?? null
}
