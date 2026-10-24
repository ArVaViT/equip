import type { Cohort } from "@/types"
import { documentDay, formatDateLong, formatDayLong } from "@/i18n/format"

export interface CourseMaterial {
  name: string
  path: string
  size?: number
  created: string | null
}

type CohortEnrollmentStatus = "not_started" | "closed" | "open" | "no_window"

export function formatDate(dateStr: string): string {
  // Course-detail prose ("Cohort starts on…") reads better as editorial
  // natural-language than canonical ISO.
  return formatDateLong(dateStr, { month: "short" })
}

/** A group's day as the school fixed it (`start_on`), in the same prose form —
 *  no zone applied, so a reader west of the school does not see the day before.
 *  A response from an older server, without the day, falls back to the
 *  instant on the reader's clock, which is what every screen did then. */
export function formatSchoolDay(day: string | null | undefined, instant: string | null | undefined): string {
  return formatDayLong(documentDay(day, instant), { month: "short" })
}

function getCohortEnrollmentStatus(cohort: Cohort): CohortEnrollmentStatus {
  const now = new Date()
  const start = cohort.enrollment_start ? new Date(cohort.enrollment_start) : null
  const end = cohort.enrollment_end ? new Date(cohort.enrollment_end) : null
  if (start && now < start) return "not_started"
  if (end && now > end) return "closed"
  if (start || end) return "open"
  return "no_window"
}

export function isEnrollableCohort(cohort: Cohort): boolean {
  return (
    (cohort.status === "active" || cohort.status === "upcoming") &&
    getCohortEnrollmentStatus(cohort) === "open"
  )
}
